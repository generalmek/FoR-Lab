"""Bounded synthesis of inquiry sequences in the existing living executor.
Supplied probe semantics and trusted physical receipts, not learned semantics.
"""
import itertools
import hashlib
import json
from diagnosing_cycle import DiagnosingCycle, ReferenceWorld
from full_cycle import PROBES


class ProcedureWorld(ReferenceWorld):
    def __init__(self,*args,probe_prices=None,**kwargs):
        super().__init__(*args,**kwargs)
        self.probe_prices=dict(probe_prices or {})
        if any(p not in PROBES or type(c) is not int or c<1 for p,c in self.probe_prices.items()):
            raise ValueError('invalid probe cost contract')

    def price(self,probe):
        return self.probe_prices.get(probe,super().price(probe))


class ProceduralCycle(DiagnosingCycle):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.db.execute('CREATE TABLE IF NOT EXISTS procedures(id INTEGER PRIMARY KEY,body TEXT)')
        self.db.commit()

    def start_cycle(self,world,*args,**kwargs):
        super().start_cycle(world,*args,**kwargs)
        s=self.state();s['procedure_id']=None
        with self.db:self.save(s)

    def compile_procedure(self,s,models):
        # Enumerate finite two-observation programs; minimize worst ambiguity,
        # then current receiver cost. Remaining probes are a bounded fallback.
        costs={p:self.active_world.price(p) for p in PROBES}
        old=self.db.execute('SELECT id,body FROM procedures ORDER BY id DESC LIMIT 1').fetchone()
        prior=json.loads(old[1]) if old else None
        if (prior and prior['status']=='validated' and prior['costs']==costs
                and prior['source_models']==json.loads(json.dumps(models))):
            record=dict(prior,source_task=s['task_id'],previous_id=old[0],
                        previous_status=prior['status'],transfer='cached-applicable-program',
                        search_nodes=0,status='candidate',evidence=[],
                        outcome_operation=None,outcome_receipt=None,reason=None)
            cursor=self.db.execute('INSERT INTO procedures(body) VALUES(?)',(json.dumps(record),))
            s['procedure_id']=cursor.lastrowid
            self.event(s,'PROCEDURE_REUSED',procedure_id=cursor.lastrowid,previous_id=old[0])
            return record
        options=[]
        for pair in itertools.combinations(PROBES,2):
            buckets={}
            for m in models:
                signature=tuple(self.predict_model(m,p) for p in pair)
                buckets[signature]=buckets.get(signature,0)+1
            options.append((max(buckets.values(),default=0),sum(costs[p] for p in pair),pair))
        best=min(options);pair=list(best[2])
        record=dict(purpose='resolve process uncertainty, validate, then guarded physical action',
            assumptions=['given probe meanings','finite model grammar','trusted physical receipt'],
            roles=['fit','out-of-fit validation','fresh local observation','authorized action','receipt check'],
            fit_order=pair+sorted(set(PROBES)-set(pair),key=lambda p:(costs[p],p)),
            costs=costs,worst_pair_ambiguity=best[0],search_nodes=len(options),
            source_task=s['task_id'],source_models=models,
            previous_id=old[0] if old else None,
            transfer='recompiled-current-costs' if prior and prior['costs']!=costs else ('rechecked-current-models' if prior else 'constructed'),
            previous_status=prior['status'] if prior else None,
            status='candidate',failure_conditions=['budget','unresolved evidence','receipt mismatch'],
            evidence=[])
        cursor=self.db.execute('INSERT INTO procedures(body) VALUES(?)',(json.dumps(record),))
        s['procedure_id']=cursor.lastrowid
        self.event(s,'PROCEDURE_CONSTRUCTED',record=record,procedure_id=cursor.lastrowid)
        return record

    def choose_plan(self,s,models):
        if s.get('procedure_id') is None:self.compile_procedure(s,models)
        choice=super().choose_plan(s,models)
        if choice[0][0]=='ACT':
            s['authorization_basis']={k:v[1] for k,v in self.beliefs().items()}
            self.save(s)
        return choice

    def choose_probe(self,s,models,probes):
        if tuple(probes)==tuple(PROBES) and s.get('procedure_id'):
            record=json.loads(self.db.execute('SELECT body FROM procedures WHERE id=?',(s['procedure_id'],)).fetchone()[0])
            seen={e['probe'] for e in s['evidence'] if self.fresh(s,e)}
            return next((p for p in record['fit_order'] if p not in seen),None)
        return super().choose_probe(s,models,probes)

    def probe_plan(self,s,probe,reason):
        cost=0 if s.get('prepaid_probe')==probe else self.active_world.price(probe)
        if s['budget']<2 or s['available']-cost<s['reserve']:
            s['resource_stop']='PROCEDURE_UNAFFORDABLE'
            return ('HALT',None),'current-operation-cost'
        self.event(s,'PROCEDURE_OPERATION',probe=probe,cost=cost,reason=reason)
        return ('PROBE',probe),reason

    def permit(self,u):
        permission=super().permit(u)
        if not permission:return None
        s=self.state()
        versions={k:v[1] for k,v in self.beliefs().items()}
        if s.get('authorization_basis')!=versions:return None
        row=self.db.execute('SELECT body FROM procedures WHERE id=?',(s.get('procedure_id'),)).fetchone()
        if not row or json.loads(row[0])['status']!='candidate':return None
        permission.update(procedure_id=s['procedure_id'],
            procedure_digest=hashlib.sha256(row[0].encode()).hexdigest(),
            basis_versions=versions)
        return permission

    def tick(self,world):
        result=super().tick(world)
        pid=result.get('procedure_id')
        if pid and result['phase'] in ('DONE','HALT'):
            with self.db:
                record=json.loads(self.db.execute('SELECT body FROM procedures WHERE id=?',(pid,)).fetchone()[0])
                if record['status']=='candidate':
                    intent=self.db.execute("SELECT id,body FROM intents WHERE status='done' ORDER BY rowid DESC LIMIT 1").fetchone()
                    if result['phase']!='DONE' and result.get('reason')!='EXECUTION_MISMATCH':intent=None
                    record.update(status='validated' if result['phase']=='DONE' else 'revoked',
                        reason=result.get('reason'),evidence=result['evidence'],
                        outcome_operation=intent[0] if intent else None,
                        outcome_receipt=world.lookup(intent[0]) if intent else None)
                    self.db.execute('UPDATE procedures SET body=? WHERE id=?',(json.dumps(record),pid))
                    self.event(result,'PROCEDURE_OUTCOME',procedure_id=pid,status=record['status'])
        return result

    def next_goal(self,world,budget=80):
        """Explicit new external goal; retain memories, never reset an active life."""
        if not self.life() or self.life()['status'] not in ('DONE','STOPPED'):
            raise ValueError('previous goal is active')
        with self.db:self.db.execute('DELETE FROM life WHERE id=1')
        return self.begin(world,budget=budget)
