"""S28 bounded concept learning and active role re-binding in S27 agent DB.

Host physical truth stays outside the agent state. No filesystem/tool access is
exposed to the candidate; only predeclared simulator measurements are allowed.
"""
import json,sqlite3,hashlib
from pathlib import Path
from s27_integrated import S27Unified
from s28_concepts import (canonical,all_inputs,evaluate,induce,atomic_expressible,
                          rebindings,choose_probe)
from s22_semantic_kernel import valid_dependency_path,revoke

class S28World:
    def __init__(self,path,fields,binding,law,*,anomaly=None):
        self.db=sqlite3.connect(str(path))
        fields=tuple(sorted(fields))
        if len(fields)!=3 or len(set(fields))!=3:raise ValueError('three public fields required')
        if set(binding)!={'a','b','c'} or set(binding.values())!=set(fields):raise ValueError('invalid private role binding')
        if law not in ('xor','and_not','xor_and_c'):raise ValueError('unsupported experimenter-only law')
        self.fields=fields
        self.world_tag=hashlib.sha256(str(Path(path).resolve()).encode('utf8')).hexdigest()[:16]
        self._private={'binding':binding,'law':law,'anomaly':anomaly,'fields':fields}
        self.db.execute('CREATE TABLE IF NOT EXISTS world_contract(id INTEGER PRIMARY KEY,body TEXT)')
        self.db.execute('CREATE TABLE IF NOT EXISTS world_readings(id TEXT PRIMARY KEY,input TEXT NOT NULL,value INTEGER NOT NULL)')
        prior=self.db.execute('SELECT body FROM world_contract WHERE id=1').fetchone()
        if prior and prior[0]!=canonical(self._private):raise ValueError('private host contract changed on restart')
        if not prior:
            with self.db:self.db.execute('INSERT INTO world_contract VALUES(1,?)',(canonical(self._private),))
    def observe(self,receipt_id,assignment):
        if set(assignment)!=set(self.fields) or any(type(x)!=int or x not in (0,1) for x in assignment.values()):
            raise ValueError('intervention not in public grammar')
        target=canonical(assignment)
        row=self.db.execute('SELECT input,value FROM world_readings WHERE id=?',(receipt_id,)).fetchone()
        if row:
            if row[0]!=target:raise ValueError('receipt id reused with different intervention')
            return row[1]
        b=self._private['binding']; a=assignment[b['a']]; bb=assignment[b['b']];c=assignment[b['c']]
        law=self._private['law']
        value=(a^bb) if law=='xor' else (int(bool(a) and not bb) if law=='and_not' else int(bool(a^bb) and bool(c)))
        anomaly=self._private['anomaly']
        if anomaly and all(assignment.get(k)==v for k,v in anomaly.items()):value=1-value
        with self.db:self.db.execute('INSERT INTO world_readings VALUES(?,?,?)',(receipt_id,target,value))
        return value
    def count(self):return self.db.execute('SELECT COUNT(*) FROM world_readings').fetchone()[0]
    def truth_audit(self):return {'private':self._private,'receipts':self.count()}
    def close(self):self.db.close()

class S28Unified(S27Unified):
    def __init__(self,*args,constructor_enabled=True,**kwargs):
        if type(constructor_enabled)!=bool:raise ValueError('bool required')
        self._constructor_enabled=constructor_enabled
        super().__init__(*args,**kwargs)
        try:
            self.conn.execute('CREATE TABLE IF NOT EXISTS s28_runs (id TEXT PRIMARY KEY,contract TEXT,record TEXT)')
            self.conn.execute('CREATE TABLE IF NOT EXISTS s28_challenges(id TEXT PRIMARY KEY,contract TEXT,record TEXT)')
            s=self.state();contract={'constructor':constructor_enabled,'language':'S28/boolean-DNF-v1'}
            if 's28' not in s:s['s28']={'contract':contract,'history':[]};self.save(s)
            elif s['s28']['contract']!=contract:raise ValueError('S28 restart contract changed')
        except BaseException:self.close();raise

    def _get_run(self,id,contract):
        row=self.conn.execute('SELECT contract,record FROM s28_runs WHERE id=?',(id,)).fetchone()
        if row and row[0]!=canonical(contract):raise ValueError('S28 case id reused with new public contract')
        return json.loads(row[1]) if row else None
    def _finish(self,id,contract,record,observations,concept=None,dependencies=()):
        state=self.state();cost=len(observations)
        if cost>state['shared_budget']:raise ValueError('budget underflow')
        state['shared_budget']-=cost;state['s22']['revision']+=1
        nodes=state['s22']['nodes'];deps=[]
        for r in observations:
            key='s28:receipt:'+r['id']
            if key in nodes:raise ValueError('duplicate graph receipt')
            nodes[key]={'kind':'intervention_observation','domain':'s28','valid':True,'depends':[],
                        'input':r['input'],'value':r['value']}
            deps.append(key)
        if concept is not None:
            key='s28:concept:'+id
            nodes[key]={'kind':'constructed_predicate','domain':'s28','valid':True,
                        'depends':list(dependencies)+deps,'clauses':concept['clauses'],
                        'scope':'three-feature Boolean world; bounded evidence, not absolute truth'}
        record['remaining_budget']=state['shared_budget']
        record['model_id']=('s28:concept:'+id) if concept is not None else None
        state['s28']['history'].append(record)
        with self.conn:
            self.conn.execute('UPDATE s20_state SET body=? WHERE id=1',(canonical(state),))
            self.conn.execute('INSERT INTO s28_runs VALUES(?,?,?)',(id,canonical(contract),canonical(record)))
        return record
    def learn_concept(self,case,world,*,budget_cap=None):
        contract={'type':'learn','case':case,'fields':list(world.fields),'world_tag':world.world_tag,'cap':budget_cap}
        old=self._get_run(case,contract)
        if old:return old
        s=self.state();limit=s['shared_budget'] if budget_cap is None else min(s['shared_budget'],budget_cap)
        if type(limit)!=int or limit<0:raise ValueError('invalid budget cap')
        obs=[];model=None
        if limit<8:status='BUDGET_STOP'
        else:
            for idx,x in enumerate(all_inputs(world.fields)):
                rid=case+':'+str(idx)
                obs.append({'id':rid,'input':x,'value':world.observe(rid,x)})
            gap=not atomic_expressible(world.fields,obs)
            if gap and not self._constructor_enabled:status='REPRESENTATION_GAP'
            else:
                model=induce(world.fields,obs);status='CONCEPT_CONSTRUCTED' if gap else 'PREEXISTING_CONCEPT'
        return self._finish(case,contract,{'case':case,'status':status,'representation_gap':bool(obs) and not atomic_expressible(world.fields,obs),
                     'observations':obs,'concept':model,'cost_used':len(obs)},obs,model)

    def transfer_concept(self,case,source_case,world,*,budget_cap=None,challenge_count=2):
        contract={'type':'transfer','source':source_case,'case':case,'fields':list(world.fields),
                  'cap':budget_cap,'world_tag':world.world_tag,'challenge_count':challenge_count}
        old=self._get_run(case,contract)
        if old:return old
        s=self.state();limit=s['shared_budget'] if budget_cap is None else min(s['shared_budget'],budget_cap)
        if type(limit)!=int or limit<0 or type(challenge_count)!=int or challenge_count<1:raise ValueError('invalid limit')
        base=self.conn.execute('SELECT record FROM s28_runs WHERE id=?',(source_case,)).fetchone()
        source=json.loads(base[0]) if base else None
        source_id='s28:concept:'+source_case
        if not source or not source['concept'] or not valid_dependency_path(s['s22']['nodes'],source_id):
            return self._finish(case,contract,{'case':case,'status':'NO_VALID_SOURCE','observations':[],
                                              'concept':None,'cost_used':0},[],None)
        source_fields=tuple(sorted(source['observations'][0]['input']))
        hypotheses=rebindings(source['concept']['clauses'],source_fields,world.fields)
        points=all_inputs(world.fields);observations=[];used=set();challenges=0;status='UNRESOLVED'
        while len(observations)<limit:
            if not hypotheses:status='TRANSFER_REFUTED';break
            if len(hypotheses)==1 and challenges>=challenge_count:
                status='TRANSFER_CHECKED';break
            inp=choose_probe(hypotheses,points,used)
            if inp is None:status='NO_FURTHER_EVIDENCE';break
            rid=case+':'+str(len(observations));value=world.observe(rid,inp)
            observations.append({'id':rid,'input':inp,'value':value});used.add(canonical(inp))
            before=len(hypotheses)
            hypotheses=[h for h in hypotheses if evaluate(h['clauses'],inp)==value]
            if before==1:challenges+=1
        if len(hypotheses)==1 and challenges>=challenge_count:status='TRANSFER_CHECKED'
        concept=None;depend=[]
        if status=='TRANSFER_CHECKED':
            concept={'clauses':hypotheses[0]['clauses'],'expression':'TRANSFER_FROM_SOURCE','cost':len(observations)}
            depend=[source_id]
        elif not hypotheses and self._constructor_enabled:
            # New data invalidate the source transfer; acquire complete local evidence
            # and construct a fresh concept rather than silently treating the source as truth.
            for inp in points:
                if canonical(inp) in used or len(observations)>=limit:continue
                rid=case+':'+str(len(observations));value=world.observe(rid,inp)
                observations.append({'id':rid,'input':inp,'value':value});used.add(canonical(inp))
            if len(used)==8:
                concept=induce(world.fields,observations)
                status='RECONSTRUCTED_FROM_NEW_EVIDENCE'
            else:status='BUDGET_STOP'
        elif len(observations)>=limit:status='BUDGET_STOP'
        return self._finish(case,contract,{'case':case,'source':source_case,'status':status,
               'concept':concept,'observations':observations,'cost_used':len(observations),
               'candidate_functions_remaining':len(hypotheses),'source_valid_at_use':True},
               observations,concept,dependencies=depend)

    def challenge(self,challenge_id,case,world,assignment):
        contract={'id':challenge_id,'case':case,'world_tag':world.world_tag,'input':assignment}
        row=self.conn.execute('SELECT contract,record FROM s28_challenges WHERE id=?',(challenge_id,)).fetchone()
        if row:
            if row[0]!=canonical(contract):raise ValueError('challenge id collision')
            return json.loads(row[1])
        s=self.state()
        if s['shared_budget']<1:return {'status':'BUDGET_STOP'}
        key='s28:concept:'+case
        model=s['s22']['nodes'].get(key)
        if not model or not valid_dependency_path(s['s22']['nodes'],key):return {'status':'NO_VALID_CONCEPT'}
        predicted=evaluate(model['clauses'],assignment)
        receipt_id='challenge:'+challenge_id;actual=world.observe(receipt_id,assignment)
        outcome='CORROBORATED' if predicted==actual else 'CONCEPT_REFUTED'
        state=self.state();state['shared_budget']-=1;state['s22']['revision']+=1
        state['s22']['nodes']['s28:receipt:'+receipt_id]={'kind':'intervention_observation','domain':'s28',
               'valid':True,'depends':[],'input':assignment,'value':actual}
        revoked=revoke(state['s22']['nodes'],key,'S28_HELDOUT_COUNTEREXAMPLE') if actual!=predicted else []
        record={'status':outcome,'predicted':predicted,'observed':actual,'revoked':revoked,'remaining_budget':state['shared_budget']}
        with self.conn:
            self.conn.execute('UPDATE s20_state SET body=? WHERE id=1',(canonical(state),))
            self.conn.execute('INSERT INTO s28_challenges VALUES(?,?,?)',(challenge_id,canonical(contract),canonical(record)))
        return record
