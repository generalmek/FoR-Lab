"""Locally generated hypotheses, persistent learning and guarded action.
No browser, network, LLM, saved Sol response or external proposal is read.
Bounded sparse polynomial grammar, not an implementation of full Reason.
"""
import argparse
import itertools
import json
from fractions import Fraction as F
from pathlib import Path
from datetime import datetime,timezone
from durable_runtime import DurableRuntime,ReceiptWorkshop
from semantic_runtime import evaluate_ast,parse_proposal

TRAIN=((0,0),(1,0),(0,1),(1,1),(2,0),(0,2))
CHECK=((3,0),(0,3),(2,2))

def fit(rows,ys):
    a=[[F(x) for x in row]+[F(y)] for row,y in zip(rows,ys)];n=len(rows[0]);pivot=0
    for col in range(n):
        k=next((i for i in range(pivot,len(a)) if a[i][col]),None)
        if k is None:return None
        a[pivot],a[k]=a[k],a[pivot];scale=a[pivot][col];a[pivot]=[v/scale for v in a[pivot]]
        for i in range(len(a)):
            if i!=pivot:
                scale=a[i][col];a[i]=[x-scale*y for x,y in zip(a[i],a[pivot])]
        pivot+=1
    if any(all(v==0 for v in row[:-1]) and row[-1]!=0 for row in a):return None
    coeff=[a[i][-1] for i in range(n)]
    return [int(c) for c in coeff] if all(c.denominator==1 and abs(c)<=20 for c in coeff) else None

def synthesize(observations):
    features=[()] + [(x,) for x in ('u','v')] + list(itertools.combinations_with_replacement(('u','v'),2))
    def value(feature,p):
        out=1
        for variable in feature:out*=p[variable]
        return out
    searched=0
    for size in range(1,5):
        for subset in itertools.combinations(features,size):
            searched+=1
            coefficients=fit([[value(f,p) for f in subset] for p in observations],[p['y'] for p in observations])
            if coefficients is None:continue
            terms=[]
            for c,feature in zip(coefficients,subset):
                if not c:continue
                term={'const':c}
                for variable in feature:term=dict(op='mul',left=term,right={'var':variable})
                terms.append(term)
            ast=terms[0] if terms else {'const':0}
            for term in terms[1:]:ast=dict(op='add',left=ast,right=term)
            raw=json.dumps(dict(expression=ast,claim='hypothesis'))
            return parse_proposal(raw),searched
    return None,searched

class NativeIncubator(DurableRuntime):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.db.execute('CREATE TABLE IF NOT EXISTS native_models(id INTEGER PRIMARY KEY,task_id INTEGER,body TEXT)')
        self.db.commit()

    def start_native(self,target,context,budget=16):
        if type(context) is not int or abs(context)>100:raise ValueError('invalid context')
        self.start_decision(target,budget)
        s=self.state();s.update(context=context,native_candidate=None,native_search_done=False,native_stored=False,native_gap=False)
        with self.db:self.save(s)

    def remembered(self):
        row=self.db.execute('SELECT body FROM native_models ORDER BY id DESC LIMIT 1').fetchone()
        return json.loads(row[0])['ast'] if row else None

    def point(self,probe):
        if probe.startswith('T'):u,v=TRAIN[int(probe[1:])]
        elif probe.startswith('V'):u,v=CHECK[int(probe[1:])]
        else:u,v=int(probe[1:]),self.state()['context']
        return dict(u=u,v=v)

    def predict_model(self,model,probe):return evaluate_ast(model,self.point(probe))

    def candidates(self,s):
        seen={e['probe'] for e in s['evidence']}
        candidate=s.get('native_candidate')
        if candidate and all('V'+str(i) in seen for i in range(len(CHECK))) and all(
                self.predict_model(candidate,e['probe'])==e['value'] for e in s['evidence']):return (candidate,)
        old=self.remembered()
        if old and all(self.predict_model(old,e['probe'])==e['value'] for e in s['evidence']):return (old,)
        return ()

    def permit(self,u):
        s=self.state();models=self.candidates(s)
        if s['phase']!='ACT' or s['budget']<1 or u not in s['actions'] or not models:return None
        if not any(e['probe']=='U'+str(u) for e in s['evidence']):return None
        if not all(self.predict_model(m,'U'+str(u))==s['target'] for m in models):return None
        return dict(u=u,target=s['target'],context=s['context'],task_id=s['task_id'],generation=s['generation'],
                    basis_versions={k:v[1] for k,v in self.beliefs().items()})

    def choose_plan(self,s,models):
        seen={e['probe'] for e in s['evidence']}
        action=next((u for u in s['actions'] if models and all(self.predict_model(m,'U'+str(u))==s['target'] for m in models)),None)
        if action is not None:
            if 'U'+str(action) in seen and s['budget']>=1:return ('ACT',action),'native-checked-model'
            if s['budget']>=2:return ('PROBE','U'+str(action)),'fresh-action-check'
        if s['budget']<2:return ('HALT',None),'insufficient-budget'
        for i in range(len(TRAIN)):
            if 'T'+str(i) not in seen:return ('PROBE','T'+str(i)),'collect-for-native-synthesis'
        if not s['native_candidate']:return ('HALT',None),'no-hypothesis-in-bounded-grammar'
        if any(self.predict_model(s['native_candidate'],e['probe'])!=e['value'] for e in s['evidence']):
            return ('HALT',None),'native-hypothesis-falsified'
        for i in range(len(CHECK)):
            if 'V'+str(i) not in seen:return ('PROBE','V'+str(i)),'check-unseen-point'
        return ('HALT',None),'no-action-for-target-in-checked-model'

    def commit_complete_evidence(self,s):
        e={x['probe']:x['value'] for x in s['evidence']}
        old=self.remembered()
        mismatch=next((x for x in s['evidence'] if old and self.predict_model(old,x['probe'])!=x['value']),None)
        if mismatch and not s['native_gap']:
            s['native_gap']=True
            self.event(s,'NATIVE_MODEL_CONTRADICTION',probe=mismatch['probe'],observed=mismatch['value'],
                       predicted=self.predict_model(old,mismatch['probe']))
        if all('T'+str(i) in e for i in range(len(TRAIN))) and not s['native_search_done']:
            observations=[dict(u=u,v=v,y=e['T'+str(i)]) for i,(u,v) in enumerate(TRAIN)]
            ast,count=synthesize(observations)
            s.update(native_candidate=ast,native_search_done=True)
            self.event(s,'NATIVE_HYPOTHESIS',ast=ast,search_nodes=count,training=observations)
        ast=s['native_candidate']
        if ast and not s['native_stored'] and all('V'+str(i) in e for i in range(len(CHECK))) and all(
                self.predict_model(ast,p)==y for p,y in e.items()):
            record=dict(ast=ast,source='internal sparse symbolic synthesis',evidence=s['evidence'],
                        scope='checked points in declared polynomial grammar')
            self.db.execute('INSERT INTO native_models(task_id,body) VALUES(?,?)',(s['task_id'],json.dumps(record)))
            self.db.execute("UPDATE beliefs SET version=version+1 WHERE name='process'")
            self.db.execute('UPDATE forecasts SET valid=0');s['native_stored']=True
            self.event(s,'NATIVE_MODEL_STORED',record=record)

    def step(self,world,fail_at=None):
        if self.state()['phase'] not in ('IDLE','DONE','HALT') and world.context!=self.state().get('context'):
            raise ValueError('receiver context differs from task')
        return super().step(world,fail_at=fail_at)

class NativeWorld(ReceiptWorkshop):
    def __init__(self,path,law,context):super().__init__(path,bias=0);self.law,self.context=law,context
    def physical(self,u):return self.law(u,self.context)
    def measure(self,p):
        if p.startswith('T'):return self.law(*TRAIN[int(p[1:])])
        if p.startswith('V'):return self.law(*CHECK[int(p[1:])])
        return self.physical(int(p[1:]))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output');args=parser.parse_args()
    root=Path(args.output) if args.output else Path(__file__).resolve().parent/'runs'/datetime.now(timezone.utc).strftime('native-%Y%m%dT%H%M%S%fZ')
    root.mkdir(parents=True,exist_ok=False)
    rows=[]
    # This harness owns hidden laws. Agent receives goals, context, and observations only.
    episodes=[('learn',lambda u,v:-3+7*u+2*u*v,1,15),
              ('new_context',lambda u,v:-3+7*u+2*u*v,3,23),
              ('hidden_change',lambda u,v:4+2*u+5*u*v,3,38),
              ('transfer_again',lambda u,v:4+2*u+5*u*v,2,28),
              ('outside_grammar',lambda u,v:1+u*u*u+v,1,10)]
    print('FoR-Lab NATIVE INCUBATOR | NO EXTERNAL MODEL AT RUNTIME',flush=True)
    for name,law,context,target in episodes:
        r=NativeIncubator(root/'agent.sqlite');w=NativeWorld(root/'receiver.sqlite',law,context)
        r.start_native(target,context)
        before=w.db.execute('SELECT COUNT(*) FROM receipts').fetchone()[0]
        state=r.run(w)
        effects=[json.loads(x[0]) for x in w.db.execute('SELECT result FROM receipts ORDER BY rowid')][before:]
        row=dict(episode=name,phase=state['phase'],probes=len(state['evidence']),
                 learned=state['native_stored'],success=bool(effects) and all(x['physical']==target for x in effects),
                 harm=sum(x['harm'] for x in effects),model_count=r.db.execute('SELECT COUNT(*) FROM native_models').fetchone()[0])
        rows.append(row);print(json.dumps(row),flush=True);r.close();w.close()
    (root/'results.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
    print('Research prototype; consciousness and full Reason NOT established.');print(root)
if __name__=='__main__':main()
