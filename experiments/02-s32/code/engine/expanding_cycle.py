"""Evidence-triggered bounded grammar expansion, not open-ended semantics."""
import itertools
import json
from budget_revision_audit import BudgetAwareCycle
from full_cycle import HYPOTHESES, PROBES, VALIDATION
from native_incubator import TRAIN, CHECK
from uncertain_runtime import UncertainRuntime


def extensions():
    # Multiplication compositions of named inputs; meanings and depth are supplied.
    for degree in (1, 2, 3):
        for variables in itertools.combinations_with_replacement('uv', degree):
            powers = (variables.count('u'), variables.count('v'))
            if powers in ((1, 0), (1, 1)):
                continue
            for base in HYPOTHESES:
                for coefficient in (1, 2):
                    yield (*base, coefficient, *powers)


class ExpandingCycle(BudgetAwareCycle):
    def start_cycle(self, world, mode='full', budget=20, search_limit=1120, strategy='adaptive'):
        if strategy not in ('adaptive', 'wide', 'fixed') or search_limit < 0:
            raise ValueError('invalid search contract')
        super().start_cycle(world, mode, budget)
        s = self.state()
        s.update(search_limit=search_limit, search_used=0, strategy=strategy,
                 expansions=0, search_status=None, validation_epoch=0)
        if strategy == 'wide' and not s['transferred']:
            generated = list(extensions())
            if len(generated) > search_limit:
                s.update(phase='HALT', reason='SEARCH_BUDGET_EXHAUSTED')
            else:
                s['pool'] = list(HYPOTHESES) + generated
                s['search_used'] = len(generated)
        with self.db:
            self.save(s)

    def predict_model(self, model, probe):
        if probe.startswith('T'):
            u, v = TRAIN[int(probe[1:])]
        elif probe.startswith('V'):
            u, v = CHECK[int(probe[1:])]
        else:
            u, v = int(probe[1:]), self.state()['context']
        b, a, q = model[:3]
        return b + a*u + q*u*v + (model[3]*u**model[4]*v**model[5] if len(model) == 6 else 0)

    def choose_probe(self, s, models, probes):
        # Exact interval-compatible minimax, using sorted predictions rather than
        # enumerating every possible sensor reading for every candidate.
        seen = {e['probe'] for e in s['evidence'] if self.fresh(s, e)}
        options = [p for p in probes if p not in seen]
        if not options:
            return None
        def score(p):
            ys = sorted(self.predict_model(m, p) for m in models)
            left = worst = 0
            for right, y in enumerate(ys):
                while y - ys[left] > 2*s['sensor_bound']:
                    left += 1
                worst = max(worst, right-left+1)
            return worst, p
        return min(options, key=score)

    def commit_complete_evidence(self, s):
        UncertainRuntime.commit_complete_evidence(self, s)
        models = self.candidates(s)
        reset = False
        if not models:
            reset = True
            s.update(verified=False, revision=True, validation_probe=None, worldview_saved=False)
            s['validation_epoch'] += 1
            models = tuple(m for m in HYPOTHESES if self.consistent(m, s))
            self.event(s, 'WORLDVIEW_CONTRADICTION', remaining=len(models))
            if not models and s['strategy'] != 'fixed':
                self.event(s, 'SELF_GENERATED_QUESTION', question='Can a bounded composition explain the contradiction?',
                           cause=s['evidence'][-1], remaining_search=s['search_limit']-s['search_used'])
                survivors = []
                exhausted = False
                for m in extensions():
                    if s['search_used'] >= s['search_limit']:
                        exhausted = True
                        break
                    s['search_used'] += 1
                    if self.consistent(m, s):
                        survivors.append(m)
                # A partial search is not a completed model-space audit.
                s['search_status'] = 'SEARCH_BUDGET_EXHAUSTED' if exhausted else 'BOUNDED_SEARCH_COMPLETE'
                models = () if exhausted else tuple(survivors)
                s['expansions'] += 1
                self.event(s, 'GRAMMAR_SEARCH', status=s['search_status'], evaluated=s['search_used'],
                           survivors=len(survivors), scope='given multiplication grammar, depth<=3')
        s['pool'] = models
        # Never validate using the very observation that triggered expansion.
        if models and not reset and s['evidence'][-1]['probe'] == s.get('validation_probe'):
            s['verified'] = True
            record = dict(models=models, evidence=s['evidence'], task=s['task_id'],
                          scope='bounded expanded grammar; fresh transfer check required')
            self.db.execute('INSERT INTO worldview_sets(body) VALUES(?)', (json.dumps(record),))
            self.db.execute("UPDATE beliefs SET version=version+1 WHERE name='process'")
            self.db.execute('UPDATE forecasts SET valid=0')
            s['worldview_saved'] = True
            self.event(s, 'WORLDVIEW_REVISED', count=len(models), record=record)

    def choose_plan(self, s, models):
        if s.get('search_status') == 'SEARCH_BUDGET_EXHAUSTED':
            s['resource_stop'] = 'SEARCH_BUDGET_EXHAUSTED'
            return ('HALT', None), 'search-incomplete-not-out-of-class'
        return super().choose_plan(s, models)
