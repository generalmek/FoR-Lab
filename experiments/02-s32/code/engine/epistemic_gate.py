"""S11. A *local*, decision-relative sufficiency cycle, not a complete FoR Core.

No access to actual-world state inside the candidate. `world` is an execution
receiver; only its observed probe receipts are returned. Complete hypothesis
class is an assumption, deliberately challenged in the tests.
"""
from copy import deepcopy


class ProbeWorld:
    """Simulated receiver. Ground truth stays private; its public methods are probes/actions."""
    def __init__(self, probe_signals, action_outcomes, tag='fixture'):
        self._signals = dict(probe_signals)
        self._outcomes = dict(action_outcomes)
        self.tag = tag
        self.probes = []
        self.actions = []

    def measure(self, probe, operation_id):
        if probe not in self._signals:
            raise ValueError('probe not available')
        receipt = {'operation_id': operation_id, 'probe': probe,
                   'observation': self._signals[probe], 'source': 'simulated_receiver'}
        self.probes.append(deepcopy(receipt))
        return receipt

    def act(self, action, operation_id):
        if action not in self._outcomes:
            raise ValueError('action not available')
        receipt = {'operation_id': operation_id, 'action': action,
                   'outcome': self._outcomes[action], 'source': 'simulated_receiver'}
        self.actions.append(deepcopy(receipt))
        return receipt


def _consistent(hypothesis, evidence):
    return all(hypothesis['probes'].get(e['probe']) == e['observation'] for e in evidence)


def _common_safe(models, action_names, objective):
    if objective == 'safe':
        return [a for a in action_names if all(m['actions'][a] > 0 for m in models)]
    # For 'optimal', mere safety is not enough: the same action must maximize
    # the supplied outcome in every remaining model. This is a supplied goal.
    return [a for a in action_names if all(
        m['actions'][a] > 0 and m['actions'][a] == max(m['actions'].values())
        for m in models)]


def run_inquiry(hypotheses, probes, world, budget, *, session='s11', policy='sufficient',
                max_probes=10, objective='safe'):
    """Select and execute a virtual action, or stop with a distinct reason.

    Finite hypotheses, positive-outcome criterion and probe prices are externally
    defined experimental contracts. Returns recorded evidence and provenance.
    """
    if policy not in ('sufficient', 'always_disambiguate'):
        raise ValueError('invalid policy')
    if objective not in ('safe', 'optimal'):
        raise ValueError('invalid objective')
    if type(budget) is not int or budget < 0:
        raise ValueError('invalid budget')
    if not hypotheses or not isinstance(probes, dict) or len(hypotheses) > 64:
        raise ValueError('invalid hypotheses/probes')
    names = set(hypotheses[0]['actions'])
    if not names or any(set(m['actions']) != names or set(m['probes']) != set(probes) for m in hypotheses):
        raise ValueError('incomplete model contract')
    if any(type(price) is not int or price <= 0 for price in probes.values()):
        raise ValueError('invalid probe cost')
    evidence, trace, used = [], [], set()
    start_budget = budget
    action_names = sorted(names)
    def event(status, *, action=None, receipt=None, candidate_count=0):
        result = dict(status=status, action=action, receipt=receipt, budget_left=budget,
                      budget_spent=start_budget-budget, candidate_count=candidate_count,
                      evidence=deepcopy(evidence), trace=deepcopy(trace), policy=policy,
                      source_scope='finite_supplied_model_class', session=session, objective=objective)
        return result
    for iteration in range(max_probes + 1):
        models = [m for m in hypotheses if _consistent(m, evidence)]
        if not models:
            trace.append({'event': 'INSUFFICIENT', 'reason': 'all-hypotheses-contradicted'})
            return event('MODEL_CLASS_INADEQUATE')
        common = _common_safe(models, action_names, objective)
        if common and (policy == 'sufficient' or len(models) == 1):
            action = common[0]
            trace.append({'event': 'LOCAL_SUFFICIENT', 'action': action,
                          'models_remaining': [m['id'] for m in models],
                          'condition': ('common-positive-action' if objective=='safe' else 'common-optimal-action')})
            receipt = world.act(action, f'{session}:action:1')
            return event('SUFFICIENT_ACTION', action=action, receipt=receipt,
                         candidate_count=len(models))
        if not common and all(all(m['actions'][a] <= 0 for a in action_names) for m in models):
            trace.append({'event': 'STOP', 'reason': 'no-positive-outcome-in-any-model'})
            return event('NO_SAFE_ACTION', candidate_count=len(models))
        if iteration >= max_probes:
            return event('SEARCH_LIMIT', candidate_count=len(models))
        choices = []
        for name, cost in probes.items():
            if name in used:
                continue
            partitions = {}
            for m in models:
                key = m['probes'][name]
                partitions[key] = partitions.get(key, 0) + 1
            if len(partitions) > 1:
                choices.append((max(partitions.values()), cost, name))
        if not choices:
            trace.append({'event': 'INSUFFICIENT', 'reason': 'no-distinguishing-probe'})
            return event('UNIDENTIFIABLE', candidate_count=len(models))
        # Choose by worst-case remaining ambiguity; then cheaper probe.
        worst_case, price, probe = min(choices)
        if budget < price:
            affordable = [choice for choice in choices if choice[1] <= budget]
            if affordable:
                worst_case, price, probe = min(affordable)
            else:
                trace.append({'event': 'STOP', 'reason': 'no-affordable-distinguishing-probe'})
                return event('BUDGET_STOP', candidate_count=len(models))
        operation_id = f'{session}:probe:{len(evidence)+1}'
        receipt = world.measure(probe, operation_id)
        budget -= price
        used.add(probe)
        # The agent sees only receipt.observation, not world._signals/actions.
        evidence.append(dict(probe=probe, observation=receipt['observation'],
                             operation_id=receipt['operation_id'], receiver=receipt['source'],
                             price=price))
        trace.append({'event': 'DISTINGUISHING_PROBE', 'probe': probe,
                      'price': price, 'worst_case_remaining': worst_case,
                      'operation_id': operation_id})
    return event('SEARCH_LIMIT')
