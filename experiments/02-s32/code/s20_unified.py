"""S20 first *limited* integrated loop.
One persistent research agenda, self-coordinate, budget and cross-domain decision.
Delegates remain specialized S16/S19 engines; this is NOT yet a single fully
shared semantic worldview, which is reported as an explicit open requirement.
Host-private physics stays in the two virtual receiver components. No shell/network.
"""
import json
import sqlite3
from pathlib import Path
from s16_integrated import S16Experiment
from s19_integrated import S19Experiment


def canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True)

class S20Unified:
    def __init__(self,path,source,*,sensor_variant='bias_A',d_values=(12,12),
                 provenance_roots=None,provenance_enabled=True,world_variant='stable_u3_exception',
                 budget=240,phase_interleave=True):
        self.root=Path(path);self.root.mkdir(parents=True,exist_ok=True)
        self.private_contract={'sensor_variant':sensor_variant,'d_values':list(d_values),
                               'world_variant':world_variant}
        self.contract={'provenance_roots':provenance_roots or
                        {'B':'shared-calibration','C':'shared-calibration','D':'distinct'},
                       'provenance_enabled':provenance_enabled,'budget':budget,
                       'phase_interleave':phase_interleave}
        self.host_db=sqlite3.connect(self.root/'s20_host.sqlite')
        self.host_db.execute('CREATE TABLE IF NOT EXISTS private_contract(id INTEGER PRIMARY KEY,body TEXT)')
        prior=self.host_db.execute('SELECT body FROM private_contract WHERE id=1').fetchone()
        if prior and json.loads(prior[0])!=self.private_contract:
            self.host_db.close();raise ValueError('S20 private world changed on restart')
        if prior is None:
            with self.host_db:self.host_db.execute('INSERT INTO private_contract VALUES(1,?)',
                                                    (canonical(self.private_contract),))
        self.conn=sqlite3.connect(self.root/'s20_agent.sqlite')
        self.conn.executescript('''CREATE TABLE IF NOT EXISTS s20_state(id INTEGER PRIMARY KEY CHECK(id=1),body TEXT NOT NULL);
           CREATE TABLE IF NOT EXISTS s20_contract(id INTEGER PRIMARY KEY CHECK(id=1),body TEXT NOT NULL);''')
        old=self.conn.execute('SELECT body FROM s20_contract WHERE id=1').fetchone()
        if old and json.loads(old[0])!=self.contract:
            self.conn.close();self.host_db.close();raise ValueError('S20 public contract changed during restart')
        self.act=S16Experiment(self.root/'actuator',world_variant=world_variant)
        self.sensor=S19Experiment(self.root/'sensors',source,variant=sensor_variant,d_values=d_values,
            provenance_roots=self.contract['provenance_roots'],
            provenance_enabled=provenance_enabled,budget=20)
        if old is None:
            self.act.start_episode('exploration',160)
            initial={'phase':'ACTIVE','tick':0,'shared_budget':budget,'worldview_version':0,
                     'self_coordinate':{},'question_agenda':[
                         {'id':'q_actuator','origin':'public goal plus observation','status':'ACTIVE','priority':2},
                         {'id':'q_source','origin':'observed source discrepancy','status':'ACTIVE','priority':3}],
                     'worldview':{'actuator':None,'source':None,'cross_domain_gate':'PENDING'},
                     'actuator_calibrated':False,'novelty_event_id':None,'actuator_receipts_before_novelty':None,
                     'events':[],'inflight':False}
            with self.conn:
                self.conn.execute('INSERT INTO s20_contract VALUES(1,?)',(canonical(self.contract),))
                self.conn.execute('INSERT INTO s20_state VALUES(1,?)',(canonical(initial),))
        self._closed=False
    def close(self):
        if self._closed:return
        self.sensor.close();self.act.close();self.conn.close();self.host_db.close();self._closed=True
    def state(self):return json.loads(self.conn.execute('SELECT body FROM s20_state WHERE id=1').fetchone()[0])
    def save(self,s):
        with self.conn:self.conn.execute('UPDATE s20_state SET body=? WHERE id=1',(canonical(s),))
    def _record(self,s,kind,**detail):s['events'].append(dict(tick=s['tick'],kind=kind,**detail))
    def snapshot(self):
        a=self.act.snapshot();sen=self.sensor.snapshot();s=self.state()
        return {'controller':s,'actuator':{'life':(a['life']or{}).get('status'),
                'phase':a['state']['phase'],'budget':a['state'].get('budget'),
                'context':a['state'].get('context'),'reason':a['state'].get('reason'),
                'completed':a['config'].get('completed_contexts'),
                'research_status':a['config'].get('research_status'),
                'receipts':len(a['receipts']),'resource_balance':a['balance'],
                's16_program':a['state'].get('s16_program')},
            'sensor':{'status':sen['state']['status'],'phase':sen['state']['phase'],
                'reason':sen['state'].get('reason'),'budget':sen['state']['budget'],
                's19_attestation':sen['state'].get('s19_provenance_attestation'),
                'action_receipt':sen['state'].get('action_receipt'),
                'readings':len(sen['sensor_readings'])}}
    def step(self):
        s=self.state()
        if s['phase']!='ACTIVE':return self.snapshot()
        if s['inflight']:raise RuntimeError('S20 unfinished tick; reconcile before replay; no silent action duplication')
        s['inflight']=True;self.save(s)
        try:
            a=self.act.snapshot();sen=self.sensor.snapshot();status=sen['state']['status']
            calibrated=s['actuator_calibrated']
            if not calibrated:
                choice='sensor' if status=='ACTIVE' and self.contract['phase_interleave'] and s['tick']%2==0 else 'actuator'
            elif status=='ACTIVE':choice='sensor'
            elif status=='STOPPED':choice='safe_hold'
            else:choice='actuator'
            # Reserve an upper bound for one currently supported atomic tick.
            # An operation with a larger declared cost must not run via this adapter.
            if s['shared_budget']<8:choice='no_budget'
            if choice=='no_budget':
                s['phase']='BUDGET_STOP';self._record(s,'S20_BUDGET_STOP')
            elif choice=='safe_hold':
                s['phase']='SAFE_HOLD'
                s['worldview']['source']={'status':'UNRESOLVED','reason':sen['state'].get('reason')}
                s['worldview']['cross_domain_gate']='DENIED_SOURCE_INSUFFICIENT'
                self._record(s,'S20_CROSS_DOMAIN_COMPASS_DENIED',reason=sen['state'].get('reason'))
            elif choice=='sensor':
                before=sen['state']['budget']
                after=self.sensor.step()
                used=max(0,before-after['state']['budget'])
                s['shared_budget']-=used
                if used or after['state']['status']!='ACTIVE':
                    s['worldview_version']+=1
                    s['worldview']['source']={'status':after['state']['status'],
                        'last_receipt':after['state']['evidence'][-1]['receipt_id'] if after['state']['evidence'] else None,
                        'reason':after['state'].get('reason'),'attestation':after['state'].get('s19_provenance_attestation')}
                if after['state']['status']!='ACTIVE':
                    accepted=after['state']['status']=='DONE'
                    s['worldview']['cross_domain_gate']='ACCEPTED_DECLARED_SOURCES' if accepted else 'DENIED_SOURCE_INSUFFICIENT'
                    s['question_agenda'][1]['status']='RESOLVED' if accepted else 'OPEN_UNRESOLVED'
                self._record(s,'S20_SENSOR_STEP',status=after['state']['status'],used=used)
            elif choice=='actuator':
                # The common inquiry/Compass scheduler never calls the actuator
                # after calibration unless the source inquiry has reached DONE.
                if calibrated and sen['state']['status']!='DONE':
                    raise AssertionError('S20 attempted actuator continuation without evidence basis')
                before=a['state'].get('budget',0)
                after=self.act.step();used=max(0,before-after['state'].get('budget',0))
                s['shared_budget']-=used
                if used or after['state'].get('task_id')!=a['state'].get('task_id'):
                    s['worldview_version']+=1
                    s['worldview']['actuator']={'task':after['state'].get('task_id'),
                        'phase':after['state']['phase'],'model_pool':after['state'].get('pool'),
                        'last_event':after['records']['events'][-1]['body']['kind'] if after['records']['events'] else None}
                self._record(s,'S20_ACTUATOR_STEP',phase=after['state']['phase'],used=used)
                if not calibrated and self.act.finished(after):
                    if (after['life']or{}).get('status')!='DONE':
                        s['phase']='PRETRAINING_FAILED'
                    else:
                        # Host adds observable context event, private process change is
                        # hidden from candidate. No user intervention between ticks.
                        eid=self.act.observe_context(4)
                        self.act.intervention('process')
                        s['actuator_calibrated']=True;s['novelty_event_id']=eid
                        s['actuator_receipts_before_novelty']=len(after['receipts'])
                        self._record(s,'S20_NOVELTY_OBSERVED',event_id=eid)
                elif calibrated and self.act.finished(after):
                    s['question_agenda'][0]['status']='RESOLVED' if (after['life']or{}).get('status')=='DONE' else 'OPEN_UNRESOLVED'
                    s['phase']='DONE' if (after['life']or{}).get('status')=='DONE' else 'ACTUATOR_STOP'
            s['tick']+=1
            s['self_coordinate']={'tick':s['tick'],'active_question':choice,
                'remaining_global_budget':s['shared_budget'],
                'source_status':self.sensor.agent.state()['status'],
                'novelty_seen':s['novelty_event_id'] is not None}
            if s['tick']>=140 and s['phase']=='ACTIVE':s['phase']='STEP_LIMIT'
            if s['shared_budget']<0:s['phase']='BUDGET_ACCOUNTING_ERROR'
            s['inflight']=False;self.save(s)
        except BaseException:
            # Do NOT clear inflight in this failure path: cross-store transaction
            # is not atomic; manual inspection before any re-execution is required.
            raise
        return self.snapshot()
    def run(self,cap=140):
        for _ in range(cap):
            x=self.step()
            if x['controller']['phase']!='ACTIVE':return x
        raise RuntimeError('S20 exceeded run cap')
