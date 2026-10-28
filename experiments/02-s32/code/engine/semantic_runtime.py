"""Untrusted external proposal -> bounded AST -> observation check -> scoped memory.
The external language model is NOT the agent's independently learned intelligence.
No eval, subprocess, imports, file access or physical permissions in the AST.
"""
import hashlib
import json
from incubator_runtime import Runtime
from method_runtime import MethodRuntime

def unique_pairs(pairs):
    out={}
    for k,v in pairs:
        if k in out:raise ValueError('duplicate JSON key')
        out[k]=v
    return out

def parse_proposal(raw):
    if not isinstance(raw,str) or len(raw)>12000:raise ValueError('proposal too large')
    data=json.loads(raw,object_pairs_hook=unique_pairs)
    if not isinstance(data,dict) or set(data)!={'expression','claim'} or data['claim']!='hypothesis':
        raise ValueError('expected hypothesis envelope')
    count=0
    def check(node,depth=0):
        nonlocal count
        count+=1
        if count>64 or depth>12 or not isinstance(node,dict):raise ValueError('AST limits')
        if set(node)=={'const'}:
            if type(node['const']) is not int or abs(node['const'])>20:raise ValueError('invalid constant')
        elif set(node)=={'var'}:
            if node['var'] not in ('u','v'):raise ValueError('unknown input')
        elif set(node)=={'op','left','right'} and node['op'] in ('add','mul'):
            check(node['left'],depth+1);check(node['right'],depth+1)
        else:raise ValueError('unsupported AST node')
    check(data['expression'])
    return data['expression']

def evaluate_ast(node,point):
    if set(point)!={'u','v'} or any(type(v) is not int or abs(v)>100 for v in point.values()):
        raise ValueError('invalid input domain')
    def visit(n):
        if 'const' in n:return n['const']
        if 'var' in n:return point[n['var']]
        a,b=visit(n['left']),visit(n['right'])
        value=a+b if n['op']=='add' else a*b
        if abs(value)>10**12:raise ValueError('numeric limit')
        return value
    return visit(node)

class SemanticRuntime(MethodRuntime):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.db.execute('CREATE TABLE IF NOT EXISTS external_proposals(id INTEGER PRIMARY KEY,body TEXT,status TEXT)')
        self.db.execute('CREATE TABLE IF NOT EXISTS semantic_models(id INTEGER PRIMARY KEY,body TEXT)')
        self.db.commit()

    def start_proposal(self,raw,source,training,validation,budget=6):
        points=[dict(u=p['u'],v=p['v']) for p in validation]
        if len(points)<2 or len({(p['u'],p['v']) for p in points})!=len(points):raise ValueError('distinct checks required')
        if {(p['u'],p['v']) for p in points}&{(p['u'],p['v']) for p in training}:raise ValueError('validation overlaps training')
        Runtime.start(self,0,budget=budget)
        s=self.state();s.update(phase='SEMANTIC',certified=False,scope=[],evidence=[])
        record=dict(raw=raw,sha256=hashlib.sha256(raw.encode()).hexdigest(),source=source,task_id=s['task_id'])
        with self.db:
            pid=self.db.execute('INSERT INTO external_proposals(body,status) VALUES(?,?)',(json.dumps(record),'PROPOSED')).lastrowid
            try:
                ast=parse_proposal(raw)
                for p in points:evaluate_ast(ast,p)
                if any(evaluate_ast(ast,dict(u=p['u'],v=p['v']))!=p['y'] for p in training):
                    raise ValueError('training observations contradicted')
                s['semantic']=dict(proposal_id=pid,ast=ast,checks=points,index=0,source=source)
            except (ValueError,TypeError,KeyError,RecursionError) as error:
                s.update(phase='HALT',reason='PROPOSAL_REJECTED')
                self.db.execute('UPDATE external_proposals SET status=? WHERE id=?',('REJECTED',pid))
                self.event(s,'PROPOSAL_REJECTED',proposal_id=pid,detail=str(error))
            self.save(s)
        return self.state()

    def step(self,world,fail_at=None):
        if self.state()['phase']!='SEMANTIC':return super().step(world,fail_at=fail_at)
        self.db.execute('BEGIN IMMEDIATE')
        try:
            s=self.state();m=s['semantic'];pid=m['proposal_id']
            if m['index']==len(m['checks']):
                record=dict(proposal_id=pid,ast=m['ast'],source=m['source'],evidence=s['evidence'],
                            qualification='consistent with checked points only; not a global certificate')
                self.db.execute('INSERT INTO semantic_models(body) VALUES(?)',(json.dumps(record),))
                self.db.execute('UPDATE external_proposals SET status=? WHERE id=?',('CHECKED',pid))
                self.event(s,'EXTERNAL_HYPOTHESIS_CHECKED',record=record)
                s.update(phase='DONE',reason='SCOPED_PREDICTOR_ONLY_NO_ACTUATION')
            elif s['budget']<1:
                s.update(phase='HALT',reason='VALIDATION_BUDGET_EXHAUSTED')
                self.db.execute('UPDATE external_proposals SET status=? WHERE id=?',('INCOMPLETE',pid))
            else:
                point=m['checks'][m['index']];prediction=evaluate_ast(m['ast'],point)
                self.event(s,'PREDICTION_BEFORE_OBSERVATION',point=point,prediction=prediction)
                observed=world.observe(point)
                if type(observed) is not int:raise ValueError('observation contract requires integer')
                s['budget']-=1;m['index']+=1
                s['evidence'].append(dict(point=point,prediction=prediction,observed=observed))
                if prediction!=observed:
                    s.update(phase='HALT',reason='EXTERNAL_HYPOTHESIS_FALSIFIED')
                    self.db.execute('UPDATE external_proposals SET status=? WHERE id=?',('FALSIFIED',pid))
                    self.event(s,'EXTERNAL_HYPOTHESIS_FALSIFIED',evidence=s['evidence'][-1])
            self.save(s);self.db.commit();return s
        except BaseException:self.db.rollback();raise
