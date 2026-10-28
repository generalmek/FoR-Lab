"""S27 bounded method-construction exercise in the SAME persistent S26 agent DB.

S25 and S26 keep exclusive control of actuator effects. S27 only performs
research measurements and writes scoped revisable propositions, no new physical
actuator entry point. Host world private measurements are not in public state.
"""
import json,sqlite3
from pathlib import Path
from s26_unified import S26Unified
from s27_method import MethodMemory,find_plan,canonical

class S27Host:
    """Private sensor responses; not passed to planner or persisted in agent state."""
    def __init__(self,path,readings,physical_truth):
        self.db=sqlite3.connect(str(path))
        self.db.execute('CREATE TABLE IF NOT EXISTS contract (id INTEGER PRIMARY KEY, content TEXT)')
        self.db.execute('CREATE TABLE IF NOT EXISTS receipts (id TEXT PRIMARY KEY, role TEXT, value REAL)')
        self._private=dict(readings)
        self._actual=physical_truth
        content=canonical({'readings':readings,'truth':physical_truth})
        previous=self.db.execute('SELECT content FROM contract WHERE id=1').fetchone()
        if previous and previous[0]!=content:raise ValueError('host world changed on restart')
        if not previous:
            with self.db:self.db.execute('INSERT INTO contract VALUES(1,?)',(content,))
    def read(self,key,role):
        existing=self.db.execute('SELECT role,value FROM receipts WHERE id=?',(key,)).fetchone()
        if existing:
            if existing[0]!=role:raise ValueError('receipt id collision')
            return existing[1]
        if role not in self._private:raise ValueError('missing private observation')
        value=self._private[role]
        if type(value) not in (int,float):raise ValueError('invalid sensor number')
        with self.db:self.db.execute('INSERT INTO receipts VALUES(?,?,?)',(key,role,value))
        return value
    def total_reads(self):return self.db.execute('SELECT COUNT(*) FROM receipts').fetchone()[0]
    def private_audit(self):return {'actual':self._actual,'readings':dict(self._private)}
    def close(self):self.db.close()

class S27Unified(S26Unified):
    def __init__(self,*args,memory_enabled=True,**kwargs):
        if type(memory_enabled) is not bool:raise ValueError('memory_enabled bool required')
        self._s27_memory_enabled=memory_enabled
        super().__init__(*args,**kwargs)
        try:
            self.method_memory=MethodMemory(self.conn)
            s=self.state()
            contract={'memory':memory_enabled,'language':'S27/compositional-methods-v1'}
            if 's27' not in s:
                s['s27']={'contract':contract,'history':[],'models':[]}
                self.save(s)
            elif s['s27']['contract']!=contract:
                raise ValueError('S27 method-memory contract cannot change on restart')
        except BaseException:self.close();raise

    def _revalidate_method_provenance(self):
        """A learned procedure cannot outlive its original evidence."""
        from s22_semantic_kernel import valid_dependency_path
        nodes=self.state()['s22']['nodes']
        rows=self.conn.execute('SELECT id,evidence FROM s27_methods WHERE valid=1').fetchall()
        for ident,evidence in rows:
            receipts=json.loads(evidence).get('receipts',[])
            if not receipts or not all(valid_dependency_path(nodes,'s27:receipt:'+r) for r in receipts):
                self.method_memory.revoke(ident)

    def research_case(self,case_id,ops,host,*,budget_cap=None):
        if not isinstance(case_id,str) or not case_id:raise ValueError('case id')
        from s27_method import candidates
        ops=candidates(ops)
        contract=canonical({'id':case_id,'ops':ops,'budget_cap':budget_cap})
        previous=self.conn.execute('SELECT contract,record FROM s27_runs WHERE id=?',(case_id,)).fetchone()
        if previous:
            if previous[0]!=contract:raise ValueError('case id reused with changed public contract')
            return json.loads(previous[1])
        s=self.state();shared_budget=s['shared_budget']
        if budget_cap is not None:
            if type(budget_cap) is not int or budget_cap<0:raise ValueError('invalid budget cap')
            limit=min(budget_cap,shared_budget)
        else:limit=shared_budget
        if self._s27_memory_enabled:self._revalidate_method_provenance()
        plan=self.method_memory.transfer(ops,limit) if self._s27_memory_enabled else None
        if plan is None:
            derived=find_plan(ops,budget=limit)
            plan=dict(derived,source='CONSTRUCTED',method_id=None) if derived else None
        lookup={x['name']:x for x in ops}
        observations=[];trace=[];cost_used=0;basis=None
        status='NO_PLAN' if plan is None else 'ACTIVE'
        if plan:
            for index,name in enumerate(plan['names']):
                op=lookup[name];cost=op['cost']
                if cost_used+cost>limit:status='BUDGET_EXHAUSTED';break
                kind=op['kind']
                if kind=='MEASURE':
                    value=host.read(f'{case_id}:{index}',op['role'])
                    observations.append({'id':f'{case_id}:{index}','role':op['role'],'value':value,
                                         'root':op['root'],'quantity':op['quantity'],'type':'primary' if 'PRIMARY_OBSERVED' in op['adds'] else 'independent'})
                if kind=='COMPARE':
                    if len(observations)!=2 or observations[0]['quantity']!=observations[1]['quantity'] or observations[0]['root']==observations[1]['root']:
                        status='INVALID_PROVENANCE';break
                    if abs(observations[0]['value']-observations[1]['value'])>0:
                        status='CONTRADICTORY_READINGS';break
                if kind=='MODEL':
                    if len(observations)!=2 or observations[0]['value']!=observations[1]['value']:
                        status='NO_VERIFIED_MODEL';break
                    basis={'value':observations[0]['value'],'quantity':observations[0]['quantity'],
                           'depends':[f's27:receipt:{o["id"]}' for o in observations],
                           'scope':'bounded independent agreement; not truth guarantee'}
                cost_used+=cost;trace.append(name)
            else:status='VERIFIED' if basis is not None else 'NO_VERIFIED_MODEL'
        method_id=None
        if status=='VERIFIED' and self._s27_memory_enabled:
            method_id=self.method_memory.learn(case_id,ops,trace,{'status':status,'receipts':[o['id'] for o in observations]})
        # Versioned evidence enters the SAME worldview dependency graph as S22.
        s['shared_budget']-=cost_used
        s['s22']['revision']+=1
        gr=s['s22']['nodes']
        for obs in observations:
            key='s27:receipt:'+obs['id']
            if key in gr:raise ValueError('duplicate receipt graph id')
            gr[key]={'kind':'observed_measurement','domain':'s27_exercise','valid':True,'depends':[],
                     'value':obs['value'],'root':obs['root'],'quantity':obs['quantity']}
        if basis is not None:
            model_key='s27:model:'+case_id
            gr[model_key]={'kind':'bounded_model','domain':'s27_exercise','valid':True,
                           'depends':list(basis['depends']),'value':basis['value'],'quantity':basis['quantity'],
                           'scope':basis['scope']}
            s['s27']['models'].append(model_key)
        record={'case':case_id,'status':status,'plan_source':plan['source'] if plan else None,
                'plan':plan['names'] if plan else [],'examined':plan['examined'] if plan else 0,
                'method_id':plan.get('method_id') if plan else None,'learned_method_id':method_id,
                'trace':trace,'cost_used':cost_used,'observations':observations,
                'model':basis,'shared_budget_after':s['shared_budget']}
        s['s27']['history'].append(record)
        # Leave the existing actuator model and physical gate untouched.
        # One SQLite transaction for state and run record. A crash before COMMIT
        # can re-read host receipts idempotently; after COMMIT it replays the record.
        with self.conn:
            self.conn.execute('UPDATE s20_state SET body=? WHERE id=1',
                              (json.dumps(s,ensure_ascii=False,sort_keys=True),))
            self.conn.execute('INSERT INTO s27_runs VALUES(?,?,?,?)',(case_id,contract,status,canonical(record)))
        return record
