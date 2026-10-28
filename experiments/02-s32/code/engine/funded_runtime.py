"""One persistent resource for inquiry and action; synchronous simulation only."""
import json
from pathlib import Path
from datetime import datetime, timezone
from continuous_campaign import ResourceWorld
from native_incubator import NativeWorld
from research_choice import ResearchChoice


class ResourceDenied(RuntimeError):
    """Receiver rejected atomically, with no effect and no debit."""


class FundedWorld(ResourceWorld):
    def __init__(self,path,law,context,initial=80,reserve=5,local_price=1,sample_price=1):
        super().__init__(path,law,context,initial)
        if any(type(x) is not int or x<=0 for x in (local_price,sample_price)):
            raise ValueError('invalid price')
        self.reserve=reserve;self.local_price=local_price;self.sample_price=sample_price
        self.measurement_key=None
        self.db.execute('CREATE TABLE IF NOT EXISTS measurements(id TEXT PRIMARY KEY,probe TEXT,value INTEGER,cost INTEGER)')
        self.db.commit()

    def balance(self):
        return super().balance()-self.db.execute('SELECT COALESCE(SUM(cost),0) FROM measurements').fetchone()[0]

    def price(self,probe):return self.local_price if probe.startswith('U') else self.sample_price

    def observation(self,probe):return NativeWorld.measure(self,probe)

    def outcome(self,cost,target):
        return dict(observed=cost,physical=cost,harm=int(cost!=target))

    def measurement_receipt(self,key):
        return self.db.execute('SELECT probe,value,cost FROM measurements WHERE id=?',(key,)).fetchone()

    def measure(self,probe):
        if self.measurement_key is None:raise ValueError('measurement needs durable operation key')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            row=self.db.execute('SELECT probe,value FROM measurements WHERE id=?',(self.measurement_key,)).fetchone()
            if row:
                if row[0]!=probe:raise ValueError('measurement key reused')
                value=row[1]
            else:
                cost=self.price(probe)
                if self.balance()-cost<self.reserve:raise ResourceDenied('measurement would breach reserve')
                value=self.observation(probe)
                self.db.execute('INSERT INTO measurements VALUES(?,?,?,?)',(self.measurement_key,probe,value,cost))
            self.db.commit();return value
        except BaseException:self.db.rollback();raise

    def apply_once(self,op,u,target):
        request=json.dumps([u,target]);self.db.execute('BEGIN IMMEDIATE')
        try:
            row=self.db.execute('SELECT request,result FROM receipts WHERE id=?',(op,)).fetchone()
            if row:
                if row[0]!=request:raise ValueError('operation key reused')
                result=json.loads(row[1])
            else:
                cost=self.physical(u)
                if cost<0 or self.balance()-cost<self.reserve:raise ResourceDenied('actuator resource interlock')
                result=self.outcome(cost,target)
                self.db.execute('INSERT INTO receipts VALUES(?,?,?)',(op,request,json.dumps(result)))
            self.db.commit();return result['observed']
        except BaseException:self.db.rollback();raise


class FundedRuntime(ResearchChoice):
    def start_funded(self,world,deliverable='action',budget=16):
        self.start_choice(world.context,world.balance(),world.reserve,deliverable=deliverable,
                          local_price=world.local_price,sample_price=world.sample_price,budget=budget)
        s=self.state();s.pop('resource_stop',None)
        with self.db:self.save(s)

    def choose_plan(self,s,models):
        if s.get('force_fresh_model') and not s['native_stored']:
            seen={e['probe'] for e in s['evidence']}
            required=[f'T{i}' for i in range(6)]+[f'V{i}' for i in range(3)]
            remaining=sum(p not in seen and p!=s.get('prepaid_probe') for p in required)
            minimum=remaining*s['sample_price']+s['local_price']
            if s['available']-minimum<s['reserve']:
                s['resource_stop']='INSUFFICIENT_RESOURCE_TO_COMPLETE'
                self.event(s,'RESEARCH_COMPLETION_UNAFFORDABLE',minimum=minimum,available=s['available'])
                return ('HALT',None),'cannot-afford-required-evidence'
        choice,reason=super().choose_plan(s,models)
        if choice[0]=='PROBE':
            cost=s['local_price'] if choice[1].startswith('U') else s['sample_price']
            if s.get('prepaid_probe')==choice[1]:cost=0
            if s['available']-cost<s['reserve']:
                s['resource_stop']='INQUIRY_RESOURCE_LIMIT'
                self.event(s,'INQUIRY_RESOURCE_STOP',probe=choice[1],cost=cost,available=s['available'])
                return ('HALT',None),'inquiry-would-breach-reserve'
        return choice,reason

    def step(self,world,fail_at=None):
        s=self.state()
        if s['phase'] in ('IDLE','DONE','HALT'):return s
        if s['context']!=world.context:raise ValueError('context changed')
        # Key survives crash after measurement receipt but before agent evidence commit.
        world.measurement_key=f"{world.receiver_id}:{s['task_id']}:{s['generation']}:{len(s['evidence'])}"
        receipt=world.measurement_receipt(world.measurement_key)
        s.update(available=world.balance(),local_price=world.local_price,sample_price=world.sample_price,
                 prepaid_probe=receipt[0] if receipt else None)
        with self.db:self.save(s)
        try:
            result=super().step(world,fail_at=fail_at)
            if result['phase']=='HALT' and result.get('resource_stop'):
                with self.db:
                    result['reason']=result['resource_stop'];self.save(result)
            return result
        except ResourceDenied as error:
            # Only this receiver's atomic NO-EFFECT rejection is safe to cancel.
            with self.db:
                s=self.state();s.update(phase='HALT',reason='RESOURCE_INTERLOCK',available=world.balance())
                self.db.execute("UPDATE intents SET status='cancelled' WHERE status='pending'")
                self.event(s,'RECEIVER_RESOURCE_DENIED',detail=str(error));self.save(s)
            return s


def run(root):
    root.mkdir(parents=True,exist_ok=False)
    rows=[]
    for initial,price in ((80,1),(20,2),(7,3)):
        for episode,deliverable in enumerate(('model_and_action','action','action','model_and_action')):
            w=FundedWorld(root/f'w-{initial}.sqlite',lambda u,v:1+2*u+u*v,1,initial=initial,
                          local_price=price,sample_price=price)
            r=FundedRuntime(root/f'a-{initial}.sqlite')
            try:
                before=w.balance();r.start_funded(w,deliverable);s=r.run(w)
                row=dict(initial=initial,price=price,episode=episode,deliverable=deliverable,
                         phase=s['phase'],before=before,after=w.balance(),probes=len(s['evidence']),
                         model_stored=s['native_stored'],reason=s.get('reason'),breach=w.balance()<5)
                rows.append(row)
            finally:r.close();w.close()
    (root/'results.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
    return rows


if __name__=='__main__':
    root=Path(__file__).resolve().parent/'runs'/datetime.now(timezone.utc).strftime('funded-%Y%m%dT%H%M%S%fZ')
    print(json.dumps(run(root),indent=2));print(root)
