"""S22 shared typed evidence graph, domain-agnostic procedure search and invalidation.
Only agent-observed evidence/receipts enter this kernel. No receiver or oracle reference.
"""
from dataclasses import dataclass
from heapq import heappush, heappop

@dataclass(frozen=True)
class Operation:
    name: str
    needs: frozenset
    adds: frozenset
    cost: int

# One language for sensor and actuator roles; the task role is an input binding.
OPERATIONS = (
    Operation('COMPARE_OBSERVATIONS', frozenset({'new_observation','prior_observation'}),frozenset({'comparison'}),1),
    Operation('CLASSIFY_CONFLICT',frozenset({'comparison','mismatch'}),frozenset({'contradiction'}),1),
    Operation('INVALIDATE_DEPENDENTS',frozenset({'contradiction'}),frozenset({'invalidation_required'}),1),
    Operation('FORM_DIFFERENTIAL_QUESTION',frozenset({'invalidation_required'}),frozenset({'research_question'}),1),
    Operation('RETAIN_CORROBORATION',frozenset({'comparison','agreement'}),frozenset({'corroborated'}),1),
)

def plan(facts,goal,max_cost=12):
    """Uniform-cost search; deterministic; no domain string or hidden world input."""
    initial=frozenset(facts)
    if goal in initial:return {'operations':[],'cost':0,'expanded':0}
    queue=[(0,(),initial)]; best={initial:0}; expanded=0
    while queue:
        cost,path,state=heappop(queue)
        if cost!=best[state]:continue
        expanded+=1
        if goal in state:return {'operations':list(path),'cost':cost,'expanded':expanded}
        for op in OPERATIONS:
            if op.needs<=state and not op.adds<=state:
                next_state=state|op.adds;total=cost+op.cost
                if total<=max_cost and total<best.get(next_state,float('inf')):
                    best[next_state]=total
                    heappush(queue,(total,path+(op.name,),next_state))
    return None


def valid_dependency_path(nodes,root):
    """Checks full transitive proof DAG with cycle/missing-node detection."""
    visiting=set();done=set()
    def check(key):
        if key in done:return True
        if key in visiting or key not in nodes:return False
        node=nodes[key]
        if not node.get('valid',False):return False
        visiting.add(key)
        ok=all(check(dep) for dep in node.get('depends',[]))
        visiting.remove(key)
        if ok:done.add(key)
        return ok
    return check(root)


def revoke(nodes,key,reason):
    """Same operation across domains; revokes all downstream causal dependents."""
    pending=[key];seen=set();revoked=[]
    while pending:
        k=pending.pop()
        if k in seen:continue
        seen.add(k)
        if k in nodes and nodes[k].get('valid',False):
            nodes[k]['valid']=False;nodes[k]['revocation_reason']=reason;revoked.append(k)
        pending.extend(n for n,node in nodes.items() if k in node.get('depends',()))
    return revoked


def compare_observations(old,new):
    """Overlapping measured intervals are consistent, disjoint are a discrepancy."""
    return abs(float(old['value'])-float(new['value']))<=float(old.get('radius',0))+float(new.get('radius',0))
