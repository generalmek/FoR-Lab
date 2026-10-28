"""Small declarative, costed method language: compose operations, don't hard-code sequences.

The facts are *agent-observed* process state, not receiver-hidden anomaly labels.
This module only plans; it never has a reference to the environment/world.
"""
from dataclasses import dataclass
from heapq import heappush, heappop

@dataclass(frozen=True)
class Op:
    name: str
    needs: frozenset[str]
    adds: frozenset[str]
    cost: int

# Three types of transformations: evidence acquisition, uncertainty treatment,
# and independent alternative construction. Their order follows dependencies.
OPERATORS = (
    Op('FRESH_REPEAT', frozenset({'contradiction'}), frozenset({'repeat_requested'}), 3),
    Op('ISOLATE_PERSISTENT_RESIDUAL', frozenset({'repeated','stable_residual'}), frozenset({'quarantined'}), 1),
    Op('ISOLATE_AMBIGUOUS_CONTROL', frozenset({'repeated','conflicting_residual'}), frozenset({'quarantined'}), 1),
    Op('PROPOSE_INDEPENDENT_CONTROL', frozenset({'quarantined','public_alternative'}), frozenset({'independent_candidate'}), 1),
    Op('REQUEST_LOCAL_VALIDATION', frozenset({'independent_candidate'}), frozenset({'validation_required'}), 3),
)

def compose(facts, goal, *, max_cost=20):
    """Uniform-cost symbolic search: return minimal applicable program or None.

    Avoid stubs that always return the one recipe: two different evidence states
    require different programs. No oracle, no mutation, no external IO.
    """
    if isinstance(facts, str):raise ValueError('facts must be iterable of atoms')
    start=frozenset(facts)
    if goal in start:return {'operators':[], 'cost':0,'facts':sorted(start),'expanded':0}
    agenda=[(0,(),start)]; best={start:0}; expanded=0
    while agenda:
        cost,path,state=heappop(agenda)
        if cost!=best[state]:continue
        expanded+=1
        if goal in state:return {'operators':list(path), 'cost':cost,'facts':sorted(state),'expanded':expanded}
        for op in OPERATORS:
            if op.needs<=state and not op.adds<=state:
                new=state|op.adds; nxt=cost+op.cost
                if nxt<=max_cost and nxt<best.get(new,float('inf')):
                    best[new]=nxt
                    heappush(agenda,(nxt,path+(op.name,),new))
    return None
