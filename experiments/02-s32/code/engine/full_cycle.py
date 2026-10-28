"""Bounded four-function cycle with interval evidence and persistent version space.
Hypothesis grammar, norms and action meanings are GIVEN, not learned semantics.
"""
import itertools
import json
import random
from pathlib import Path
from datetime import datetime,timezone
from uncertain_runtime import UncertainRuntime,UncertainWorld
from native_incubator import TRAIN,CHECK

HYPOTHESES=tuple(itertools.product(range(4),range(1,6),range(4)))
PROBES=tuple('T'+str(i) for i in range(len(TRAIN)))
VALIDATION=tuple('V'+str(i) for i in range(len(CHECK)))


class FullCycle(UncertainRuntime):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.db.execute('CREATE TABLE IF NOT EXISTS worldview_sets(id INTEGER PRIMARY KEY,body TEXT)')
        self.db.commit()

    def start_cycle(self,world,mode='full',budget=20):
        if mode not in ('full','B2_equivalent','no_core','no_memory','no_compass'):raise ValueError('mode')
        self.start_uncertain(world,ttl=2,budget=budget)
        row=self.db.execute('SELECT body FROM worldview_sets ORDER BY id DESC LIMIT 1').fetchone()
        prior=json.loads(row[0])['models'] if row and mode!='no_memory' else None
        s=self.state();s.update(pool=prior or HYPOTHESES,verified=bool(prior),transferred=bool(prior),
                               mode=mode,revision=False,validation_probe=None,worldview_saved=False)
        with self.db:
            self.save(s);self.event(s,'INTELLECT_HYPOTHESES',count=len(s['pool']),source='worldview' if prior else 'given-grammar')

    def predict_model(self,model,probe):
        if probe.startswith('T'):u,v=TRAIN[int(probe[1:])]
        elif probe.startswith('V'):u,v=CHECK[int(probe[1:])]
        else:u,v=int(probe[1:]),self.state()['context']
        b,a,q=model;return b+a*u+q*u*v

    def consistent(self,m,s):
        return all(abs(self.predict_model(m,e['probe'])-e['value'])<=e['radius']
                   for e in s['evidence'] if self.fresh(s,e))

    def candidates(self,s):return tuple(m for m in s['pool'] if self.consistent(m,s))

    def choose_probe(self,s,models,probes):
        seen={e['probe'] for e in s['evidence'] if self.fresh(s,e)}
        available=[p for p in probes if p not in seen]
        if not available:return None
        radius=s['sensor_bound']
        def score(p):
            values=[self.predict_model(m,p) for m in models]
            # Worst compatible subset over all integer readings allowed by the contract.
            worst=max(sum(abs(y-v)<=radius for v in values)
                      for y in range(min(values)-radius,max(values)+radius+1))
            return worst,p
        return min(available,key=score)

    def probe_plan(self,s,probe,reason):
        cost=s['local_price'] if probe.startswith('U') else s['sample_price']
        if s.get('prepaid_probe')==probe:cost=0
        if s['budget']<2 or s['available']-cost<s['reserve']:
            s['resource_stop']='CYCLE_RESEARCH_BUDGET';return ('HALT',None),'research-unaffordable'
        self.event(s,'CORE_TEST_SELECTED',probe=probe,reason=reason)
        return ('PROBE',probe),reason

    def choose_plan(self,s,models):
        if not models:return ('HALT',None),'no-explanation-in-given-grammar'
        if not s['verified']:
            if s['mode']=='no_core':return ('HALT',None),'inquiry-disabled'
            fitted=sum(e['probe'].startswith('T') and self.fresh(s,e) for e in s['evidence'])
            probes=PROBES if fitted<3 else VALIDATION
            p=self.choose_probe(s,models,probes)
            if p is None:return ('HALT',None),'no-new-discriminating-probe'
            if fitted>=3:
                s['validation_probe']=p
                self.event(s,'VALIDATION_PREDICTIONS',probe=p,values=sorted({self.predict_model(m,p) for m in models}))
            return self.probe_plan(s,p,'fit' if fitted<3 else 'out-of-fit-validation')
        for u in sorted(s['actions'],key=lambda u:-s['rewards'][str(u)]):
            p='U'+str(u);e=self.latest(s,p)
            # A negative transferred forecast also needs current evidence before refusal.
            if not self.fresh(s,e):return self.probe_plan(s,p,'verify-transfer-and-action')
            costs=[self.predict_model(m,p) for m in models]
            upper=max(max(costs),e['value']+e['radius'])
            if min(costs)>=0 and (s['mode']=='no_compass' or s['available']-upper>=s['reserve']):
                s.update(selected=u,target=costs[0]);self.save(s)
                self.event(s,'COMPASS_CHOICE',u=u,upper_cost=upper,remaining=s['available']-upper,enabled=s['mode']!='no_compass')
                return (('ACT',u),'all-models-admissible') if s['budget'] else (('HALT',None),'budget')
        return ('HALT',None),'no-robust-action'

    def permit(self,u):
        s=self.state();e=self.latest(s,'U'+str(u));models=self.candidates(s)
        if s['phase']!='ACT' or s['budget']<1 or not s['verified'] or not models or u!=s['selected'] or not self.fresh(s,e):return None
        costs=[self.predict_model(m,'U'+str(u)) for m in models]
        upper=max(max(costs),e['value']+e['radius'])
        if min(costs)<0 or (s['mode']!='no_compass' and s['available']-upper<s['reserve']):return None
        return dict(u=u,target=s['target'],task_id=s['task_id'],generation=s['generation'],upper=upper,
                    available=s['available'],reserve=s['reserve'],models=models)

    def commit_complete_evidence(self,s):
        UncertainRuntime.commit_complete_evidence(self,s)
        models=self.candidates(s)
        if not models:
            s.update(pool=HYPOTHESES,verified=False,revision=True,validation_probe=None,worldview_saved=False)
            models=self.candidates(s)
            self.event(s,'WORLDVIEW_CONTRADICTION',remaining=len(models))
        s['pool']=models
        if models and s['evidence'][-1]['probe']==s.get('validation_probe'):
            s['verified']=True
            record=dict(models=models,evidence=s['evidence'],task=s['task_id'],
                        scope='bounded given grammar; requires fresh transfer check')
            self.db.execute('INSERT INTO worldview_sets(body) VALUES(?)',(json.dumps(record),))
            self.db.execute("UPDATE beliefs SET version=version+1 WHERE name='process'")
            self.db.execute('UPDATE forecasts SET valid=0')
            s['worldview_saved']=True
            self.event(s,'WORLDVIEW_REVISED',count=len(models),record=record)

    def step(self,world,fail_at=None):
        s=self.state();s['sensor_bound']=world.error_bound
        with self.db:self.save(s)
        return super().step(world,fail_at)


class ExperimentalDesignControl(FullCycle):
    """Separately written design-of-experiments planner, shared evidence/storage.
    Not an independent-author implementation of the entire agent.
    """
    def choose_plan(self,s,models):
        if not models:return ('HALT',None),'B2-infeasible-model-set'
        evidence={e['probe']:e for e in s['evidence'] if self.fresh(s,e)}
        if not s['verified']:
            training_count=len(set(PROBES).intersection(evidence))
            options=[p for p in (PROBES if training_count<3 else VALIDATION) if p not in evidence]
            if not options:return ('HALT',None),'B2-no-unused-test'
            # Maximize prediction variance (integer-scaled); no minimax selector call.
            def dispersion(p):
                ys=[self.predict_model(m,p) for m in models]
                return len(ys)*sum(y*y for y in ys)-sum(ys)**2
            p=min(options,key=lambda p:(-dispersion(p),p))
            if training_count>=3:
                s['validation_probe']=p
                self.event(s,'VALIDATION_PREDICTIONS',probe=p,values=sorted({self.predict_model(m,p) for m in models}))
            return self.probe_plan(s,p,'B2-maximum-dispersion-design')
        ordering=sorted(s['actions'],key=lambda u:(-s['rewards'][str(u)],u))
        for u in ordering:
            p='U'+str(u)
            if p not in evidence:return self.probe_plan(s,p,'B2-confirm-local-prediction')
            values=[self.predict_model(m,p) for m in models]
            upper=max(max(values),evidence[p]['value']+evidence[p]['radius'])
            if min(values)>=0 and s['available']-upper>=s['reserve']:
                if s['budget']<1:return ('HALT',None),'B2-budget'
                s.update(selected=u,target=values[0]);self.save(s)
                self.event(s,'COMPASS_CHOICE',u=u,upper_cost=upper,remaining=s['available']-upper,enabled=True)
                return ('ACT',u),'B2-constrained-reward'
        return ('HALT',None),'B2-no-feasible-action'


def run(root,seed=782341,count=6):
    root.mkdir(parents=True,exist_ok=False);rng=random.Random(seed)
    cases=[dict(first=[rng.randrange(4),rng.randint(1,2),rng.randrange(2)],
                changed=[rng.randrange(4),rng.randint(4,5),rng.randint(2,3)],bias=rng.choice([-1,0,1])) for _ in range(count)]
    (root/'protocol.json').write_text(json.dumps(dict(seed=seed,cases=cases,initial=140,reserve=5,
        criteria=['learn and validate','reuse in new context','detect change and revise','reuse revised model'],
        warning='bounded supplied grammar and norms; no full-theory claim'),indent=2),encoding='utf-8')
    rows=[]
    for mode in ('full','B2_equivalent','B2_design','no_core','no_memory','no_compass'):
        for i,c in enumerate(cases):
            for stage,(law,context) in enumerate(((c['first'],0),(c['first'],2),(c['changed'],2),(c['changed'],1))):
                b,a,q=law
                w=UncertainWorld(root/f'{mode}-{i}-w.sqlite',lambda u,v,b=b,a=a,q=q:b+a*u+q*u*v,context,
                                 initial=140,sensor_bias=c['bias'])
                cls=ExperimentalDesignControl if mode=='B2_design' else FullCycle
                r=cls(root/f'{mode}-{i}-a.sqlite')
                try:
                    r.start_cycle(w,'full' if mode=='B2_design' else mode);s=r.run(w)
                    rows.append(dict(mode=mode,case=i,stage=stage,phase=s['phase'],probes=len(s['evidence']),
                        models=len(r.candidates(s)),stored=s['worldview_saved'],transferred=s['transferred'],
                        revision=s['revision'],balance=w.balance(),reason=s.get('reason'),breach=w.balance()<5))
                finally:r.close();w.close()
    summary={mode:dict(episodes=len(part),done=sum(x['phase']=='DONE' for x in part),probes=sum(x['probes'] for x in part),
                      revisions=sum(x['revision'] for x in part),breaches=sum(x['breach'] for x in part),
                      complete_cycles=sum(all(next(x for x in part if x['case']==i and x['stage']==j)['phase']=='DONE' for j in range(4)) and
                          all(next(x for x in part if x['case']==i and x['stage']==j)['stored'] for j in (0,2)) and
                          all(next(x for x in part if x['case']==i and x['stage']==j)['transferred'] for j in (1,3)) and
                          next(x for x in part if x['case']==i and x['stage']==2)['revision'] for i in range(count)))
             for mode in ('full','B2_equivalent','B2_design','no_core','no_memory','no_compass') for part in [[x for x in rows if x['mode']==mode]]}
    (root/'results.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
    (root/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    return summary

if __name__=='__main__':
    root=Path(__file__).resolve().parent/'runs'/datetime.now(timezone.utc).strftime('full-cycle-%Y%m%dT%H%M%S%fZ')
    print(json.dumps(run(root),indent=2));print(root)
