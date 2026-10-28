"""S25: common action gateway for the existing S16 and S24 physical paths.

Physical calls to apply_once from BOTH paths go through an S25 gate; S16
calibration remains an explicit limited bootstrap exception. No hidden physics
are passed to the pure adjudicator. Adjudication is re-evaluated before every
call, including the retry after a crash.
"""
import json
from s24_unified import S24Unified,S24Actuator,S24Receiver
from s25_gate import authorize,ActionDenied
from s20_unified import canonical

class GatedActuator(S24Actuator):
    def __init__(self,*args,**kwargs):
        self.gateway=None
        super().__init__(*args,**kwargs)
    def open_engine(self):
        agent,world=super().open_engine()
        physical=world.apply_once
        def guarded(op,u,expected):
            if self.gateway is None:raise ActionDenied('MISSING_COMMON_EXECUTION_GATE')
            self.gateway(op,u,expected)
            return physical(op,u,expected)
        world.apply_once=guarded
        return agent,world

class S25Unified(S24Unified):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        prior=self.act
        try:
            physics_variant=self.s24_physics_variant()
            prior.close()
            self.act=GatedActuator(self.root/'actuator',variant=physics_variant)
            self.act.gateway=self._physical_gate
            self.probe_receiver.act=self.act
            self._s25_token=None
            self.conn.execute('''CREATE TABLE IF NOT EXISTS s25_gate_log
                (op TEXT PRIMARY KEY,route TEXT,control INTEGER,prediction REAL,proof TEXT,decision TEXT)''')
            state=self.state()
            if 's25' not in state:
                state['s25']={'language':'common_action_authorizer_v1',
                              'status':'ACTIVE','last_proof':None,'outcomes_seen':0}
                self.save(state)
            elif state['s25']['language']!='common_action_authorizer_v1':
                raise ValueError('S25 public contract changed')
        except BaseException:
            self.close();raise
    def s24_physics_variant(self):
        # Host-only: read private contract from its host DB (never candidate state).
        row=self.act.host.execute('SELECT variant FROM s24_epoch WHERE id=1').fetchone()
        if not row:raise ValueError('missing private S24 variant')
        return row[0]
    def _physical_gate(self,op,u,expected):
        s=self.state()
        # S16 pretraining actions are bounded experiments before source certification.
        # Explicitly NOT counted as an S25 full cross-domain authorization.
        if not s['actuator_calibrated']:
            if s['s24']['status']!='IDLE' or s['phase']!='ACTIVE':raise ActionDenied('BOOTSTRAP_SCOPE_INVALID')
            proof={'route':'bootstrap','control':u,'expected':expected,
                   'decision':'PRECALIBRATION_ONLY','worldview_revision':s['s22']['revision']}
        else:
            route='revised' if self._s25_token else 'legacy'
            evidence=self.act.snapshot()['state'].get('evidence',[]) if route=='legacy' else None
            proof=authorize(s,route=route,operation_id=op,control=u,expected=expected,
                output_floor=self.act.output_floor,current_context=self.act.snapshot()['state']['context'],
                local_token=self._s25_token,legacy_evidence=evidence)
        old=self.conn.execute('SELECT route,control,prediction,proof FROM s25_gate_log WHERE op=?',(op,)).fetchone()
        if old:
            if old[:3]!=(proof['route'],u,expected):raise ActionDenied('IMMUTABLE_OPERATION_REUSED')
        else:
            with self.conn:
                self.conn.execute('INSERT INTO s25_gate_log VALUES(?,?,?,?,?,?)',
                    (op,proof['route'],u,expected,canonical(proof),'PERMITTED'))
        return proof
    def _act(self,s):
        a=s['s24']['action']
        self._s25_token=(a['id'],a['control'],a['expected']) if a else None
        try:
            result=super()._act(s)
            committed=self.state()
            receipt=committed['s24']['action']
            if receipt and receipt.get('outcome') and committed['s25'].get('outcome_operation')!=receipt['id']:
                committed['s25']['outcome_operation']=receipt['id']
                committed['s25']['outcomes_seen']+=1
                row=self.conn.execute('SELECT proof FROM s25_gate_log WHERE op=?',(receipt['id'],)).fetchone()
                committed['s25']['last_proof']=json.loads(row[0]) if row else None
                self.save(committed)
                with self.conn:
                    self.conn.execute('UPDATE s25_gate_log SET decision=? WHERE op=?',
                        ('EFFECT_RECEIPTED',receipt['id']))
            return result
        finally:self._s25_token=None
    def snapshot(self):
        x=super().snapshot()
        if 's25' in x['controller']:
            x['action_gateway']=x['controller']['s25']
        return x
