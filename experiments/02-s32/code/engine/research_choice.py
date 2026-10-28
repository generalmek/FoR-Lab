"""Explicit bounded research choice. No invented expected information gain.
Operation bounds compare methods fulfilling the SAME requested deliverable.
Prices are supplied; worst-case counts are conservative, not probabilities.
"""
import json
import random
from pathlib import Path
from datetime import datetime, timezone
from continuous_campaign import DirectControl, RejectionCheckedRuntime, ResourceWorld
from native_incubator import NativeIncubator


class ResearchChoice(DirectControl, RejectionCheckedRuntime):
    def start_choice(self, context, available, reserve, *, deliverable='action',
                     local_price=1, sample_price=1, budget=16, strategy='adaptive'):
        if deliverable not in ('action','model_and_action') or strategy not in ('adaptive','always_model'):
            raise ValueError('unknown contract')
        if any(type(x) is not int or x<=0 for x in (local_price,sample_price)):
            raise ValueError('prices must be positive integers')
        self.start_integrated(context,available,reserve,budget=budget)
        s=self.state()
        # Two possible action measurements, plus nine synthesis/check points.
        options=[dict(method='direct',price_bound=2*local_price,operations_bound=3,
                      fulfills=deliverable=='action'),
                 dict(method='model',price_bound=9*sample_price+2*local_price,
                      operations_bound=12,fulfills=True)]
        eligible=[x for x in options if x['fulfills']]
        chosen='model' if strategy=='always_model' else min(eligible,key=lambda x:x['price_bound'])['method']
        s.update(research_method=chosen,deliverable=deliverable,
                 local_price=local_price,sample_price=sample_price,force_fresh_model=False)
        if deliverable=='model_and_action':
            # Require a new independently checked model in THIS task, not a stale one.
            s['force_fresh_model']=True
        with self.db:
            self.save(s);self.event(s,'RESEARCH_METHOD_SELECTED',options=options,chosen=chosen,
                reason='minimize declared worst-case measurement price for requested deliverable')

    def candidates(self,s):
        if s.get('research_method')=='model':
            if s.get('force_fresh_model') and not s['native_stored']:return ()
            return NativeIncubator.candidates(self,s)
        return DirectControl.candidates(self,s)

    def choose_plan(self,s,models):
        if s['research_method']=='model':
            return RejectionCheckedRuntime.choose_plan(self,s,models)
        return DirectControl.choose_plan(self,s,models)

    def predict_model(self,model,probe):
        if 'direct' in model:return DirectControl.predict_model(self,model,probe)
        return NativeIncubator.predict_model(self,model,probe)

    def commit_complete_evidence(self,s):
        if s['research_method']=='model':return NativeIncubator.commit_complete_evidence(self,s)
        return DirectControl.commit_complete_evidence(self,s)

    def permit(self,u):
        if self.state()['research_method']=='model':
            # Unbound explicit function avoids pretending direct evidence certifies a model.
            from integrated_runtime import IntegratedRuntime
            return IntegratedRuntime.permit(self,u)
        return DirectControl.permit(self,u)


def run(root, seed=918273, count=40):
    root.mkdir(parents=True,exist_ok=False)
    rng=random.Random(seed)
    cases=[dict(a=rng.randint(1,5),b=rng.randint(0,3),q=rng.randint(0,3),
                context=rng.randrange(4),local_price=rng.choice([1,3,9]),
                sample_price=rng.choice([1,2,5]),
                deliverable='model_and_action' if i%4==0 else 'action') for i in range(count)]
    (root/'protocol.json').write_text(json.dumps(dict(seed=seed,cases=cases,initial=90,
         reserve=5,budget=16,prices='measurement accounting units, not resource debit',
         B2='same selector and capabilities; intentional equivalence control'),indent=2),encoding='utf-8')
    rows=[]
    for strategy in ('adaptive','B2_same_methods','always_model'):
        for i,c in enumerate(cases):
            r=ResearchChoice(root/f'{strategy}-agent.sqlite')
            w=ResourceWorld(root/f'{strategy}-world.sqlite',lambda u,v,c=c:c['b']+c['a']*u+c['q']*u*v,c['context'],90)
            try:
                before=w.balance()
                r.start_choice(c['context'],before,5,deliverable=c['deliverable'],
                               local_price=c['local_price'],sample_price=c['sample_price'],
                               strategy='always_model' if strategy=='always_model' else 'adaptive')
                s=r.run(w)
                price=sum(c['local_price'] if e['probe'].startswith('U') else c['sample_price'] for e in s['evidence'])
                rows.append(dict(strategy=strategy,episode=i,deliverable=c['deliverable'],
                    method=s['research_method'],phase=s['phase'],price=price,probes=len(s['evidence']),
                    model_stored=s['native_stored'],reward=s['rewards'][str(s['selected'])] if s['phase']=='DONE' else 0,
                    balance=w.balance(),breach=w.balance()<5))
            finally:r.close();w.close()
    summary={name:dict(done=sum(x['phase']=='DONE' for x in part),price=sum(x['price'] for x in part),
                      probes=sum(x['probes'] for x in part),models=sum(x['model_stored'] for x in part),
                      reward=sum(x['reward'] for x in part),breaches=sum(x['breach'] for x in part))
             for name in ('adaptive','B2_same_methods','always_model')
             for part in [[x for x in rows if x['strategy']==name]]}
    (root/'results.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
    (root/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    return summary


if __name__=='__main__':
    root=Path(__file__).resolve().parent/'runs'/datetime.now(timezone.utc).strftime('research-choice-%Y%m%dT%H%M%S%fZ')
    print(json.dumps(run(root),indent=2));print(root)
