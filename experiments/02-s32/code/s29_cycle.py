"""S29: scoped autonomous concept inquiry in one persistent agent tick loop.

The concept-cycle and actuator S25 route are still distinct authorization
contracts; do not mistake this for an unrestricted/complete Reason system.
"""
import hashlib,json,sqlite3,re
from pathlib import Path
from s28_integrated import S28Unified
from s28_concepts import all_inputs,atomic_expressible,induce,evaluate,canonical
from s22_semantic_kernel import valid_dependency_path,revoke

class S29World:
    """Host-private, epoch-changing physical world. Only fields/world_tag,
    `measure` and `act` are available to the agent-side loop.
    """
    def __init__(self,path,fields,binding,law='xor'):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(str(path))
        self.fields=tuple(sorted(fields))
        if len(self.fields)!=3 or set(binding)!={'a','b','c'} or set(binding.values())!=set(fields):raise ValueError('host binding')
        if law not in ('xor','xor_and_c','and_not'):raise ValueError('host law')
        self.world_tag=hashlib.sha256(str(self.path.resolve()).encode()).hexdigest()[:20]
        self.db.execute('CREATE TABLE IF NOT EXISTS s29_private(id INTEGER PRIMARY KEY, body TEXT)')
        self.db.execute('CREATE TABLE IF NOT EXISTS s29_receipts(id TEXT PRIMARY KEY, kind TEXT, assignment TEXT, value INTEGER, epoch INTEGER)')
        self.private={'binding':binding,'initial_law':law,'current_law':law,'epoch':0}
        row=self.db.execute('SELECT body FROM s29_private WHERE id=1').fetchone()
        if row:
            saved=json.loads(row[0]);
            if saved['binding']!=binding or saved['initial_law']!=law:raise ValueError('changed host private contract')
            self.private=saved
        else:
            with self.db:self.db.execute('INSERT INTO s29_private VALUES(1,?)',(canonical(self.private),))
    def change_law(self,new_law):
        if new_law not in ('xor','xor_and_c','and_not'):raise ValueError('host-only variant')
        if new_law==self.private['current_law']:return
        self.private['current_law']=new_law;self.private['epoch']+=1
        with self.db:self.db.execute('UPDATE s29_private SET body=? WHERE id=1',(canonical(self.private),))
    def _truth(self,assignment):
        b=self.private['binding'];a=assignment[b['a']];z=assignment[b['b']];c=assignment[b['c']]
        law=self.private['current_law']
        return (a^z) if law=='xor' else ((a^z)&c if law=='xor_and_c' else (a&(1-z)))
    def _receipt(self,rid,kind,assignment):
        if set(assignment)!=set(self.fields) or any(type(v)!=int or v not in (0,1) for v in assignment.values()):
            raise ValueError('invalid public intervention')
        body=canonical(assignment)
        row=self.db.execute('SELECT kind,assignment,value FROM s29_receipts WHERE id=?',(rid,)).fetchone()
        if row:
            if row[0]!=kind or row[1]!=body:raise ValueError('immutable receipt collision')
            return row[2]
        value=self._truth(assignment)
        with self.db:self.db.execute('INSERT INTO s29_receipts VALUES(?,?,?,?,?)',(rid,kind,body,value,self.private['epoch']))
        return value
    def measure(self,rid,assignment):return self._receipt(rid,'MEASURE',assignment)
    def act(self,rid,assignment):return self._receipt(rid,'ACT',assignment)
    def counts(self):return dict(self.db.execute('SELECT kind,COUNT(*) FROM s29_receipts GROUP BY kind').fetchall())
    def private_audit(self):return dict(self.private,counts=self.counts())
    def close(self):self.db.close()

class S29Agent(S28Unified):
    def __init__(self,*args,monitor_enabled=True,**kwargs):
        if type(monitor_enabled)!=bool:raise ValueError('monitor flag')
        self.monitor_enabled=monitor_enabled
        super().__init__(*args,**kwargs)
        try:
            state=self.state();contract={'monitor':monitor_enabled,'version':'S29-live-inquiry-v1'}
            if 's29' not in state:
                state['s29']={'contract':contract,'tasks':{},'order':[],'cursor':0,'tick':0,'events':[]}
                self.save(state)
            elif state['s29']['contract']!=contract:raise ValueError('S29 settings changed on restart')
        except BaseException:self.close();raise
    def _event(self,s,kind,task,**detail):
        item={'tick':s['s29']['tick'],'kind':kind,'task':task,**detail}
        s['s29']['events'].append(item)
        return item
    def add_task(self,task_id,world,*,output_floor=0):
        if not isinstance(task_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,32}',task_id) or type(output_floor)!=int:
            raise ValueError('invalid public task')
        s=self.state();tasks=s['s29']['tasks']
        identity={'fields':list(world.fields),'world_tag':world.world_tag,'output_floor':output_floor}
        if task_id in tasks:
            if tasks[task_id]['public']!=identity:raise ValueError('task id used with different world or goal')
            return tasks[task_id]
        tasks[task_id]={'public':identity,'phase':'INQUIRY','generation':0,'observations':[],
                        'model':None,'question':None,'act_id':None,'monitor_index':0,'last_action':None}
        s['s29']['order'].append(task_id)
        self._event(s,'TASK_OBSERVED',task_id,fields=list(world.fields))
        self.save(s)
        return tasks[task_id]
    def _persist(self,s):
        s['s29']['tick']+=1
        s['s22']['revision']+=1
        self.save(s)
    def tick_concepts(self,worlds):
        """One step, one research or action operation. Selects internally among tasks.

        External caller merely supplies accessible host interface by known task id,
        never a proposed question, model or plan.
        """
        s=self.state();cyc=s['s29'];order=cyc['order']
        if not order:return {'kind':'IDLE'}
        for offset in range(len(order)):
            idx=(cyc['cursor']+offset)%len(order);task_id=order[idx]
            t=cyc['tasks'][task_id]
            if t['phase']!='STOPPED':break
        else:return {'kind':'ALL_STOPPED'}
        cyc['cursor']=(idx+1)%len(order)
        world=worlds.get(task_id)
        if world is None:raise ValueError('missing registered world')
        if t['public']['fields']!=list(world.fields) or t['public']['world_tag']!=world.world_tag:
            raise ValueError('world identity mismatch')
        nodes=s['s22']['nodes'];phase=t['phase'];key=f's29:concept:{task_id}:{t["generation"]}'
        if phase=='INQUIRY':
            if s['shared_budget']<1:
                t['phase']='STOPPED';ev=self._event(s,'BUDGET_STOP',task_id)
            else:
                samples=all_inputs(world.fields)
                i=len(t['observations']);x=samples[i]
                rid=f'{task_id}:g{t["generation"]}:read{i}'
                y=world.measure(rid,x)   # host receipt is idempotent across a crash
                t['observations'].append({'id':rid,'input':x,'value':y})
                nodes['s29:receipt:'+rid]={'kind':'intervention_observation','domain':'s29','valid':True,'depends':[],
                                          'value':y,'input':x,'task':task_id,'generation':t['generation']}
                s['shared_budget']-=1
                if len(t['observations'])>=4 and not atomic_expressible(world.fields,t['observations']) and not t['question']:
                    t['question']=f's29:question:{task_id}:{t["generation"]}'
                    nodes[t['question']]={'kind':'research_question','valid':True,
                        'depends':['s29:receipt:'+r['id'] for r in t['observations']],
                        'task':task_id,'issue':'REPRESENTATION_GAP','status':'OPEN'}
                    self._event(s,'QUESTION_INITIATED',task_id,issue='REPRESENTATION_GAP')
                ev=self._event(s,'ACTIVE_MEASUREMENT',task_id,receipt=rid,value=y)
                if len(t['observations'])==8:t['phase']='CONSTRUCT'
        elif phase=='CONSTRUCT':
            observations=t['observations'];gap=not atomic_expressible(world.fields,observations)
            if gap and not self._constructor_enabled:
                t['phase']='STOPPED';ev=self._event(s,'CONSTRUCTION_ABLATED',task_id)
            else:
                try:model=induce(world.fields,observations)
                except ValueError:
                    t['phase']='STOPPED';ev=self._event(s,'MODEL_UNIDENTIFIABLE',task_id)
                else:
                    t['model']=key;t['phase']='READY'
                    nodes[key]={'kind':'constructed_predicate','domain':'s29','valid':True,
                        'depends':['s29:receipt:'+r['id'] for r in observations],
                        'clauses':model['clauses'],'task':task_id,'generation':t['generation'],
                        'scope':'three-bit total intervention table'}
                    if t['question']:nodes[t['question']]['status']='RESOLVED'
                    ev=self._event(s,'NEW_CONCEPT_CONSTRUCTED',task_id,model=key,gap=gap,clauses=model['clauses'])
        elif phase=='READY':
            if not valid_dependency_path(nodes,key):
                t['phase']='INQUIRY';t['generation']+=1;t['observations']=[];t['model']=None;t['question']=None
                ev=self._event(s,'INVALID_MODEL_RESEARCH_REOPENED',task_id)
            else:
                positives=[x for x in all_inputs(world.fields) if evaluate(nodes[key]['clauses'],x)>t['public']['output_floor']]
                if not positives:
                    t['phase']='STOPPED';ev=self._event(s,'COMPASS_REFUSED_ALL',task_id)
                elif s['shared_budget']<1:
                    t['phase']='STOPPED';ev=self._event(s,'BUDGET_STOP',task_id)
                else:
                    action_input=positives[0];action_id=f'{task_id}:g{t["generation"]}:effect'
                    # Shared graph + Compass + immutable host receipt, checked at the
                    # last possible instant, before the only new physical entry point.
                    if not valid_dependency_path(nodes,key):raise RuntimeError('stale model immediately before action')
                    expected=evaluate(nodes[key]['clauses'],action_input)
                    if expected<=t['public']['output_floor']:raise RuntimeError('Compass denied unearned action')
                    result=world.act(action_id,action_input)
                    s['shared_budget']-=1;t['act_id']=action_id
                    t['last_action']={'expected':expected,'actual':result,'input':action_input}
                    nodes[f's29:decision:{action_id}']={'kind':'action_permission','valid':True,
                            'depends':[key],'expected':expected,'actual':result,'floor':t['public']['output_floor']}
                    if expected!=result:
                        revoked=revoke(nodes,key,'ACTION_MISMATCH')
                        t['generation']+=1;t['observations']=[];t['model']=None;t['question']=None;t['phase']='INQUIRY'
                        ev=self._event(s,'ACTION_MISMATCH_REOPEN',task_id,revoked=revoked)
                    else:
                        t['phase']='MONITOR' if self.monitor_enabled else 'DONE'
                        ev=self._event(s,'ACTION_PERFORMED',task_id,expected=expected,actual=result)
        elif phase=='MONITOR':
            if not valid_dependency_path(nodes,key):
                t['generation']+=1;t['observations']=[];t['model']=None;t['question']=None;t['phase']='INQUIRY'
                ev=self._event(s,'REVOKED_DURING_MONITOR',task_id)
            elif s['shared_budget']<1:
                t['phase']='STOPPED';ev=self._event(s,'BUDGET_STOP',task_id)
            else:
                x=all_inputs(world.fields)[t['monitor_index']%8]
                rid=f'{task_id}:monitor:{t["monitor_index"]}'
                actual=world.measure(rid,x)
                predicted=evaluate(nodes[key]['clauses'],x)
                t['monitor_index']+=1;s['shared_budget']-=1
                nodes['s29:receipt:'+rid]={'kind':'monitor_measurement','valid':True,'depends':[],
                                         'value':actual,'input':x,'task':task_id}
                if actual!=predicted:
                    revoked=revoke(nodes,key,'LATE_DISAGREEMENT')
                    t['generation']+=1;t['observations']=[];t['model']=None;t['question']=None;t['phase']='INQUIRY'
                    ev=self._event(s,'LATE_CONTRADICTION_REOPEN',task_id,old_model=key,revoked=revoked)
                else:ev=self._event(s,'MONITOR_CONFIRMED',task_id,receipt=rid)
        else:ev=self._event(s,'NO_OP',task_id,phase=phase)
        self._persist(s)
        return dict(ev,phase=cyc['tasks'][task_id]['phase'],remaining=s['shared_budget'])
