"""S24: one private actuator physics for inquiry and subsequent virtual action.

The old S16 actor remains as a predecessor, but S24's diagnostic and its new
scoped action use the SAME S16 world.sqlite, law/context and idempotent receipts.
No hidden world variant, law or epoch enters the candidate's stored state.
"""
from copy import deepcopy
from math import isfinite
import json
from pathlib import Path
from s16_integrated import S16Experiment
from s23_unified import S23Unified
from s22_semantic_kernel import valid_dependency_path,revoke
from s25_gate import effective_source_basis


class S24Actuator(S16Experiment):
    """Virtual host with persistent post-calibration changes, closed to agent."""
    VARIANTS_S24={'high':15,'low':8,'false_meters':8}
    def __init__(self,root,*,variant='high'):
        if variant not in self.VARIANTS_S24:raise ValueError('unknown S24 host variant')
        super().__init__(root,world_variant='stable_u3_exception')
        self.host.execute('CREATE TABLE IF NOT EXISTS s24_epoch(id INTEGER PRIMARY KEY,epoch INT,variant TEXT)')
        row=self.host.execute('SELECT epoch,variant FROM s24_epoch WHERE id=1').fetchone()
        if row and row[1]!=variant:
            self.close();raise ValueError('S24 private physics contract changed on restart')
        if not row:
            with self.host:self.host.execute('INSERT INTO s24_epoch VALUES(1,0,?)',(variant,))
        self.s24_variant=variant

    def transition(self):
        if self.config()['context']!=4:raise ValueError('S24 intervention requires observed context four')
        with self.host:self.host.execute('UPDATE s24_epoch SET epoch=1 WHERE id=1')

    def open_engine(self):
        agent,world=super().open_engine()
        row=(self.host.execute('SELECT epoch,variant FROM s24_epoch WHERE id=1').fetchone() if hasattr(self,'host') and self.host.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='s24_epoch'").fetchone() else None)
        if row and row[0]==1 and self.config()['context']==4:
            prior=world.law;new=self.VARIANTS_S24[row[1]]
            world.law=lambda u,v: new if (u==3 and v==4) else prior(u,v)
        return agent,world

    def read_same_world(self,role,key):
        # Distinct public meter roles read same *physical* process, independent
        # calibration is only an advertised assumption and can be false.
        if role not in ('U3','U3-alt','U4','U4-alt'):
            raise ValueError('unsupported public measurement role')
        probe='U'+('3' if role.startswith('U3') else '4')
        agent,world=self.open_engine()
        try:
            world.measurement_key=key
            raw=world.measure(probe)  # persistent physical-world measurement
            world.db.execute('CREATE TABLE IF NOT EXISTS s24_meter_receipts(id TEXT PRIMARY KEY, role TEXT, raw INTEGER, reported INTEGER)')
            prior=world.db.execute('SELECT role,raw,reported FROM s24_meter_receipts WHERE id=?',(key,)).fetchone()
            if prior:
                if prior[0]!=role or prior[1]!=raw:raise ValueError('S24 meter receipt reused')
                observed=prior[2]
            else:
                biased=(self.s24_variant=='false_meters' and probe=='U3' and
                    self.host.execute('SELECT epoch FROM s24_epoch WHERE id=1').fetchone()[0]==1)
                observed=raw+(7 if biased else 0)
                with world.db:world.db.execute('INSERT INTO s24_meter_receipts VALUES(?,?,?,?)',
                                               (key,role,raw,observed))
            return {'id':key,'role':role,'value':observed,'radius':0,
                    'world_receipt_key':key,'physical_probe':probe}
        finally:agent.close();world.close()

    def execute_same_world(self,key,u,expected):
        agent,world=self.open_engine()
        try:
            # One idempotent receiver, identical law/context to local measurements.
            observed=world.apply_once(key,u,expected)
            return {'receipt_id':key,'selected':u,'expected':expected,'observed':observed,
                    'matching':observed==expected}
        finally:agent.close();world.close()

    def physical_receipt(self,key):
        agent,world=self.open_engine()
        try:return world.db.execute('SELECT request,result FROM receipts WHERE id=?',(key,)).fetchone()
        finally:agent.close();world.close()


class S24Receiver:
    def __init__(self,old,act):self.old,self.act=old,act
    def read(self,domain,role,key):
        if domain=='actuator':
            r=self.act.read_same_world(role,key)
            return {'id':key,'domain':domain,'role':role,'value':r['value'],'radius':0,
                    'sequence':1}
        return self.old.read(domain,role,key)
    def close(self):self.old.close()


class S24Unified(S23Unified):
    def __init__(self,*args,physics_variant='high',revision_enabled=True,fail_after_action_effect=False,**kwargs):
        if type(revision_enabled) is not bool:raise ValueError('revision_enabled bool expected')
        super().__init__(*args,**kwargs)
        original=self.act
        try:
            original.close()
            self.act=S24Actuator(self.root/'actuator',variant=physics_variant)
            self.probe_receiver=S24Receiver(self.probe_receiver,self.act)
            s=self.state();contract={'revision_enabled':revision_enabled}
            if 's24' not in s:
                s['s24']={'contract':contract,'status':'IDLE','inquiry':None,'observations':[],
                         'local_models':[],'action':None,'events':[],'cost_used':0,'reason':None}
                self.save(s)
            elif s['s24']['contract']!=contract:raise ValueError('S24 agent contract changed on restart')
        except BaseException:
            self.close();raise
        self.revision_enabled=revision_enabled
        self._inject_failure=fail_after_action_effect

    def publish_change(self,event_id='S24-CHANGED'):
        s=self.state();entry=s['s24']
        if entry['status']!='IDLE':
            if entry['inquiry']==event_id:return
            raise ValueError('second intervention in same bounded episode')
        if s['tick']<25 or not s['actuator_calibrated']:
            raise ValueError('physical change after calibration and novelty only')
        if s['shared_budget']<2:raise ValueError('insufficient budget for public change measurement')
        self.act.transition()
        r=self.act.read_same_world('U3','S24:PUBLIC:'+event_id)
        # The host publishes only witnessed value. The candidate never sees
        # which virtual law was changed, or the physical variant label.
        self.observe_public(event_id,'actuator','U3',r['value'])
        s=self.state();s['shared_budget']-=2;s['s24']['cost_used']+=2
        s['s24']['inquiry']=event_id;s['s24']['status']='AWAIT_S23'
        s['s24']['events'].append({'kind':'PUBLIC_MEASUREMENT','receipt':'S24:PUBLIC:'+event_id,
                                  'value':r['value']})
        self.save(s)

    def _fail(self,s,reason,phase='SAFE_HOLD'):
        s['s24']['reason']=reason;s['s24']['status']='STOPPED';s['phase']=phase
        s['s21']['permission']={'status':'DENIED','basis':[],'revision':s['s22']['revision']}
        s['worldview']['cross_domain_gate']='DENIED_S24_'+reason
        s['s24']['events'].append({'kind':'S24_STOP','reason':reason});self.save(s)

    def plan_validation_probe(self, state, index):
        return {'role':'U4','cost':2,'control':4}

    def plan_scoped_action(self, state, model, floor):
        candidates=sorted((int(u),v) for u,v in model['outputs'].items() if v>floor)
        return candidates[0] if candidates else None

    def _read_candidate(self,s):
        r=s['s24'];n=len(r['observations'])
        probe=self.plan_validation_probe(s,n)
        if not probe:
            self._fail(s,'NO_PLANNED_VALIDATION','SAFE_HOLD');return
        role,cost=probe['role'],probe['cost']
        key=f'S24:{r["inquiry"]}:{role}:{n+1}'
        if s['shared_budget']<cost:self._fail(s,'BUDGET_FOR_LOCAL_VALIDATION','BUDGET_STOP');return
        receipt=self.act.read_same_world(role,key)
        s['shared_budget']-=cost;r['cost_used']+=cost
        ob={'id':key,'probe':'U4','value':receipt['value'],'radius':0,'root':'claimed-secondary',
            'measurand':'response-at-U4'}
        r['observations'].append(ob)
        s['s22']['nodes']['actuator:s24:receipt:'+key]={
            'kind':'observed_measurement','domain':'actuator','valid':True,'depends':[],
            'value':ob['value'],'radius':0,'probe':'U4','root':ob['root']}
        s['s22']['revision']+=1;s['tick']+=1
        r['events'].append({'kind':'S24_U4_MEASURED','receipt':key,'value':ob['value']})
        self.save(s)

    def _construct(self,s):
        r=s['s24'];obs=r['observations'];h=s['s23']['history'][-1]
        if len(obs)!=2 or obs[0]['value']!=obs[1]['value']:
            self._fail(s,'LOCAL_MODEL_UNSTABLE');return
        old_model=s['s22']['nodes'].get('actuator:model')
        if not old_model or old_model['valid']:
            self._fail(s,'PRIOR_MODEL_NOT_REVOKED');return
        fresh=h['receipt_keys']
        if len(fresh)!=4 or not all(valid_dependency_path(s['s22']['nodes'],k) for k in fresh):
            self._fail(s,'S23_GROUND_INVALID');return
        s23values=[x['value'] for stage in h['readings'].values() for x in stage]
        if len(s23values)!=4 or len(set(s23values))!=1:
            self._fail(s,'S23_PERSISTENCE_UNVERIFIED');return
        u3=s23values[0];u4=obs[0]['value']
        if any(type(v) is bool or not isinstance(v,(int,float)) or not isfinite(v) for v in (u3,u4)):
            self._fail(s,'INVALID_LOCAL_VALUE');return
        # Limited new local functional relation: observed control -> value.
        # No extrapolation to unmeasured controls or a claimed global law.
        scoped_model={'scope':{'context':4,'task':self.act.snapshot()['state'].get('task_id')},
                      'outputs':{'3':u3,'4':u4},'method':'finite observed control-response relation',
                      'evidence':fresh+['actuator:s24:receipt:'+x['id'] for x in obs]}
        model_key='actuator:s24:model:'+r['inquiry']
        s['s22']['revision']+=1
        s['s22']['nodes'][model_key]={'kind':'locally_revised_model','domain':'actuator',
            'valid':True,'depends':scoped_model['evidence'],'revision':s['s22']['revision'],
            'scope':scoped_model['scope'],'outputs':scoped_model['outputs']}
        r['local_models'].append(scoped_model)
        # Compass uses public fixed normative floor, not receiver's hidden target.
        floor=self.act.output_floor
        selection=self.plan_scoped_action(s,scoped_model,floor)
        if selection is None:self._fail(s,'NO_ADMISSIBLE_MEASURED_CONTROL');return
        chosen,expected=selection
        other=effective_source_basis(s)
        if other is None or not valid_dependency_path(s['s22']['nodes'],other):
            self._fail(s,'SOURCE_BASIS_INVALID');return
        decision='decision:s24:act:'+r['inquiry']
        s['s22']['revision']+=1
        s['s22']['nodes'][decision]={'kind':'scoped_compass_permission','domain':'cross_domain','valid':True,
            'depends':[model_key,other],'revision':s['s22']['revision'],'control':chosen,
            'expected':expected,'floor':floor}
        if not valid_dependency_path(s['s22']['nodes'],decision):
            self._fail(s,'PERMISSION_PROOF_INVALID');return
        r['action']={'id':'S24:ACT:'+r['inquiry'],'control':chosen,'expected':expected,
                     'decision':decision,'outcome':None}
        r['status']='READY_TO_ACT';s['phase']='ACTIVE'
        s['s21']['permission']={'status':'VALID','basis':[decision],'revision':s['s22']['revision']}
        s['worldview']['cross_domain_gate']='S24_VERIFIED_LOCAL_MODEL'
        r['events'].append({'kind':'S24_MODEL_CONSTRUCTED','outputs':scoped_model['outputs'],
                            'action':chosen,'permission':decision})
        self.save(s)

    def _act(self,s):
        r=s['s24'];a=r['action'];n=s['s22']['nodes'].get(a['decision'])
        if (not n or not valid_dependency_path(s['s22']['nodes'],a['decision'])
            or n.get('control')!=a['control'] or n.get('expected')!=a['expected']):
            self._fail(s,'ACTION_DEPENDENCIES_REVOKED');return
        if s['shared_budget']<1:
            self._fail(s,'BUDGET_FOR_ACTION','BUDGET_STOP');return
        # Durable receiver ID prevents repeated side effect on restart. Results
        # are read back before we declare the model's prediction successful.
        result=self.act.execute_same_world(a['id'],a['control'],a['expected'])
        if self._inject_failure:
            self._inject_failure=False
            raise RuntimeError('S24 injected crash after durable virtual effect, before agent commit')
        a['outcome']=result;s['shared_budget']-=1;s['s24']['cost_used']+=1
        r['events'].append({'kind':'S24_ACTION_RECEIPTED',**result})
        if not result['matching']:
            revoked=revoke(s['s22']['nodes'],'actuator:s24:model:'+r['inquiry'],'S24_ACTUAL_EXECUTION_MISMATCH')
            r['events'].append({'kind':'S24_COUNTEREXAMPLE','revoked':revoked})
            self._fail(s,'EXECUTION_MISMATCH_AFTER_EFFECT');return
        r['status']='DONE';r['reason']='SCOPED_MODEL_CONFIRMED_BY_ACTION'
        for q in s['s22']['questions']:
            if q.get('origin')==r['inquiry']:q['status']='RESOLVED_BY_S24_LOCAL_REVISION'
        s['question_agenda'][0]['status']='RESOLVED';s['phase']='DONE'
        self.save(s)

    def step(self):
        s=self.state();r=s['s24']
        if r['status']=='AWAIT_S23' and s['s23']['status']=='REQUIRES_REVISION':
            if not self.revision_enabled:self._fail(s,'REVISION_DISABLED');return self.snapshot()
            r['status']='VALIDATE_U4';s['phase']='ACTIVE';self.save(s)
        if r['status']=='VALIDATE_U4':
            if len(r['observations'])<2:self._read_candidate(s)
            else:self._construct(s)
            return self.snapshot()
        if r['status']=='READY_TO_ACT':
            self._act(s);return self.snapshot()
        if r['status']=='AWAIT_S23' and s['s23']['status']!='ACTIVE':
            self._fail(s,'RESEARCH_NOT_PERSISTENT');return self.snapshot()
        return super().step()

    def snapshot(self):
        ans=super().snapshot();ans['s24_revision']=ans['controller'].get('s24')
        return ans
