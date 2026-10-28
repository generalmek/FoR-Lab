"""Durable intents + idempotent simulated receiver; not a real actuator guarantee."""
import json
import sqlite3
import uuid
from decision_runtime import DecisionRuntime
from conflict_diagnosis import predicted

class ReceiptWorkshop:
    """Physical state and receipt are one transaction in this SIMULATED world."""
    supports_idempotency=True
    def __init__(self,path,gain=2,bias=0):
        self.gain,self.bias=gain,bias
        self.db=sqlite3.connect(str(path))
        self.db.execute('CREATE TABLE IF NOT EXISTS receipts(id TEXT PRIMARY KEY,request TEXT,result TEXT)')
        self.db.execute('CREATE TABLE IF NOT EXISTS receiver_identity(id TEXT PRIMARY KEY)')
        if not self.db.execute('SELECT 1 FROM receiver_identity').fetchone():
            self.db.execute('INSERT INTO receiver_identity VALUES(?)',(str(uuid.uuid4()),))
        self.db.commit()
        self.receiver_id=self.db.execute('SELECT id FROM receiver_identity').fetchone()[0]
    def lookup(self,op):
        row=self.db.execute('SELECT result FROM receipts WHERE id=?',(op,)).fetchone()
        return json.loads(row[0]) if row else None
    def measure(self,p):
        return self.bias if p=='CAL' else self.physical(int(p[1:]))+self.bias
    def physical(self,u):return self.gain*u
    def apply_once(self,op,u,target):
        request=json.dumps([u,target])
        self.db.execute('BEGIN IMMEDIATE')
        try:
            row=self.db.execute('SELECT request,result FROM receipts WHERE id=?',(op,)).fetchone()
            if row:
                if row[0]!=request: raise ValueError('operation ID reused with different request')
                result=json.loads(row[1])
            else:
                result=dict(observed=self.measure('U'+str(u)),physical=self.physical(u),
                            harm=int(self.physical(u)!=target))
                self.db.execute('INSERT INTO receipts VALUES(?,?,?)',(op,request,json.dumps(result)))
            self.db.commit(); return result['observed']
        except BaseException:self.db.rollback();raise
    def close(self):self.db.close()

class DurableRuntime(DecisionRuntime):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.db.execute('CREATE TABLE IF NOT EXISTS intents(id TEXT PRIMARY KEY,body TEXT,status TEXT)')
        self.db.commit()

    def step(self,world,fail_at=None):
        pending=self.db.execute("SELECT id,body FROM intents WHERE status='pending'").fetchone()
        if pending:
            if not getattr(world,'supports_idempotency',False):
                # Uncertain delivery is not permission to retry a non-idempotent action.
                return dict(self.state(),reason='UNKNOWN_DELIVERY_NEEDS_RECONCILIATION')
            op,body=pending; body=json.loads(body)
            if body.get('receiver_id')!=getattr(world,'receiver_id',None):
                return dict(self.state(),reason='RECEIVER_IDENTITY_MISMATCH')
            receipt=world.lookup(op)
            if receipt is None:
                # In this synchronous simulator no receipt proves no effect.
                # Never replay an unexecuted stale permit after an outage.
                with self.db:
                    s=self.state()
                    s.update(phase='ASSESS',reason='REVALIDATION_REQUIRED',evidence=[],certified=False,scope=[],
                             generation=s['generation']+1)
                    self.save(s);self.event(s,'UNEXECUTED_INTENT_CANCELLED',operation_id=op)
                    self.db.execute("UPDATE intents SET status='cancelled' WHERE id=?",(op,))
                return s
            observed=receipt['observed']
            if fail_at=='after_effect':raise RuntimeError('injected after receiver commit')
            self.db.execute('BEGIN IMMEDIATE')
            try:
                s=self.state()
                if s['task_id']!=body['task_id']:raise RuntimeError('task changed during pending execution')
                s['budget']-=1
                s.update(phase='DONE' if observed in body['expected'] else 'HALT',
                         reason=None if observed in body['expected'] else 'EXECUTION_MISMATCH')
                self.event(s,'PROCESS_RECONCILED',operation_id=op,observed=observed)
                self.save(s)
                self.db.execute("UPDATE intents SET status='done' WHERE id=?",(op,))
                self.db.commit();return s
            except BaseException:self.db.rollback();raise
        outer=self
        class Receiver:
            def measure(self,p):return world.measure(p)
            def execute(self,u,target):
                if not getattr(world,'supports_idempotency',False):
                    raise ValueError('receiver needs explicit idempotency contract')
                s=outer.state(); op=str(uuid.uuid4())
                permission=outer.permit(u)
                if not outer.validate_permission(permission):raise RuntimeError('invalid execution permission')
                body=dict(u=u,target=target,task_id=s['task_id'],receiver_id=world.receiver_id,permission=permission,
                          expected=sorted({outer.predict_model(m,'U'+str(u)) for m in outer.candidates(s)}))
                outer.db.execute('INSERT INTO intents VALUES(?,?,?)',(op,json.dumps(body),'pending'))
                outer.event(s,'INTENT',operation_id=op,request=body)
                outer.db.commit()  # Persist intent BEFORE external effect.
                if fail_at=='after_intent':raise RuntimeError('injected before receiver execution')
                if not outer.validate_permission(permission):raise RuntimeError('basis changed before execution')
                observed=world.apply_once(op,u,target)
                if fail_at=='after_effect':raise RuntimeError('injected after receiver commit')
                outer.db.execute('BEGIN IMMEDIATE')
                outer.db.execute("UPDATE intents SET status='done' WHERE id=?",(op,))
                return observed  # Parent atomically saves outcome, budget and done marker.
        return super().step(Receiver())
