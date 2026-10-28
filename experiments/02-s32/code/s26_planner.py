"""S26 single typed one-step planning language for probing and executable actions.

No host secret, world law, or file APIs. The same constraint solver scores
proposed typed operations across source, actuator diagnostics and action.
A restricted finite public language; NOT open concept generation.
"""
from math import isfinite

class NoPlan(ValueError):
    pass


def _valid_number(v):
    return type(v) in (int,float) and isfinite(v)


def choose(*, kind, available, required=(), forbidden=(), budget=None):
    """Uniform-cost, deterministically selected applicable single-step plan.

    Candidates expose their public preconditions as a list of signed facts.
    Required/forbidden facts make applicability domain-independent.
    Cost is the local operation cost, separate from the global budget.
    Returns a decision certificate containing the *chosen* operation.
    """
    if kind not in ('MEASURE','ACT'):raise ValueError('unsupported operation family')
    if budget is not None and (type(budget) is not int or budget<0):raise ValueError('invalid budget')
    required=set(required);forbidden=set(forbidden)
    plans=[]
    for item in available:
        if item.get('kind')!=kind:continue
        price=item.get('cost')
        facts=set(item.get('facts',[]))
        if type(price) is not int or price<1:continue
        if (budget is not None and price>budget) or (required-facts) or (forbidden&facts):continue
        role=item.get('role')
        if not isinstance(role,str) or not role:continue
        plans.append((price,role,item))
    if not plans:return None
    price,_,selected=min(plans,key=lambda x:(x[0],x[1]))
    return {'language':'S26/typed-ops-v1','kind':kind,'operation':selected['role'],
            'cost':price,'facts':sorted(set(selected['facts'])),
            'witness':selected.get('witness'),'control':selected.get('control'),
            'expected':selected.get('expected')}


def probe(stage,domain,requested_role,catalog,readings,budget=None):
    """Plan measurement by target quantity, independence and current stage."""
    entries=catalog.get(domain,[])
    target=next((p for p in entries if p['role']==requested_role),None)
    if not target or stage not in ('REPEAT','INDEPENDENT'):return None
    available=[]
    for p in entries:
        facts={'CAPABILITY','MEASURAND='+p['measurand'],'DOMAIN='+domain}
        if p['role']==requested_role:facts.add('SAME_ROLE')
        if p['role']!=requested_role and p.get('root') and target.get('root') and p['root']!=target['root']:
            facts.add('DIFFERENT_DECLARED_ROOT')
        available.append({'kind':'MEASURE','role':p['role'],'cost':p['cost'],
            'facts':list(facts),'witness':{'measurand':p['measurand'],'declared_root':p.get('root')}})
    needed=['CAPABILITY','MEASURAND='+target['measurand'],'DOMAIN='+domain,
            'SAME_ROLE' if stage=='REPEAT' else 'DIFFERENT_DECLARED_ROOT']
    result=choose(kind='MEASURE',available=available,required=needed,budget=budget)
    return (dict(next(p for p in entries if p['role']==result['operation'])) if result else None)


def validation(candidates,budget):
    """Plan scoped local validation using the same typed operator selector."""
    available=[]
    for p in candidates:
        available.append({'kind':'MEASURE','role':p['role'],'cost':p['cost'],
            'facts':['CAPABILITY','VALIDATE_ALTERNATIVE','DOMAIN=actuator'],
            'witness':{'declared_root':p.get('root'),'control':p['control']},
            'control':p['control']})
    chosen=choose(kind='MEASURE',available=available,
                  required=['VALIDATE_ALTERNATIVE','DOMAIN=actuator'],budget=budget)
    if not chosen:return None
    return next(dict(p) for p in candidates if p['role']==chosen['operation'])


def action(outputs,floor,*,scope_ok=True,permitted=True,budget=1):
    """Choose a measured, compass-admissible action; no extrapolation."""
    if not _valid_number(floor):raise ValueError('invalid compass threshold')
    available=[]
    for key,v in outputs.items():
        try:u=int(key)
        except (ValueError,TypeError):continue
        if type(u) is bool or u<1 or not _valid_number(v):continue
        facts={'OBSERVED','CONTROL='+str(u)}
        if v>floor:facts.add('COMPASS_OK')
        if scope_ok:facts.add('SCOPED')
        if permitted:facts.add('PERMITTED')
        available.append({'kind':'ACT','role':str(u).zfill(6),'cost':1,
                          'facts':sorted(facts),'control':u,'expected':v,
                          'witness':'observed-outputs'})
    chosen=choose(kind='ACT',available=available,
                  required=['OBSERVED','COMPASS_OK','SCOPED','PERMITTED'],budget=budget)
    return (chosen['control'],chosen['expected']) if chosen else None
