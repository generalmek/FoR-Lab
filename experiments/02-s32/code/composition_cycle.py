"""General finite monomial constructor; meanings remain supplied, not invented."""
import itertools
import json
from procedural_cycle import ProceduralCycle
from full_cycle import HYPOTHESES
from uncertain_runtime import UncertainRuntime

def construct(max_degree):
    for degree in range(1,max_degree+1):
        for variables in itertools.combinations_with_replacement('uv',degree):
            powers=(variables.count('u'),variables.count('v'))
            if powers in ((1,0),(1,1)):continue
            for base in HYPOTHESES:
                for coefficient in (1,2):yield (*base,coefficient,*powers)

class CompositionCycle(ProceduralCycle):
    def start_cycle(self,world,*args,**kwargs):
        super().start_cycle(world,*args,**kwargs)
        s=self.state();s.update(construction_degree=5,search_limit=2880)
        with self.db:self.save(s)

    def commit_complete_evidence(self,s):
        # Preserve the diagnosing engine's calibrated-evidence contract before fitting.
        cal=s.get('calibration')
        if cal is None:raise RuntimeError('uncalibrated observation')
        e=s['evidence'][-1];raw=e['value']
        e.update(value=(raw-cal['bias'])/cal['gain'],raw=raw,calibration_epoch=cal['epoch'],
            calibration_operations=[x['operation_id'] for x in cal['evidence']],
            receiver_id=self.active_world.receiver_id,operation_id=self.active_world.measurement_key)
        UncertainRuntime.commit_complete_evidence(self,s)
        models=self.candidates(s);reset=False
        if not models:
            reset=True
            s.update(verified=False,revision=True,validation_probe=None,worldview_saved=False)
            s['validation_epoch']+=1
            models=tuple(m for m in HYPOTHESES if self.consistent(m,s))
            self.event(s,'WORLDVIEW_CONTRADICTION',remaining=len(models))
            if not models:
                self.event(s,'CONSTRUCTION_QUESTION',cause=s['evidence'][-1],
                    question='Which bounded product of known inputs explains the contradiction?')
                survivors=[];exhausted=False
                for model in construct(s['construction_degree']):
                    if s['search_used']>=s['search_limit']:exhausted=True;break
                    s['search_used']+=1
                    if self.consistent(model,s):survivors.append(model)
                models=() if exhausted else tuple(survivors)
                s['search_status']='SEARCH_BUDGET_EXHAUSTED' if exhausted else 'BOUNDED_SEARCH_COMPLETE'
                s['expansions']+=1
                self.event(s,'CONSTRUCTION_SEARCH',evaluated=s['search_used'],survivors=len(survivors),
                    status=s['search_status'],grammar='base + coefficient * product(u,v); degree<=5')
        s['pool']=models
        if models and not reset and s['evidence'][-1]['probe']==s.get('validation_probe'):
            s['verified']=True
            record=dict(models=models,evidence=s['evidence'],task=s['task_id'],
                        scope='finite constructed monomial; new validation and transfer required')
            self.db.execute('INSERT INTO worldview_sets(body) VALUES(?)',(json.dumps(record),))
            self.db.execute("UPDATE beliefs SET version=version+1 WHERE name='process'")
            self.db.execute('UPDATE forecasts SET valid=0');s['worldview_saved']=True
            self.event(s,'WORLDVIEW_REVISED',count=len(models),record=record)
