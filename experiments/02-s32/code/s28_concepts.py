"""S28 bounded truth-functional concept induction from intervention receipts.

No XOR operator or named learned concept is supplied to this inducer. It composes
DNF using binary input literals and conjunction/disjunction. Finite three-bit
world means this does not establish open-world generalization or causal identity.
"""
from itertools import combinations,product,permutations
import json

def canonical(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))

def all_inputs(fields):
    return [dict(zip(fields,bits)) for bits in product((0,1),repeat=len(fields))]

def evaluate(clauses,values):
    return int(any(all(int(values[k])==v for k,v in clause.items()) for clause in clauses))

def induce(fields,observations,*,max_clauses=4):
    """Minimum description length exact DNF, 1..3 literals per clause.

    More general clauses beat memorizing all individual positive assignments.
    """
    fields=tuple(sorted(fields))
    if len(fields)!=3 or len(set(fields))!=3:raise ValueError('S28 expects three distinct binary features')
    data={}
    for record in observations:
        key=tuple(record['input'][f] for f in fields)
        if any(x not in (0,1) or type(x)!=int for x in key):raise ValueError('nonbinary input')
        y=record['value']
        if type(y)!=int or y not in (0,1):raise ValueError('nonbinary response')
        if key in data and data[key]!=y:raise ValueError('inconsistent observations')
        data[key]=y
    if len(data)!=2**len(fields):raise ValueError('insufficient coverage')
    positives={x for x,y in data.items() if y};negative={x for x,y in data.items() if not y}
    if not positives:return {'clauses':[],'cost':0,'expression':'FALSE'}
    if not negative:return {'clauses':[{}],'cost':1,'expression':'TRUE'}
    choices=[]
    for n in range(1,len(fields)+1):
        for selected in combinations(fields,n):
            for bits in product((0,1),repeat=n):
                clause=dict(zip(selected,bits))
                covers={x for x in data if all(x[fields.index(k)]==v for k,v in clause.items())}
                if covers and not covers&negative:
                    choices.append((clause,covers))
    best=None
    for n in range(1,max_clauses+1):
        for group in combinations(range(len(choices)),n):
            covered=set().union(*(choices[i][1] for i in group))
            if covered!=positives:continue
            clauses=[choices[i][0] for i in group]
            cost=sum(len(c) for c in clauses)+len(clauses)
            cand=(cost,len(group),canonical(clauses),clauses)
            if best is None or cand[:3]<best[:3]:best=cand
        if best is not None and best[1]==n:break
    if best is None:raise ValueError('concept grammar insufficient')
    return {'clauses':best[3],'cost':best[0],'expression':'DNF'}

def atomic_expressible(fields,observations):
    """Does one known input literal or constant already predict all observations?"""
    vals=[x['value'] for x in observations]
    if len(set(vals))==1:return True
    return any(all(x['value']==x['input'][field] for x in observations) or
               all(x['value']==1-x['input'][field] for x in observations)
               for field in fields)

def rebindings(source_clauses,source_fields,target_fields):
    """Distinct prediction functions, not semantic role oracles."""
    source_fields=tuple(sorted(source_fields));target_fields=tuple(sorted(target_fields))
    if len(source_fields)!=len(target_fields):return []
    points=all_inputs(target_fields)
    predicted={}
    for target_permutation in permutations(target_fields):
        mapping=dict(zip(source_fields,target_permutation))
        clauses=[{mapping[k]:v for k,v in clause.items()} for clause in source_clauses]
        signature=tuple(evaluate(clauses,x) for x in points)
        predicted.setdefault(signature,{'clauses':clauses,'possible_mappings':[]})['possible_mappings'].append(mapping)
    return list(predicted.values())

def choose_probe(hypotheses,points,used):
    available=[x for x in points if canonical(x) not in used]
    if not available:return None
    if len(hypotheses)==1:return available[0]
    def quality(point):
        ones=sum(evaluate(h['clauses'],point) for h in hypotheses)
        return (min(ones,len(hypotheses)-ones),-abs(2*ones-len(hypotheses)))
    return max(available,key=lambda x:(quality(x),tuple(-x[k] for k in sorted(x))))
