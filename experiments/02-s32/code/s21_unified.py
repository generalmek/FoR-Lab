"""S21: cross-domain causal worldview built over S20 without changing historical code.

Late E is an observed, public newly available source; the candidate only sees
read receipts, claimed lineage and values. The private values are stored in
host DB. This is not an OS sandbox and does not grant filesystem access to agent.
"""
import json
from s20_unified import S20Unified, canonical

class S21Unified(S20Unified):
    def __init__(self, path, source, *, late_values=(12,12), late_root='root-E', late_enabled=True, **kwargs):
        super().__init__(path,source,**kwargs)
        self._late_values=tuple(late_values)
        if len(self._late_values)!=2 or not all(isinstance(x,(int,float)) and not isinstance(x,bool) for x in self._late_values):
            self.close();raise ValueError('E needs two numeric private readings')
        self.late_root=late_root
        self.late_enabled=late_enabled
        public={'late_root':late_root,'late_enabled':late_enabled}
        self.host_db.execute('CREATE TABLE IF NOT EXISTS s21_host(id INTEGER PRIMARY KEY,body TEXT NOT NULL)')
        self.conn.execute('CREATE TABLE IF NOT EXISTS s21_public(id INTEGER PRIMARY KEY,body TEXT NOT NULL)')
        host_body={'E_values':list(self._late_values)}
        host=self.host_db.execute('SELECT body FROM s21_host WHERE id=1').fetchone()
        pub=self.conn.execute('SELECT body FROM s21_public WHERE id=1').fetchone()
        if host and json.loads(host[0])!=host_body:
            self.close();raise ValueError('S21 private observations changed on restart')
        if pub and json.loads(pub[0])!=public:
            self.close();raise ValueError('S21 public source contract changed on restart')
        if not host:
            with self.host_db:self.host_db.execute('INSERT INTO s21_host VALUES(1,?)',(canonical(host_body),))
        if not pub:
            with self.conn:self.conn.execute('INSERT INTO s21_public VALUES(1,?)',(canonical(public),))
        s=self.state()
        if 's21' not in s:
            s['s21']={'nodes':{},'revision':0,'late':{'announced':False,'readings':[], 'state':'NONE'},
                      'permission':{'status':'PENDING','basis':[],'revision':0},
                      'history':[],'questions':[]}
            self._synchronize(s)
            self.save(s)

    @staticmethod
    def _node(s,key,kind,domain,valid=True,depends=None,**attributes):
        gr=s['s21']; nodes=gr['nodes']; deps=list(depends or [])
        v={'kind':kind,'domain':domain,'valid':valid,'depends':deps, **attributes}
        if nodes.get(key)!=v:
            if key in nodes:
                gr['history'].append({'claim_id':key,'prior_revision':gr['revision'],
                                      'previous':nodes[key]})
            gr['revision']+=1
            nodes[key]=v
        return key

    def _revoke(self,s, key,reason):
        graph=s['s21']; nodes=graph['nodes']; visited=set(); todo=[key]; revoked=[]
        while todo:
            current=todo.pop()
            if current in visited:continue
            visited.add(current)
            if current in nodes and nodes[current]['valid']:
                grnode=nodes[current]
                graph['history'].append({'claim_id':current,'prior_revision':graph['revision'],
                                         'previous':dict(grnode)})
                grnode['valid']=False;grnode['revoked_reason']=reason
                graph['revision']+=1;revoked.append(current)
            todo.extend(k for k,node in nodes.items() if current in node.get('depends',[]) and node['valid'])
        return revoked

    def _synchronize(self,s):
        """Project actual specialist receipts into ONE typed, dependent public graph.
        Never read host hidden variants or physics to make a policy decision.
        """
        gr=s['s21']; sen=self.sensor.agent.state(); att=sen.get('s19_provenance_attestation')
        for obs in sen.get('evidence',[]):
            key='source:receipt:'+obs['receipt_id']
            self._node(s,key,'observation','source',value=obs['value'],radius=obs.get('radius',0),channel=obs['channel'])
        if att and sen['status']=='DONE':
            deps=['source:receipt:'+rid for rid in att['basis_receipts']]
            deps=[key for key in deps if key in gr['nodes']]
            if len(deps)==len(att['basis_receipts']):
                self._node(s,'source:attestation','derived_source_basis','source',depends=deps,
                           roots=att['roots'],status=att['status'])
        if not att and sen['status']=='DONE':
            # S19 does not issue a D attestation for already-separated B/C roots.
            # A positive result must still have explicit receipt-backed grounds.
            roots=self.contract['provenance_roots']
            b=[x for x in sen['evidence'] if x['channel']=='B']
            c=[x for x in sen['evidence'] if x['channel']=='C']
            if (roots.get('B') and roots.get('C') and roots['B']!=roots['C']
                and len(b)==2 and len(c)==2):
                deps=['source:receipt:'+x['receipt_id'] for x in b+c]
                self._node(s,'source:attestation','derived_source_basis','source',depends=deps,
                           roots={'B':roots['B'],'C':roots['C']},status='DECLARED_DIFFERENT_ROOTS')
        ast=self.act.snapshot(); a=ast['state']
        if a.get('pool') is not None:
            previous=gr['nodes'].get('actuator:model')
            current={'kind':'model_state','domain':'actuator','valid':True,'depends':[],
                     'task':a.get('task_id'),'context':a.get('context'),'pool':a.get('pool')}
            if previous and previous!=current:
                removed=self._revoke(s,'actuator:model','MODEL_REVISED')
                if removed:self._record(s,'S21_MODEL_DEPENDENCIES_REVOKED',revoked=removed)
            self._node(s,'actuator:model','model_state','actuator',
                       task=a.get('task_id'),context=a.get('context'),pool=a.get('pool'))
        if ('source:attestation' in gr['nodes'] and gr['nodes']['source:attestation']['valid']
            and not gr['late']['announced']):
            deps=['source:attestation']
            if 'actuator:model' in gr['nodes']:deps.append('actuator:model')
            self._node(s,'decision:actuator_authorization','decision_basis','cross_domain',depends=deps)
            gr['permission']={'status':'VALID','basis':deps,'revision':gr['revision']}
        if gr['late']['state']=='VALIDATED' and 'source:E_challenge' in gr['nodes']:
            deps=['source:E_challenge']+(['actuator:model'] if 'actuator:model' in gr['nodes'] else [])
            self._node(s,'decision:actuator_authorization','decision_basis','cross_domain',depends=deps)
            gr['permission']={'status':'VALID','basis':deps,'revision':gr['revision']}
        return gr

    def announce_E(self, event_id):
        """Environment emits a public observation that E has become available.
        No truth label, world variant, preferred result or new task is supplied.
        """
        if not isinstance(event_id,str) or not event_id.strip():raise ValueError('event_id required')
        s=self.state();gr=s['s21']
        if gr['late']['announced']:
            if gr['late']['event_id']!=event_id:raise ValueError('second E announcement needs new episode')
            return
        if not s['actuator_calibrated'] or self.sensor.agent.state()['status']!='DONE':
            raise ValueError('late source must arrive after initial attestation and novelty')
        if s['phase']!='ACTIVE':raise ValueError('late source must arrive before episode terminates')
        gr['late']={'announced':True,'event_id':event_id,'readings':[], 'state':'OPEN',
                    'origin':'public_new_source_available'}
        gr['questions'].append({'id':'q_late_E','origin':'public newly observed source',
                                'question':'Does a separate new measurement alter present grounds?', 'status':'ACTIVE'})
        self._node(s,'event:'+event_id,'observed_source_availability','source',root=self.late_root)
        gr['permission']={'status':'SUSPENDED','basis':['event:'+event_id],'revision':gr['revision']}
        s['worldview']['cross_domain_gate']='SUSPENDED_NEW_EVIDENCE'
        self._record(s,'S21_SOURCE_APPEARED',event_id=event_id)
        s['worldview_version']+=1;self.save(s)

    def _late_step(self,s):
        gr=s['s21'];late=gr['late']; k=len(late['readings'])
        if not self.late_enabled:
            late['state']='ABLATED'; gr['questions'][-1]['status']='ABLATED'
            self._record(s,'S21_LATE_CHECK_DISABLED')
            gr['permission']={'status':'UNCHECKED','basis':[], 'revision':gr['revision']}
            s['worldview']['cross_domain_gate']='ACCEPTED_DECLARED_SOURCES'
        elif self.late_root in (None,'') or self.late_root in self.contract['provenance_roots'].values():
            late['state']='UNIDENTIFIABLE';gr['questions'][-1]['status']='OPEN_UNRESOLVED'
            gr['permission']={'status':'DENIED','basis':[], 'revision':gr['revision']}
            s['worldview']['cross_domain_gate']='DENIED_SHARED_ROOT'
            s['phase']='SAFE_HOLD'
            self._record(s,'S21_E_NOT_INDEPENDENT_BY_DECLARED_LINEAGE')
        elif s['shared_budget']<2:
            late['state']='BUDGET_STOP';gr['questions'][-1]['status']='OPEN_UNRESOLVED'
            s['phase']='BUDGET_STOP'
            gr['permission']={'status':'DENIED','basis':[], 'revision':gr['revision']}
            self._record(s,'S21_BUDGET_INSUFFICIENT_FOR_NEW_EVIDENCE')
        elif k<2:
            # Sensor E's private observations are consumed via receipt, not copied into agent contract.
            obs={'channel':'E','value':self._late_values[k], 'radius':0,
                 'receipt_id':f'{late["event_id"]}:E:{k+1}', 'root':self.late_root}
            key='source:receipt:'+obs['receipt_id']
            self._node(s,key,'observation','source',value=obs['value'],radius=0,channel='E',root=self.late_root)
            late['readings'].append(obs);s['shared_budget']-=2
            self._record(s,'S21_E_MEASURED',receipt_id=obs['receipt_id'],value=obs['value'],cost=2)
            if k==1:
                # Compare against observed D readings, not the hidden physical law.
                old=[x for x in self.sensor.agent.state()['evidence'] if x['channel']=='D']
                if len(old)!=2:raise AssertionError('missing acknowledged D readings')
                vals=[v['value'] for v in late['readings']]
                normal=abs(vals[0]-vals[1])<=0 and all(abs(z['value']-vals[0])<=z.get('radius',0) for z in old)
                if normal:
                    deps=['source:attestation']+[f'source:receipt:{x["receipt_id"]}' for x in late['readings']]
                    self._node(s,'source:E_challenge','cross_check','source',depends=deps,status='CONSISTENT')
                    if 'actuator:model' in gr['nodes']:deps+=['actuator:model']
                    self._node(s,'decision:actuator_authorization','decision_basis','cross_domain',depends=['source:E_challenge']+(['actuator:model'] if 'actuator:model' in gr['nodes'] else []))
                    gr['permission']={'status':'VALID','basis':['source:E_challenge'],'revision':gr['revision']}
                    s['worldview']['cross_domain_gate']='ACCEPTED_EXTENDED_EVIDENCE'
                    late['state']='VALIDATED';gr['questions'][-1]['status']='RESOLVED'
                    self._record(s,'S21_NEW_EVIDENCE_CONFIRMED',values=vals)
                elif vals[0]!=vals[1]:
                    # Competing readings do not demonstrate a stable counter-model.
                    # Suspend decision without falsely revoking the older attestation.
                    gr['permission']={'status':'DENIED_UNIDENTIFIED','basis':[f'source:receipt:{x["receipt_id"]}' for x in late['readings']],
                                      'revision':gr['revision']}
                    s['worldview']['cross_domain_gate']='SUSPENDED_UNSTABLE_E'
                    late['state']='INCONSISTENT';gr['questions'][-1]['status']='OPEN_UNRESOLVED'
                    s['phase']='SAFE_HOLD'
                    self._record(s,'S21_E_SELF_CONTRADICTION',values=vals)
                else:
                    revoked=self._revoke(s,'source:attestation','LATE_CONTRADICTING_EVIDENCE')
                    gr['permission']={'status':'REVOKED','basis':revoked,'revision':gr['revision']}
                    s['worldview']['cross_domain_gate']='DENIED_NEW_EVIDENCE'
                    late['state']='CONTRADICTION';gr['questions'][-1]['status']='OPEN_UNRESOLVED'
                    s['phase']='SAFE_HOLD'
                    self._record(s,'S21_DEPENDENCY_INVALIDATION',revoked=revoked,values=vals)
        s['tick']+=1
        s['self_coordinate']={'tick':s['tick'],'active_question':'q_late_E',
            'remaining_global_budget':s['shared_budget'],
            'source_status':self.sensor.agent.state()['status'],
            'novelty_seen':s['novelty_event_id'] is not None}
        s['worldview_version']+=1
        self.save(s)

    def step(self):
        s=self.state()
        if s['phase']!='ACTIVE':return self.snapshot()
        if s['inflight']:raise RuntimeError('cross-database S20 inflight; reconcile manually')
        late=s['s21']['late']
        if late['announced'] and late['state']=='OPEN':
            self._late_step(s)
            return self.snapshot()
        if s['s21']['permission']['status'] in ('REVOKED','DENIED','SUSPENDED','DENIED_BUDGET','DENIED_UNIDENTIFIED'):
            s['phase']='SAFE_HOLD';self.save(s);return self.snapshot()
        if (s['actuator_calibrated'] and self.sensor.agent.state()['status']=='DONE'
            and s['s21']['permission']['status'] not in ('VALID','UNCHECKED')):
            s['phase']='SAFE_HOLD';s['worldview']['cross_domain_gate']='DENIED_NO_VALID_CROSS_DOMAIN_GROUND'
            self._record(s,'S21_MISSING_CROSS_DOMAIN_GROUND')
            self.save(s);return self.snapshot()
        result=super().step()
        s=self.state()
        self._synchronize(s)
        if s['phase']=='BUDGET_STOP':
            revoked=self._revoke(s,'decision:actuator_authorization','GLOBAL_BUDGET_INSUFFICIENT')
            s['s21']['permission']={'status':'DENIED_BUDGET','basis':revoked,'revision':s['s21']['revision']}
            self._record(s,'S21_BUDGET_PERMISSION_REVOKED',revoked=revoked)
        self.save(s)
        return self.snapshot()

    def snapshot(self):
        ans=super().snapshot()
        # Copy projection without leaking host-only world parameters.
        ans['shared_worldview']=ans['controller']['s21']
        return ans
