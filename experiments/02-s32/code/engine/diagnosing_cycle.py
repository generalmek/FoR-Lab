"""Calibrated evidence in the living loop; explicit finite sensor contract.

Trusted reference inputs and an affine, stationary-between-checks sensor are
assumptions, not conclusions about arbitrary real sensors. Receiver receipts
remain independently observed physical outcomes in this simulator.
"""
import json
from living_cycle import LivingCycle
from uncertain_runtime import UncertainWorld
from funded_runtime import ResourceDenied


class ReferenceWorld(UncertainWorld):
    def __init__(self,*args,gain=1,bias=0,reference_trusted=True,**kwargs):
        super().__init__(*args,**kwargs)
        self.channel_gain=gain
        self.channel_bias=bias
        self.reference_trusted=reference_trusted

    def channel(self,value):
        return self.channel_gain*value+self.channel_bias

    def observation(self,probe):
        if probe.startswith('C'):
            value=self.channel(int(probe[1:]))
            self.db.execute('INSERT INTO observation_metadata VALUES(?,?,?)',
                            (self.measurement_key,self.now(),self.error_bound))
            return value
        return self.channel(super().observation(probe))


class DiagnosingCycle(LivingCycle):
    def start_cycle(self,world,*args,**kwargs):
        super().start_cycle(world,*args,**kwargs)
        s=self.state()
        s.update(calibration=None,calibration_epoch=0,diagnostic_seq=0)
        with self.db:self.save(s)

    def prepare_step(self,world,life):
        s=self.state()
        if not isinstance(world,ReferenceWorld):
            raise ValueError('explicit reference-channel contract required')
        # Reserve one operation after the diagnostic, never reset the life budget.
        reason=None
        if not world.reference_trusted:reason='UNTRUSTED_REFERENCE'
        elif world.error_bound!=0:reason='UNCERTAIN_CALIBRATION_UNRESOLVED'
        elif s['budget']<4:reason='DIAGNOSTIC_BUDGET_EXHAUSTED'
        if reason:
            with self.db:
                s.update(phase='HALT',reason=reason,calibration=None)
                self.event(s,'DIAGNOSIS_UNRESOLVED',reason=reason,
                           alternatives=['process','sensor','joint','outside-contract'])
                self.save(s)
            return False
        seq=s.get('diagnostic_seq',0)
        evidence=[]
        try:
            for reference in (0,1,2):
                key=f"{world.receiver_id}:cal:{s['task_id']}:{seq}:{reference}"
                world.measurement_key=key
                value=world.measure('C'+str(reference))
                evidence.append(dict(reference=reference,raw=value,operation_id=key,
                                     receiver_id=world.receiver_id,**world.metadata(key)))
        except ResourceDenied:
            # Completed, durable reference receipts are charged even on partial failure.
            with self.db:
                s['budget']-=len(evidence)
                s.update(phase='HALT',reason='DIAGNOSTIC_RESOURCE_EXHAUSTED',calibration=None)
                self.event(s,'DIAGNOSIS_UNRESOLVED',evidence=evidence)
                self.save(s)
            return False
        bias=evidence[0]['raw'];gain=evidence[1]['raw']-bias
        valid=gain in (1,2,3) and bias in range(-5,6) and evidence[2]['raw']==2*gain+bias
        old=s.get('calibration')
        with self.db:
            s['budget']-=3;s['diagnostic_seq']=seq+1
            self.event(s,'REFERENCE_CHECK',evidence=evidence,fit=[0,1],validation=[2],
                       valid=valid,scope='affine channel; trusted references; zero declared noise')
            if not valid:
                s.update(phase='HALT',reason='SENSOR_OUTSIDE_CONTRACT',calibration=None)
                self.save(s);return False
            changed=old is not None and (old['gain'],old['bias'])!=(gain,bias)
            if old is None or changed:s['calibration_epoch']+=1
            s['calibration']=dict(gain=gain,bias=bias,epoch=s['calibration_epoch'],
                                  evidence=evidence,checked_at=world.now())
            if changed:
                # Process hypotheses were fitted to CORRECTED evidence; retain them.
                # Require a fresh local observation rather than relabelling sensor drift
                # as process drift. No model revision is manufactured here.
                s.update(evidence=[],validation_probe=None,generation=s['generation']+1)
                self.db.execute("UPDATE beliefs SET version=version+1 WHERE name='sensor'")
                for name,deps in self.db.execute('SELECT name,deps FROM forecasts').fetchall():
                    if 'sensor' in json.loads(deps):
                        self.db.execute('UPDATE forecasts SET valid=0 WHERE name=?',(name,))
                self.event(s,'SENSOR_REVISED',before=old,after=s['calibration'],
                           process_pool_preserved=True)
            self.save(s)
        return True

    def commit_complete_evidence(self,s):
        calibration=s.get('calibration')
        if calibration is None:raise RuntimeError('uncalibrated observation')
        e=s['evidence'][-1];raw=e['value']
        e.update(value=(raw-calibration['bias'])/calibration['gain'],raw=raw,
                 calibration_epoch=calibration['epoch'],
                 calibration_operations=[x['operation_id'] for x in calibration['evidence']],
                 receiver_id=self.active_world.receiver_id,
                 operation_id=self.active_world.measurement_key)
        super().commit_complete_evidence(s)

    def permit(self,u):
        s=self.state();cal=s.get('calibration')
        if not cal or cal['checked_at']!=s.get('now'):return None
        local=self.latest(s,'U'+str(u))
        if not local or local.get('calibration_epoch')!=cal['epoch']:return None
        p=super().permit(u)
        if p:
            p.update(calibration_epoch=cal['epoch'],
                     calibration_operations=[x['operation_id'] for x in cal['evidence']],
                     observation_operation=local['operation_id'])
        return p
