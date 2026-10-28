"""Development correction evaluated on PREVIOUS cases, not a holdout result."""
import json
import hashlib
from pathlib import Path
from datetime import datetime,timezone
from full_cycle import FullCycle,VALIDATION
from uncertain_runtime import UncertainWorld
from stress_protocol import external_metrics


class BudgetAwareCycle(FullCycle):
    def choose_plan(self,s,models):
        fitted=any(e['probe'].startswith('T') and self.fresh(s,e) for e in s['evidence'])
        if s['mode']!='no_core' and not s['verified'] and len(models)==1 and fitted:
            p=self.choose_probe(s,models,VALIDATION)
            if p is not None:
                s['validation_probe']=p
                self.event(s,'VALIDATION_PREDICTIONS',probe=p,values=[self.predict_model(models[0],p)],
                           reason='single-survivor; skip redundant fitting, retain new validation')
                return self.probe_plan(s,p,'validate-single-surviving-hypothesis')
        return super().choose_plan(s,models)


def run(root):
    root.mkdir(parents=True,exist_ok=False)
    base=Path(__file__).parent/'runs/stress-20261025T104025450401Z'
    cases=json.loads((base/'protocol.json').read_text())['cases']
    manifest={}
    source=root/'source';source.mkdir()
    for f in Path(__file__).parent.glob('*.py'):
        data=f.read_bytes();(source/f.name).write_bytes(data);manifest[f.name]=hashlib.sha256(data).hexdigest()
    (root/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    (root/'protocol.json').write_text(json.dumps(dict(cases=cases,origin=str(base),status='same-case development evaluation; no held-out claim'),indent=2),encoding='utf-8')
    rows=[]
    for i,c in enumerate(cases):
        for stage,(params,context) in enumerate(((c['first'],0),(c['first'],2),(c['changed'],2),(c['changed'],1))):
            b,a,q=params;extra=int(c['family']=='outside')
            law=lambda u,v,b=b,a=a,q=q,extra=extra:b+a*u+q*u*v+extra*u**3
            w=UncertainWorld(root/f'w-{i}.sqlite',law,context,initial=80,error_bound=c['radius'],sensor_bias=c['bias'])
            r=BudgetAwareCycle(root/f'a-{i}.sqlite')
            try:
                before=w.balance();n=w.db.execute('SELECT COUNT(*) FROM receipts').fetchone()[0]
                r.start_cycle(w,budget=c['budget']);s=r.run(w)
                actions=[json.loads(x[0])[0] for x in w.db.execute('SELECT request FROM receipts ORDER BY rowid')][n:]
                rows.append(dict(case=i,stage=stage,phase=s['phase'],reason=s.get('reason'),probes=len(s['evidence']),
                                 **external_metrics(before,w.balance(),actions,law,context)))
            finally:r.close();w.close()
    summary=dict(actions=sum(x['reward']>0 for x in rows),reward=sum(x['reward'] for x in rows),
                 probes=sum(x['probes'] for x in rows),resource_spent=sum(x['resource_spent'] for x in rows),
                 breaches=sum(x['reserve_breach'] for x in rows),mismatches=sum(x['reason']=='EXECUTION_MISMATCH' for x in rows))
    (root/'results.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
    (root/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    return summary

if __name__=='__main__':
    root=Path(__file__).parent/'runs'/datetime.now(timezone.utc).strftime('budget-revision-%Y%m%dT%H%M%S%fZ')
    print(json.dumps(run(root),indent=2));print(root)
