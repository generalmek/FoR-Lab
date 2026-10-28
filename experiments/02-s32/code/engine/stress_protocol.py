"""Frozen difficulty grid, replacement controls, external outcome metrics.
No tuning to make FoR win; all cells, including failed/out-of-grammar, retained.
"""
import hashlib
import json
import random
from pathlib import Path
from datetime import datetime,timezone
from full_cycle import FullCycle,ExperimentalDesignControl
from uncertain_runtime import UncertainWorld


class FixedResearch(FullCycle):
    def choose_probe(self,s,models,probes):
        seen={e['probe'] for e in s['evidence'] if self.fresh(s,e)}
        return next((p for p in probes if p not in seen),None)


class RandomResearch(FullCycle):
    def choose_probe(self,s,models,probes):
        seen={e['probe'] for e in s['evidence'] if self.fresh(s,e)}
        options=[p for p in probes if p not in seen]
        if not options:return None
        # Deterministic independent stream, reproducible after process restart.
        seed=s['task_id']*1009+s['generation']*101+len(s['evidence'])*17
        return random.Random(seed).choice(options)


def external_metrics(before,after,effects,law,context,reserve=5):
    rewards={1:4,2:10}
    best=max([0]+[rewards[u] for u in (1,2) if 0<=law(u,context)<=before-reserve])
    reward=sum(rewards[u] for u in effects)
    return dict(reward=reward,oracle_reward=best,opportunity_gap=best-reward,
                resource_spent=before-after,reserve_breach=after<reserve)


def run(root,seed=871223,repeats=2,budgets=(5,10),radii=(0,1,2),families=('inside','outside')):
    root.mkdir(parents=True,exist_ok=False);rng=random.Random(seed);cases=[]
    for budget in budgets:
        for radius in radii:
            for family in families:
                for rep in range(repeats):
                    cases.append(dict(budget=budget,radius=radius,family=family,rep=rep,
                        first=[rng.randrange(4),rng.randint(1,3),rng.randrange(3)],
                        changed=[rng.randrange(4),rng.randint(3,5),rng.randint(1,3)],
                        bias=rng.randint(-radius,radius)))
    protocol=dict(seed=seed,cases=cases,initial=80,reserve=5,
        policies=['full','B2_design','fixed','random','no_memory'],
        metric='Reward and spending per cycle; opportunity_gap is per-task clairvoyant upper bound at pre-inquiry balance, NOT optimal trajectory regret.',
        selection='All grid cells retained; no success-rate target or winner selection.',
        observation='constant sensor bias bounded by declared radius; not independent random noise',
        generalization='developer-generated evaluation, not independent external replication')
    protocol_bytes=json.dumps(protocol,indent=2).encode()
    (root/'protocol.json').write_bytes(protocol_bytes)
    source=root/'source';source.mkdir();manifest={}
    for f in sorted(Path(__file__).parent.glob('*.py')):
        data=f.read_bytes();(source/f.name).write_bytes(data);manifest[f.name]=hashlib.sha256(data).hexdigest()
    (root/'manifest.json').write_text(json.dumps(dict(source_sha256=manifest,protocol_sha256=hashlib.sha256(protocol_bytes).hexdigest()),indent=2),encoding='utf-8')
    rows=[]
    for name,cls in [('full',FullCycle),('B2_design',ExperimentalDesignControl),('fixed',FixedResearch),('random',RandomResearch),('no_memory',FullCycle)]:
        for i,c in enumerate(cases):
            for stage,(params,context) in enumerate(((c['first'],0),(c['first'],2),(c['changed'],2),(c['changed'],1))):
                b,a,q=params
                extra=1 if c['family']=='outside' else 0
                law=lambda u,v,b=b,a=a,q=q,extra=extra:b+a*u+q*u*v+extra*u**3
                w=UncertainWorld(root/f'{name}-{i}-w.sqlite',law,context,initial=80,
                    error_bound=c['radius'],sensor_bias=c['bias'])
                r=cls(root/f'{name}-{i}-a.sqlite')
                try:
                    before=w.balance();n=w.db.execute('SELECT COUNT(*) FROM receipts').fetchone()[0]
                    r.start_cycle(w,'no_memory' if name=='no_memory' else 'full',budget=c['budget']);s=r.run(w)
                    actual=[json.loads(x[0])[0] for x in w.db.execute('SELECT request FROM receipts ORDER BY rowid')][n:]
                    outcome=external_metrics(before,w.balance(),actual,law,context)
                    rows.append(dict(policy=name,case=i,stage=stage,family=c['family'],radius=c['radius'],budget=c['budget'],
                        phase=s['phase'],reason=s.get('reason'),probes=len(s['evidence']),**outcome))
                finally:r.close();w.close()
    cycles=[]
    for name in protocol['policies']:
        for i,c in enumerate(cases):
            part=[x for x in rows if x['policy']==name and x['case']==i]
            cycles.append(dict(policy=name,case=i,family=c['family'],radius=c['radius'],budget=c['budget'],
                all_actions=all(x['reward']>0 for x in part),reward=sum(x['reward'] for x in part),
                opportunity_gap=sum(x['opportunity_gap'] for x in part),resource_spent=sum(x['resource_spent'] for x in part),
                probes=sum(x['probes'] for x in part),breaches=sum(x['reserve_breach'] for x in part)))
    summary={name:dict(cycles=len(part),all_actions=sum(x['all_actions'] for x in part),
        reward=sum(x['reward'] for x in part),opportunity_gap=sum(x['opportunity_gap'] for x in part),
        resource_spent=sum(x['resource_spent'] for x in part),probes=sum(x['probes'] for x in part),breaches=sum(x['breaches'] for x in part))
        for name in protocol['policies'] for part in [[x for x in cycles if x['policy']==name]]}
    for filename,content in [('results.json',rows),('cycles.json',cycles),('summary.json',summary)]:
        (root/filename).write_text(json.dumps(content,indent=2),encoding='utf-8')
    return summary


if __name__=='__main__':
    root=Path(__file__).resolve().parent/'runs'/datetime.now(timezone.utc).strftime('stress-%Y%m%dT%H%M%S%fZ')
    print(json.dumps(run(root),indent=2));print(root)
