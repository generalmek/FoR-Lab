"""Bounded synthesis of measurement programs under an explicit linear sensor schema.
Research only: does not grant permission for an unmeasured physical action.
"""
import hashlib
import itertools
import json
from fractions import Fraction as F
from incubator_runtime import Runtime
from structure_runtime import StructureRuntime

def solve(vectors,values):
    if len(vectors)!=3:return None
    a=[[F(v) for v in row]+[F(y)] for row,y in zip(vectors,values)]
    for j in range(3):
        pivot=next((i for i in range(j,3) if a[i][j]),None)
        if pivot is None:return None
        a[j],a[pivot]=a[pivot],a[j]
        scale=a[j][j];a[j]=[v/scale for v in a[j]]
        for i in range(3):
            if i!=j:
                scale=a[i][j];a[i]=[x-scale*y for x,y in zip(a[i],a[j])]
    return tuple(str(row[-1]) for row in a)

def dot(vector,model):return sum(F(x)*F(y) for x,y in zip(vector,model))

def normalize(operations):
    if not 4<=len(operations)<=8:raise ValueError('need 4..8 measurement operations')
    if len({o['name'] for o in operations})!=len(operations):raise ValueError('duplicate name')
    clean=[]
    for o in operations:
        if len(o['vector'])!=3 or type(o['cost']) is not int or o['cost']<=0:raise ValueError('invalid measurement schema')
        v=[str(F(x)) for x in o['vector']]
        if not any(F(x) for x in v):raise ValueError('empty measurement')
        clean.append(dict(name=o['name'],vector=v,cost=o['cost']))
    if len({tuple(o['vector']) for o in clean})!=len(clean):raise ValueError('duplicate measurement vector')
    return sorted(clean,key=lambda o:(o['vector'],o['cost']))

def compile_program(ops,seen=(),solver='combinations'):
    """Exhaustive least additional measurement cost; fit/check sets disjoint."""
    source=itertools.combinations(range(len(ops)),3) if solver=='combinations' else itertools.permutations(range(len(ops)),3)
    best=None;examined=0
    for basis in source:
        examined+=1
        if solve([ops[i]['vector'] for i in basis],[0]*3) is None:continue
        for check in range(len(ops)):
            if check in basis or check in seen:continue
            ids=tuple(sorted(basis));cost=sum(ops[i]['cost'] for i in (*ids,check) if i not in seen)
            key=(cost,ids,check)
            if best is None or key<best:best=key
    if best is None:return None,examined
    return dict(cost=best[0],basis=list(best[1]),check=best[2]),examined

class MethodRuntime(StructureRuntime):
    def __init__(self,*args,use_method=True,solver='combinations',**kwargs):
        super().__init__(*args,**kwargs)
        if solver not in ('combinations','permutations'):raise ValueError('unknown solver')
        self.use_method,self.solver=use_method,solver
        self.db.execute('CREATE TABLE IF NOT EXISTS inquiry_methods(signature TEXT PRIMARY KEY,body TEXT)')
        self.db.commit()

    def start_research(self,operations,budget=12):
        ops=normalize(operations)
        signature=hashlib.sha256(json.dumps([(o['vector'],o['cost']) for o in ops]).encode()).hexdigest()
        Runtime.start(self,0,budget=budget)
        s=self.state();s.update(phase='RESEARCH',evidence=[],certified=False,scope=[],
            research=dict(ops=ops,signature=signature,observed={},prior=self.remembered(),
                          prior_refuted=False,plan=None,search_nodes=0,cache_hit=False))
        with self.db:self.save(s)

    def step(self,world,fail_at=None):
        if self.state()['phase']!='RESEARCH':return super().step(world,fail_at=fail_at)
        self.db.execute('BEGIN IMMEDIATE')
        try:
            s=self.state();r=s['research'];ops=r['ops'];seen={int(i) for i in r['observed']}
            if r['plan'] is None:
                cached=self.db.execute('SELECT body FROM inquiry_methods WHERE signature=?',(r['signature'],)).fetchone()
                if self.use_method and cached and not seen:
                    plan=json.loads(cached[0]);r['cache_hit']=True
                else:
                    plan,nodes=compile_program(ops,seen,self.solver);r['search_nodes']+=nodes
                if plan is None or plan['cost']>s['budget']:
                    s.update(phase='HALT',reason='UNIDENTIFIABLE_OR_BUDGET')
                    self.save(s);self.db.commit();return s
                r['plan']=plan
                self.event(s,'RESEARCH_PROGRAM',plan=plan,cache_hit=r['cache_hit'])
            plan=r['plan'];pending=[i for i in (*plan['basis'],plan['check']) if i not in seen]
            if pending:
                i=pending[0];op=ops[i]
                if op['cost']>s['budget']:raise RuntimeError('research budget inconsistency')
                if i==plan['check']:
                    basis=plan['basis']
                    fitted=solve([ops[j]['vector'] for j in basis],[r['observed'][str(j)] for j in basis])
                    r['precheck_model']=fitted
                    self.event(s,'RESEARCH_PREDICTION_BEFORE_CHECK',coefficients=fitted,
                               check=op['name'],prediction=str(dot(op['vector'],fitted)))
                value=str(F(world.measure_operation(op['name'])))
                s['budget']-=op['cost'];r['observed'][str(i)]=value
                self.event(s,'RESEARCH_OBSERVATION',name=op['name'],vector=op['vector'],value=value,cost=op['cost'])
                prior=r['prior']
                if prior and not r['prior_refuted'] and dot(op['vector'],list(prior)+['0']*(3-len(prior)))!=F(value):
                    r['prior_refuted']=True;r['plan']=None
                    self.event(s,'RESEARCH_PROGRAM_REOPENED',reason='prior_prediction_contradicted')
            else:
                basis=plan['basis'];check=plan['check']
                model=solve([ops[i]['vector'] for i in basis],[r['observed'][str(i)] for i in basis])
                if any(dot(ops[int(i)]['vector'],model)!=F(value) for i,value in r['observed'].items()):
                    s.update(phase='HALT',reason='INDEPENDENT_OBSERVATION_CONTRADICTION')
                else:
                    record=dict(coefficients=model,grammar='degree<=2; known linear measurement semantics',
                                fitting_operations=[ops[i] for i in basis],validation_operation=ops[check],
                                observations=r['observed'],signature=r['signature'])
                    self.db.execute('INSERT INTO expressions(task_id,body) VALUES(?,?)',(s['task_id'],json.dumps(record)))
                    if self.remembered()!=r['prior']:
                        self.db.execute("UPDATE beliefs SET version=version+1 WHERE name IN ('process','sensor')")
                    self.db.execute('UPDATE forecasts SET valid=0')
                    self.db.execute('INSERT INTO runtime_revisions(body) VALUES(?)',(json.dumps(record),))
                    # Cache applicability includes semantic vectors and costs, not names.
                    cached_plan=dict(plan,cost=sum(ops[i]['cost'] for i in (*basis,check)))
                    self.db.execute('INSERT OR REPLACE INTO inquiry_methods VALUES(?,?)',(r['signature'],json.dumps(cached_plan)))
                    self.event(s,'RESEARCH_MODEL_VALIDATED',record=record)
                    s.update(phase='DONE',reason='RESEARCH_ONLY_NO_ACTUATION')
            self.save(s);self.db.commit();return s
        except BaseException:self.db.rollback();raise
