"""S22 shared semantic evidence and inquiry language layered over S21.
Two specialist physical adapters still exist; shared semantic invalidation is live.
"""
from copy import deepcopy
from s21_unified import S21Unified
from s22_semantic_kernel import plan,valid_dependency_path,revoke,compare_observations

class S22Unified(S21Unified):
    def __init__(self,*args,semantic_enabled=True,**kwargs):
        super().__init__(*args,**kwargs)
        self.semantic_enabled=semantic_enabled
        s=self.state()
        if 's22' in s and s['s22'].get('semantic_enabled')!=semantic_enabled:
            self.close();raise ValueError('S22 semantic ablation mode changed on restart')
        if 's22' not in s:
            s['s22']={'semantic_enabled':semantic_enabled,'revision':0,'nodes':{},'history':[], 'questions':[], 'procedures':[],
                       'external_observations':[], 'gate':'PENDING','method_language':'generic_evidence_v1'}
            self._refresh(s);self.save(s)
        else:
            self._refresh(s);self.save(s)

    @staticmethod
    def _add(gr,key,kind,domain,depends=(),**kw):
        node={'kind':kind,'domain':domain,'valid':True,'depends':list(dict.fromkeys(depends)),**kw}
        prior=gr['nodes'].get(key)
        if prior is None:
            gr['nodes'][key]=node;gr['revision']+=1
        elif prior.get('valid') and prior!=node:
            gr['history'].append({'node':key,'previous':deepcopy(prior),'revision':gr['revision']})
            gr['nodes'][key]=node;gr['revision']+=1
        # Never silently re-validate a previously invalidated claim.
        return key

    def _refresh(self,s):
        gr=s['s22'];nodes=gr['nodes']
        # Reconcile public S21 claim revisions. A model's ID is stable across
        # tasks, but its version/content is NOT; never retain task-1 evidence
        # for a task-4 model. Preserve historical revisions in append-only history.
        for key,upstream in s['s21']['nodes'].items():
            fresh=deepcopy(upstream)
            if key not in nodes:
                nodes[key]=fresh;gr['revision']+=1
                continue
            prior=nodes[key]
            if not fresh.get('valid',True) and prior.get('valid',True):
                revoked=revoke(nodes,key,'S21_PRIOR_BASIS_REVOKED')
                gr['revision']+=len(revoked)
            elif prior.get('valid') and fresh.get('valid'):
                # The model's evidence dependency edges are added below.
                comparable={k:v for k,v in prior.items() if not (key=='actuator:model' and k=='depends')}
                upstream_comparable={k:v for k,v in fresh.items() if not (key=='actuator:model' and k=='depends')}
                if comparable!=upstream_comparable:
                    gr['history'].append({'node':key,'previous':deepcopy(prior),'revision':gr['revision']})
                    nodes[key]=fresh;gr['revision']+=1
            # An invalid S22 claim cannot be revived merely by re-projection.
        ast=self.act.snapshot()['state']
        ctx=ast.get('context');task=ast.get('task_id')
        receipt_keys=[]
        for ob in ast.get('evidence',[]):
            rid=ob.get('operation_id')
            if not rid:continue
            key='actuator:receipt:'+str(rid)
            self._add(gr,key,'observed_measurement','actuator',value=ob['value'],radius=ob.get('radius',0),
                      probe=ob['probe'],context=ctx,task_id=task)
            receipt_keys.append(key)
        # Unlike S21, model now has explicit dependencies on the observed evidence.
        if 'actuator:model' in nodes and nodes['actuator:model'].get('valid'):
            node=nodes['actuator:model'];desired=list(dict.fromkeys(receipt_keys))
            if node.get('context')==ctx and node.get('task')==task and node.get('depends')!=desired:
                gr['history'].append({'node':'actuator:model','previous':deepcopy(node),'revision':gr['revision']})
                node['depends']=desired;gr['revision']+=1
        if any(not nodes[k].get('valid') for k in ('source:attestation','actuator:model','decision:actuator_authorization') if k in nodes):
            gr['gate']='REVOKED'
        elif 'decision:actuator_authorization' in nodes and nodes['decision:actuator_authorization'].get('valid'):
            valid=valid_dependency_path(nodes,'decision:actuator_authorization')
            model_ok=valid_dependency_path(nodes,'actuator:model') and bool(nodes['actuator:model']['depends'])
            if valid and model_ok:
                gr['gate']='SUPPORTED'
            else:
                gr['gate']='INSUFFICIENT_DEPENDENCIES'
        else:
            gr['gate']='UNRESOLVED'

    def observe_public(self,event_id,domain,role,value,*,radius=0):
        """Injects a witnessed public observation (not a hidden truth or diagnosis).
        Method construction, evidence comparison and invalidation are identical in both domains.
        """
        if domain not in ('source','actuator'):raise ValueError('unsupported observed domain')
        if not isinstance(event_id,str) or not event_id.strip():raise ValueError('event id required')
        if not isinstance(role,str) or not role.strip():raise ValueError('observed role required')
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not isinstance(radius,(int,float)) or radius<0:
            raise ValueError('numeric observation/radius required')
        s=self.state()
        if s['phase']!='ACTIVE':raise ValueError('public observation requires active episode')
        gr=s['s22']
        if any(o['event_id']==event_id for o in gr['external_observations']):
            prior=next(o for o in gr['external_observations'] if o['event_id']==event_id)
            if (domain,role,value,radius)!=(prior['domain'],prior['role'],prior['value'],prior['radius']):
                raise ValueError('immutable event id reused')
            return
        self._refresh(s)
        # Evidence from current domain is required; no claim about an unseen source.
        if domain=='source':
            olds=[o for o in self.sensor.agent.state()['evidence'] if o['channel']==role]
            prereq='source:attestation'
            if not olds:raise ValueError('role was not previously observed')
        else:
            olds=[o for o in self.act.snapshot()['state'].get('evidence',[]) if o['probe']==role]
            prereq='actuator:model'
            if not olds:raise ValueError('role was not previously observed')
        if prereq not in gr['nodes']:raise ValueError('no verified model in shared graph')
        ob={'event_id':event_id,'domain':domain,'role':role,'value':value,'radius':radius,
            'origin':'public_observation','tick':s['tick']}
        gr['external_observations'].append(ob)
        newkey=f'{domain}:receipt:external:{event_id}'
        self._add(gr,newkey,'observed_measurement',domain,value=value,radius=radius,role=role,receipt_id=event_id)
        # Execute the first common operation to acquire a comparison, then
        # compose the rest from the observed comparison result (not host truth).
        initial_facts={'new_observation','prior_observation'}
        compare_program=plan(initial_facts,'comparison')
        if compare_program is None or compare_program['operations']!=['COMPARE_OBSERVATIONS']:
            raise AssertionError('common comparison operator unavailable')
        match=all(compare_observations(x,ob) for x in olds)
        facts=initial_facts|{'comparison',('agreement' if match else 'mismatch')}
        goal='corroborated' if match else 'research_question'
        continuation=plan(facts,goal)
        if continuation is None:raise AssertionError('failed to assemble common research method')
        procedure={'domain_binding':domain,'role_binding':role,'event_id':event_id,
                   'goal':goal,'operations':compare_program['operations']+continuation['operations'],
                   'cost':compare_program['cost']+continuation['cost'],
                   'expanded':compare_program['expanded']+continuation['expanded']}
        gr['procedures'].append(procedure)
        if not match and self.semantic_enabled:
            revoked=revoke(gr['nodes'],prereq,'NEW_CONFLICTING_OBSERVATION')
            gr['revision']+=len(revoked)
            gr['gate']='REVOKED'
            gr['questions'].append({'origin':event_id,'type':'resolve_competing_measurements',
                                    'domain':domain,'role':role,'status':'OPEN','method':procedure['operations']})
            # Bind the same revocation into S21's live permission and executor gate.
            s21revoked=self._revoke(s,prereq,'S22_CROSS_DOMAIN_CONTRADICTION')
            s['s21']['permission']={'status':'REVOKED','basis':s21revoked,'revision':s['s21']['revision']}
            s['worldview']['cross_domain_gate']='DENIED_NEW_MEASUREMENT'
            self._record(s,'S22_SHARED_MODEL_INVALIDATED',domain=domain,role=role,
                         event_id=event_id,revoked=revoked,method=procedure['operations'])
        else:
            # An additional agreement does not justify a missing model by itself.
            self._record(s,'S22_OBSERVATION_COMPARED',domain=domain,role=role,
                         event_id=event_id,agrees=match,method=procedure['operations'])
        s['worldview_version']+=1
        self.save(s)

    def step(self):
        s=self.state()
        if s['phase']!='ACTIVE':return self.snapshot()
        if self.semantic_enabled and s['s22']['gate']=='REVOKED':
            s['phase']='SAFE_HOLD';self._record(s,'S22_SHARED_REASON_PREVENTS_ACTION');self.save(s)
            return self.snapshot()
        result=super().step()
        s=self.state();self._refresh(s);self.save(s)
        return self.snapshot()

    def snapshot(self):
        ans=super().snapshot();ans['semantic_worldview']=ans['controller']['s22']
        return ans
