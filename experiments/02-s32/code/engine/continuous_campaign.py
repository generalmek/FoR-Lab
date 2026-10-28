"""Persistent resource accounting and a direct-measurement comparison.
The B2 control has the same safe probes, rewards, norm, action budget,
model store and synthesizer available, but chooses not to fit a model when
direct measurement suffices. This is a narrow task-matched control.
"""
import json
import random
from pathlib import Path
from datetime import datetime, timezone
from integrated_runtime import IntegratedRuntime
from native_incubator import NativeWorld


class ResourceWorld(NativeWorld):
    def __init__(self, path, law, context, initial=80):
        super().__init__(path, law, context)
        self.db.execute('CREATE TABLE IF NOT EXISTS resource_origin(id INTEGER PRIMARY KEY, amount INTEGER)')
        with self.db:
            self.db.execute('INSERT OR IGNORE INTO resource_origin VALUES(1,?)', (initial,))

    def balance(self):
        # Receipt IS the resource debit: no second write that can be lost or doubled.
        origin = self.db.execute('SELECT amount FROM resource_origin WHERE id=1').fetchone()[0]
        return origin - sum(json.loads(row[0])['physical'] for row in self.db.execute('SELECT result FROM receipts'))


class DirectControl(IntegratedRuntime):
    def choose_plan(self, s, models):
        observations = {e['probe']: e['value'] for e in s['evidence']}
        for u in sorted(s['actions'], key=lambda x: (-s['rewards'][str(x)], x)):
            probe = 'U'+str(u)
            if probe not in observations:
                return (('PROBE', probe), 'B2-direct-check') if s['budget'] >= 2 else (('HALT', None), 'budget')
            cost = observations[probe]
            if cost >= 0 and s['available']-cost >= s['reserve']:
                s['selected'], s['target'] = u, cost
                self.save(s)
                return (('ACT', u), 'B2-measured-admissible') if s['budget'] else (('HALT', None), 'budget')
        return ('HALT', None), 'B2-no-admissible-action'

    def permit(self, u):
        s = self.state()
        observed = {e['probe']:e['value'] for e in s['evidence']}
        if (s['phase']!='ACT' or s['budget']<1 or u!=s['selected'] or
                observed.get('U'+str(u))!=s['target'] or s['target']<0 or
                s['available']-s['target']<s['reserve']):
            return None
        return dict(u=u, target=s['target'], task_id=s['task_id'], generation=s['generation'],
                    context=s['context'], available=s['available'], reserve=s['reserve'])

    def candidates(self, s):
        # Prediction is a local measurement record; not generalized knowledge.
        return ({'direct': {e['probe']: e['value'] for e in s['evidence']}},)

    def predict_model(self, model, probe):
        return model['direct'].get(probe)

    def commit_complete_evidence(self, s):
        self.event(s, 'B2_LOCAL_EVIDENCE', evidence=s['evidence'][-1])


class RejectionCheckedRuntime(IntegratedRuntime):
    def choose_plan(self, s, models):
        if models:
            safe = [u for u in s['actions'] if all(0 <= self.predict_model(m,'U'+str(u)) <=
                    s['available']-s['reserve'] for m in models)]
            if not safe:
                seen={e['probe'] for e in s['evidence']}
                for u in sorted(s['actions'], key=lambda x:-s['rewards'][str(x)]):
                    probe='U'+str(u)
                    if probe not in seen and s['budget']>=2:
                        self.event(s,'CORE_CHECK_REJECTION',probe=probe,
                                   reason='old negative forecast may conceal feasible action')
                        return ('PROBE',probe),'verify-ground-for-refusal'
        return super().choose_plan(s,models)


def run_campaign(root, seeds=12, episodes=12):
    root.mkdir(parents=True, exist_ok=False)
    rng = random.Random(251025)
    cases = [[dict(context=rng.randrange(3), a=rng.randint(1,4), b=rng.randint(0,2),
                   q=rng.randint(0,2)) for _ in range(episodes)] for _ in range(seeds)]
    (root/'protocol.json').write_text(json.dumps(dict(cases=cases, initial=80, reserve=5,
        budget=16, rewards={'1':4,'2':10}, measurement_resource_cost=0,
        limitations='Exact safe measurements; serial simulator; seeded by developer, not independent blind test.'), indent=2), encoding='utf-8')
    rows=[]
    for name, cls in [('integrated',IntegratedRuntime), ('B2_direct',DirectControl),
                      ('rejection_checked',RejectionCheckedRuntime)]:
        for seed, sequence in enumerate(cases):
            for episode, case in enumerate(sequence):
                law=lambda u,v,c=case: c['b']+c['a']*u+c['q']*u*v
                w=ResourceWorld(root/f'{name}-{seed}-world.sqlite',law,case['context'])
                r=cls(root/f'{name}-{seed}-agent.sqlite')
                try:
                    before=w.balance()
                    if before<5: raise AssertionError('prior reserve breached')
                    r.start_integrated(case['context'],before,5)
                    s=r.run(w)
                    acted=s['phase']=='DONE'
                    feasible=[u for u in (1,2) if before-law(u,case['context'])>=5]
                    rows.append(dict(policy=name,seed=seed,episode=episode,before=before,after=w.balance(),
                        phase=s['phase'],probes=len(s['evidence']),reward=s['rewards'][str(s['selected'])] if acted else 0,
                        missed_feasible=not acted and bool(feasible),reserve_breach=w.balance()<5,
                        revised=s['native_gap']))
                finally: r.close();w.close()
    summary={name:dict(episodes=len(part),done=sum(x['phase']=='DONE' for x in part),
                      probes=sum(x['probes'] for x in part),reward=sum(x['reward'] for x in part),
                      missed_feasible=sum(x['missed_feasible'] for x in part),
                      breaches=sum(x['reserve_breach'] for x in part))
             for name in ('integrated','B2_direct','rejection_checked') for part in [[x for x in rows if x['policy']==name]]}
    (root/'results.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
    (root/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    return summary


if __name__=='__main__':
    root=Path(__file__).resolve().parent/'runs'/datetime.now(timezone.utc).strftime('continuous-%Y%m%dT%H%M%S%fZ')
    print(json.dumps(run_campaign(root),indent=2));print(root)
