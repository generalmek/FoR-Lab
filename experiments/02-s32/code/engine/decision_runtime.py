"""Finite minimax inquiry plus task-scoped permission, not full model certification."""
from functools import lru_cache
from fractions import Fraction
from conflict_diagnosis import HYPOTHESES, PROBES, predicted
from incubator_runtime import Runtime
from revision_gate import assess_revision
import json

def robust_action(models,target,actions,seen):
    return next((u for u in actions if 'U'+str(u) in seen and models and
                 all(g*u==target for g,b in models)),None)

def select(models,target,actions,seen,budget,costs,penalty,policy='decision'):
    """Costs are declared objective weights; budget counts actual operations."""
    @lru_cache(None)
    def solve(ms,ss,left):
        u=robust_action(ms,target,actions,ss)
        if u is not None and left>=1: return Fraction(0),('ACT',u)
        if not ms or not any(g*u==target for g,b in ms for u in actions):
            return Fraction(0),('HALT',None)
        if left<2:
            return Fraction(penalty),('HALT',None)
        best=(Fraction(penalty),('HALT',None))
        for p in PROBES:
            if p in ss: continue
            groups=tuple(tuple(m for m in ms if predicted(m,p)==v) for v in sorted({predicted(m,p) for m in ms}))
            score=Fraction(costs[p])+max(solve(group,tuple(sorted((*ss,p))),left-1)[0] for group in groups)
            if score<best[0]: best=(score,('PROBE',p))
        return best
    value,action=solve(tuple(models),tuple(sorted(seen)),budget)
    if policy=='information' and action[0]=='PROBE':
        options=[p for p in PROBES if p not in seen]
        p=max(options,key=lambda p:(len({predicted(m,p) for m in models}),-PROBES.index(p)))
        return ('PROBE',p),str(value)
    return action,str(value)

class DecisionRuntime(Runtime):
    def start_decision(self,target,budget=6,actions=(1,2),costs=None,penalty='2',policy='decision'):
        if not actions or any(type(u) is not int or u not in (1,2) for u in actions):
            raise ValueError('unsupported actions')
        costs=costs or {p:'1/10' for p in PROBES}
        if set(costs)!=set(PROBES) or any(Fraction(c)<0 for c in costs.values()) or Fraction(penalty)<0:
            raise ValueError('invalid costs')
        if policy not in ('decision','information'): raise ValueError('invalid policy')
        super().start(target,budget)
        s=self.state()
        s.update(phase='ASSESS',evidence=[],certified=False,scope=[],generation=s['generation']+1,
                 actions=list(actions),costs={p:str(c) for p,c in costs.items()},penalty=str(penalty),policy=policy,
                 decision_contract='finite-minimax-v1')
        with self.db: self.save(s); self.event(s,'FRESH_TASK_PERMISSION_POLICY')

    def candidates(self,s):
        return tuple(m for m in HYPOTHESES if all(predicted(m,e['probe'])==e['value'] for e in s['evidence']))

    def commit_complete_evidence(self,s):
        """Called inside the observation transaction; never promotes partial evidence."""
        if {e['probe'] for e in s['evidence']}!=set(PROBES):return
        before=self.beliefs()
        report=assess_revision((before['process'][0],before['sensor'][0]),s['evidence'],s['trusted'])
        if 'model' not in report:
            self.event(s,'REVISION_DENIED',report=report);return
        changed=set(report['changed'])
        for name,value in zip(('process','sensor'),report['model']):
            if name in changed:
                self.db.execute('UPDATE beliefs SET value=?,version=version+1 WHERE name=?',(value,name))
        for name,deps in self.db.execute('SELECT name,deps FROM forecasts').fetchall():
            if changed.intersection(json.loads(deps)):
                self.db.execute('UPDATE forecasts SET valid=0 WHERE name=?',(name,))
        self.db.execute('INSERT INTO runtime_revisions(body) VALUES(?)',
                        (json.dumps(dict(task_id=s['task_id'],before=before,report=report,evidence=s['evidence'])),))
        # Record scoped knowledge, not a perpetual licence for future actions.
        self.event(s,'FULL_LOCAL_REVISION',report=report)

    def permit(self,u):
        s=self.state(); models=self.candidates(s); seen={e['probe'] for e in s['evidence']}
        if s.get('decision_contract')!='finite-minimax-v1': return None
        if s['phase']!='ACT' or s['budget']<1 or not s['trusted'] or u not in s['actions']: return None
        if robust_action(models,s['target'],(u,),seen) is None: return None
        return dict(u=u,generation=s['generation'],task_id=s['task_id'],target=s['target'],
                    basis_versions={k:v[1] for k,v in self.beliefs().items()})

    def validate_permission(self,permission):
        return bool(permission and permission==self.permit(permission['u']))

    def choose_plan(self,s,models):
        return select(models,s['target'],tuple(s['actions']),
                      tuple(e['probe'] for e in s['evidence']),s['budget'],
                      s['costs'],s['penalty'],s['policy'])

    def predict_model(self,model,probe):
        return predicted(model,probe)

    def step(self,world,fail_revision=False):
        s=self.state()
        if s['phase'] in ('IDLE','HALT','DONE'): return s
        if s.get('decision_contract')!='finite-minimax-v1': raise ValueError('wrong runtime contract')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            s=self.state(); models=self.candidates(s)
            if not s['trusted']:
                s.update(phase='HALT',reason='UNTRUSTED_CAL')
            else:
                action,value=self.choose_plan(s,models)
                self.event(s,'PLAN',chosen=action,worst_case_loss=value,candidates=models)
                kind,arg=action
                if kind=='HALT':
                    s.update(phase='HALT',reason='OUT_OF_CLASS' if not models else 'NO_WORTHWHILE_CERTIFIED_PLAN')
                elif kind=='PROBE':
                    observed=world.measure(arg); s['budget']-=1
                    s['evidence'].append(dict(probe=arg,value=observed)); s['phase']='ASSESS'
                    self.event(s,'PROBE',probe=arg,value=observed)
                    self.commit_complete_evidence(s)
                else:
                    s['phase']='ACT'; self.save(s)
                    permission=self.permit(arg)
                    if permission is None: raise RuntimeError('planner bypassed permission')
                    observed=world.execute(arg,s['target']); s['budget']-=1
                    self.event(s,'PROCESS',u=arg,observed=observed,permit=permission)
                    if observed not in {self.predict_model(m,'U'+str(arg)) for m in models}:
                        s.update(phase='HALT',reason='EXECUTION_MISMATCH')
                    else: s['phase']='DONE'
                    # Permission is task-local. Do NOT certify or revise full beliefs.
            self.save(s); self.db.commit(); return s
        except BaseException:
            self.db.rollback(); raise
