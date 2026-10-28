"""Four-component operational subset. Resource preservation is a GIVEN norm,
not a derivation of the Compass or evidence of consciousness.
Measurements are safe simulator queries; their operation budget is separate
from the resource consumed by an irreversible action.
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from native_incubator import NativeIncubator, NativeWorld


class IntegratedRuntime(NativeIncubator):
    def start_integrated(self, context, available, reserve, rewards=None,
                         budget=16, compass=True, core=True, alternatives=True):
        if not 0 <= reserve <= available:
            raise ValueError('invalid resource bounds')
        self.start_native(0, context, budget)
        s = self.state()
        s.update(available=available, reserve=reserve,
                 rewards=rewards or {'1': 4, '2': 10}, compass=compass,
                 core=core, alternatives=alternatives, selected=None)
        with self.db:
            self.save(s)
            self.event(s, 'NORM_DECLARED', reserve=reserve,
                       provenance='experimenter-given viability proxy')

    def choose_plan(self, s, models):
        if models:
            options = []
            for u in s['actions']:
                costs = [self.predict_model(m, 'U'+str(u)) for m in models]
                remaining = s['available'] - max(costs)
                options.append(dict(u=u, cost=max(costs), remaining=remaining,
                                    reward=s['rewards'][str(u)],
                                    admissible=min(costs) >= 0 and
                                    (not s['compass'] or remaining >= s['reserve'])))
            self.event(s, 'ALTERNATIVES_FORECAST', options=options)
            ranked = sorted(options, key=lambda x: (-x['reward'], x['cost'], x['u']))
            if not s['alternatives']:
                ranked = ranked[:1]
            chosen = next((x for x in ranked if x['admissible']), None)
            if chosen is None:
                self.event(s, 'NO_ADMISSIBLE_ACTION')
                return ('HALT', None), 'no-known-admissible-action'
            s['target'], s['selected'] = chosen['cost'], chosen['u']
            # Save before superclass prediction reads task state.
            self.save(s)
            probe = 'U'+str(chosen['u'])
            if any(e['probe'] == probe for e in s['evidence']):
                return (('ACT', chosen['u']), 'checked-admissible-option') if s['budget'] >= 1 else (('HALT', None), 'budget')
            return (('PROBE', probe), 'verify-current-consequence') if s['budget'] >= 2 else (('HALT', None), 'budget')
        if not s['core']:
            return ('HALT', None), 'inquiry-disabled'
        self.event(s, 'CORE_GAP', question='What resource consequence follows each action in this context?')
        return super().choose_plan(s, models)

    def permit(self, u):
        permit = super().permit(u)
        s = self.state()
        if not permit or u != s['selected'] or s['target'] < 0:
            return None
        if s['compass'] and s['available'] - s['target'] < s['reserve']:
            return None
        return dict(permit, available=s['available'], reserve=s['reserve'], compass=s['compass'])


def campaign(root):
    root.mkdir(parents=True, exist_ok=False)
    rows = []
    for policy in ('full', 'no_compass', 'no_core', 'no_alternatives', 'no_memory'):
        for index, (context, law) in enumerate(((1, lambda u,v:1+2*u+u*v),
                                              (0, lambda u,v:1+2*u+u*v),
                                              (0, lambda u,v:1+4*u+u*v))):
            db = root / (policy + (str(index) if policy == 'no_memory' else '') + '.sqlite')
            r = IntegratedRuntime(db)
            w = NativeWorld(root / (policy+str(index)+'-world.sqlite'), law, context)
            try:
                r.start_integrated(context, 10, 5, compass=policy!='no_compass',
                                   core=policy!='no_core', alternatives=policy!='no_alternatives')
                s = r.run(w)
                effects = [json.loads(x[0]) for x in w.db.execute('SELECT result FROM receipts')]
                consumed = sum(x['physical'] for x in effects)
                rows.append(dict(policy=policy, episode=index, phase=s['phase'],
                                 action=s['selected'] if effects else None,
                                 probes=len(s['evidence']), remaining=10-consumed,
                                 reserve_breach=10-consumed<5, revised=s['native_gap']))
            finally:
                r.close(); w.close()
    (root/'results.json').write_text(json.dumps(rows, indent=2), encoding='utf-8')
    return rows


if __name__ == '__main__':
    root = Path(__file__).resolve().parent/'runs'/datetime.now(timezone.utc).strftime('integrated-%Y%m%dT%H%M%S%fZ')
    for row in campaign(root):
        print(json.dumps(row), flush=True)
    print(root)
