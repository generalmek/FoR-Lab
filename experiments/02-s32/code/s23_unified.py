"""S23 active diagnostic inquiry built on S22; shared source/actuator semantics.
The receiver does not disclose private sample vectors or world variant to agent state.
"""
from copy import deepcopy
from math import isfinite
from s22_unified import S22Unified
from s21_unified import S21Unified
from s22_semantic_kernel import valid_dependency_path
from s23_inquiry import PUBLIC_PROBES,PrivateProbeReceiver,select_probe

DEFAULT_PRIVATE={
 'source':{'D':[12,12],'E':[12,12]},
 'actuator':{'U3':[7,7],'U3-alt':[7,7]}
}

class S23Unified(S22Unified):
    def __init__(self,*args,active_inquiry=True,probe_catalog=None,private_samples=None,**kwargs):
        if type(active_inquiry) is not bool:raise ValueError('active_inquiry bool required')
        self.active_inquiry=active_inquiry
        self.probe_catalog=deepcopy(probe_catalog if probe_catalog is not None else PUBLIC_PROBES)
        self._check_public_catalog(self.probe_catalog)
        super().__init__(*args,**kwargs)
        try:
            self.probe_receiver=PrivateProbeReceiver(self.root/'s23_probe_host.sqlite',
                deepcopy(private_samples if private_samples is not None else DEFAULT_PRIVATE))
            s=self.state()
            contract={'enabled':active_inquiry,'catalog':self.probe_catalog}
            if 's23' not in s:
                s['s23']={'contract':contract,'status':'IDLE','inquiries':[],
                          'active':None,'cost_used':0,'attempted':0,'outcome':None,'history':[]}
                self.save(s)
            elif s['s23']['contract']!=contract:
                raise ValueError('S23 public inquiry contract changed on restart')
        except BaseException:
            if hasattr(self,'probe_receiver'):self.probe_receiver.close()
            super().close();raise
    @staticmethod
    def _check_public_catalog(catalog):
        for domain,entries in catalog.items():
            if domain not in ('source','actuator'):raise ValueError('unsupported domain')
            for p in entries:
                if not isinstance(p.get('role'),str) or not isinstance(p.get('root'),str) or not isinstance(p.get('measurand'),str):
                    raise ValueError('invalid public capability')
                if not isinstance(p.get('cost'),int) or isinstance(p['cost'],bool) or p['cost']<1:
                    raise ValueError('invalid public probe cost')
    def close(self):
        if hasattr(self,'probe_receiver'):self.probe_receiver.close();del self.probe_receiver
        super().close()
    def observe_public(self,event_id,domain,role,value,*,radius=0):
        before=self.state();previous_events={x['event_id'] for x in before['s22']['external_observations']}
        super().observe_public(event_id,domain,role,value,radius=radius)
        if event_id in previous_events:return
        s=self.state();gr=s['s23']
        if not s['s22']['questions'] or s['s22']['questions'][-1]['origin']!=event_id:
            return  # agreement doesn't trigger active inquiry
        if gr['active'] is not None:raise ValueError('another S23 inquiry is already active')
        if not self.active_inquiry:
            gr['status']='ABLATED';self.save(s);return
        if domain=='source':
            olds=[x for x in self.sensor.agent.state()['evidence'] if x['channel']==role]
        else:
            olds=[x for x in self.act.snapshot()['state']['evidence'] if x['probe']==role]
        if not olds:raise AssertionError('S22 accepted an unobserved role')
        if not all(isfinite(float(v['value'])) for v in olds):raise ValueError('non-finite previous value')
        item={'event_id':event_id,'domain':domain,'role':role,'old_values':[x['value'] for x in olds],
              'new_value':value,'stage':'REPEAT','readings':{'REPEAT':[],'INDEPENDENT':[]},
              'receipt_keys':[],'chosen_probes':[],'question':'Which observation distinguishes transient error from a changed law?',
              'status':'ACTIVE'}
        gr['status']='ACTIVE';gr['active']=item;gr['inquiries'].append({'event_id':event_id,'status':'ACTIVE'})
        self._record(s,'S23_ACTIVE_QUESTION',origin=event_id,domain=domain,role=role)
        self.save(s)
    def _finish(self,s,status,reason):
        r=s['s23'];item=r['active'];item['status']=status;item['reason']=reason
        for question in s['s22']['questions']:
            if question.get('origin')==item['event_id']:
                question['status']='RESOLVED_WITH_NEW_BASIS' if status=='VALIDATED' else 'OPEN_UNRESOLVED'
        r['inquiries'][-1]['status']=status;r['outcome']=reason
        r['history'].append(deepcopy(item));r['active']=None;r['status']=status
        if status!='VALIDATED':
            s['phase']='BUDGET_STOP' if status=='BUDGET_STOP' else 'SAFE_HOLD'
            s['s21']['permission']['status']='DENIED'
            s['worldview']['cross_domain_gate']='DENIED_UNRESOLVED_INQUIRY'
        self._record(s,'S23_INQUIRY_RESULT',status=status,reason=reason)
        self.save(s)
    def _validate_new_bases(self,s,item):
        gr=s['s22'];nodes=gr['nodes']
        fresh=item['receipt_keys']
        if len(fresh)!=4 or not all(valid_dependency_path(nodes,k) for k in fresh):
            raise AssertionError('fresh independent evidence missing')
        domain=item['domain']; origin=item['event_id']
        root=f'{domain}:s23:revised_basis:{origin}'
        if domain=='source':
            # Explicitly new claim, not revalidation of invalidated S22 attestation.
            deps=list(fresh)
            model='actuator:model'
        else:
            previous=[k for k in nodes if k.startswith('actuator:receipt:') and ':external:' not in k]
            deps=previous+list(fresh)
            model=root
        gr['revision']+=1
        nodes[root]={'kind':'verified_revised_model','domain':domain,'valid':True,
                     'depends':deps,'revision':gr['revision'],'origin':origin,
                     'scope':'one current bounded task','trust_limit':'declared independent roots'}
        if not valid_dependency_path(nodes,root):raise AssertionError('new model lacks full proof path')
        other=('actuator:model' if domain=='source' else 'source:attestation')
        if not valid_dependency_path(nodes,other):
            return False
        decision='decision:s23:reissued:'+origin
        gr['revision']+=1
        nodes[decision]={'kind':'reissued_decision_basis','domain':'cross_domain','valid':True,
                         'depends':[root,other],'revision':gr['revision'],'origin':origin}
        if not valid_dependency_path(nodes,decision):raise AssertionError('new permission missing proof')
        s['s21']['permission']={'status':'VALID','basis':[decision],'revision':gr['revision']}
        s['worldview']['cross_domain_gate']='S23_NEW_VERSIONED_BASIS'
        return True
    def plan_probe(self, stage, domain, role, catalog, readings):
        return select_probe(stage,domain,role,catalog,readings)

    def _one_active_read(self):
        s=self.state();gr=s['s23'];item=gr['active']
        if item is None:return self.snapshot()
        stage=item['stage']
        probe=self.plan_probe(stage,item['domain'],item['role'],self.probe_catalog,item['readings'])
        if probe is None:
            self._finish(s,'UNIDENTIFIABLE','NO_DECLARED_INDEPENDENT_PROBE');return self.snapshot()
        if s['shared_budget']<probe['cost']:
            self._finish(s,'BUDGET_STOP','NOT_ENOUGH_BUDGET_FOR_PROBE');return self.snapshot()
        n=len(item['readings'][stage])+1
        key='S23:'+item['event_id']+':'+stage+':'+str(n)
        # The agent chooses probe; only host receiver supplies the response and persisted receipt.
        receipt=self.probe_receiver.read(item['domain'],probe['role'],key)
        val=receipt['value']
        if isinstance(val,bool) or not isinstance(val,(float,int)) or not isfinite(float(val)):
            raise ValueError('invalid measured value from host')
        s['shared_budget']-=probe['cost'];gr['cost_used']+=probe['cost'];gr['attempted']+=1
        obs={'id':key,'role':probe['role'],'value':val,'radius':receipt['radius'],'root':probe['root'],
             'measurand':probe['measurand'],'cost':probe['cost']}
        item['readings'][stage].append(obs);item['receipt_keys'].append(f'{item["domain"]}:s23:receipt:{key}')
        item['chosen_probes'].append({'stage':stage,'role':probe['role'],'receipt_id':key})
        nodes=s['s22']['nodes'];id=item['receipt_keys'][-1]
        if id in nodes:raise AssertionError('duplicate S23 evidence')
        nodes[id]={'kind':'observed_measurement','domain':item['domain'],'valid':True,'depends':[],
                   'value':val,'radius':receipt['radius'],'root':probe['root'], 'measurand':probe['measurand']}
        s['s22']['revision']+=1
        self._record(s,'S23_PROBE_OBSERVED',domain=item['domain'],stage=stage,role=probe['role'],receipt_id=key,value=val)
        if stage=='REPEAT' and n==2:
            a,b=item['readings']['REPEAT']
            if abs(a['value']-b['value'])>a['radius']+b['radius']:
                self._finish(s,'UNIDENTIFIABLE','SUSPECT_REPEAT_INCONSISTENT');return self.snapshot()
            item['stage']='INDEPENDENT'
        elif stage=='INDEPENDENT' and n==2:
            a,b=item['readings']['INDEPENDENT']
            if abs(a['value']-b['value'])>a['radius']+b['radius']:
                self._finish(s,'UNIDENTIFIABLE','INDEPENDENT_REPEAT_INCONSISTENT');return self.snapshot()
            old=item['old_values']
            if len(set(old))!=1:
                self._finish(s,'UNIDENTIFIABLE','ORIGINAL_EVIDENCE_UNSTABLE');return self.snapshot()
            repeated=item['readings']['REPEAT']
            if abs(repeated[0]['value']-a['value'])>repeated[0]['radius']+a['radius']:
                self._finish(s,'UNIDENTIFIABLE','CROSS_PROBE_DISAGREEMENT');return self.snapshot()
            # An apparently separate measurement may still be correlated; claim is bounded.
            if abs(a['value']-old[0])>a['radius']:
                self._finish(s,'REQUIRES_REVISION','PERSISTENT_CHANGED_MEASUREMENT');return self.snapshot()
            if not self._validate_new_bases(s,item):
                self._finish(s,'UNIDENTIFIABLE','OTHER_CROSS_DOMAIN_BASIS_UNVERIFIED');return self.snapshot()
            self._finish(s,'VALIDATED','TRANSIENT_DISCREPANCY_RETESTED')
            return self.snapshot()
        s['tick']+=1
        s['self_coordinate']={'tick':s['tick'],'active_question':'S23:'+item['event_id'],
                              'remaining_global_budget':s['shared_budget'],
                              'inquiry_phase':item['stage']}
        self.save(s)
        return self.snapshot()
    def step(self):
        s=self.state()
        if s['phase']!='ACTIVE':return self.snapshot()
        if s['s23']['active'] is not None:
            return self._one_active_read()
        if s['s23']['status']=='VALIDATED':
            # S22 keeps its historical revoked claim; bypass ONLY its obsolete
            # terminal gate after establishing a fresh proof path.
            if not s['s21']['permission']['status']=='VALID':
                raise AssertionError('no versioned authorization for resumption')
            claim='decision:s23:reissued:'+s['s23']['history'][-1]['event_id']
            if not valid_dependency_path(s['s22']['nodes'],claim):
                s['phase']='SAFE_HOLD'
                s['s21']['permission']['status']='DENIED'
                self._record(s,'S23_NEW_AUTHORIZATION_LOST_BASIS',claim=claim)
                self.save(s)
                return self.snapshot()
            out=S21Unified.step(self)
            state=self.state();self._refresh(state);self.save(state)
            return self.snapshot()
        return super().step()
    def snapshot(self):
        ans=super().snapshot();ans['active_inquiry']=ans['controller'].get('s23');return ans
