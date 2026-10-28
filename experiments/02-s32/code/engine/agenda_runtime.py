"""Persistent caller-specified agenda; no claim of self-generated goals."""
import json
from durable_runtime import DurableRuntime

class AgendaRuntime(DurableRuntime):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.db.execute('CREATE TABLE IF NOT EXISTS agenda(id TEXT PRIMARY KEY,position INTEGER,request TEXT,status TEXT,task_id INTEGER)')
        self.db.commit()
    def enqueue(self,key,target,budget=6):
        if type(target) is not int or type(budget) is not int or budget<0:
            raise ValueError('invalid agenda request')
        request=json.dumps(dict(target=target,budget=budget))
        old=self.db.execute('SELECT request FROM agenda WHERE id=?',(key,)).fetchone()
        if old:
            if old[0]!=request:raise ValueError('agenda key already has a different request')
            return
        with self.db:
            pos=self.db.execute('SELECT COALESCE(MAX(position),0)+1 FROM agenda').fetchone()[0]
            self.db.execute('INSERT INTO agenda VALUES(?,?,?,?,NULL)',(key,pos,request,'queued'))
    def tick(self,world):
        self.recover_agenda()
        active=self.db.execute("SELECT id,task_id FROM agenda WHERE status='active'").fetchone()
        if active:
            s=self.state()
            if s['task_id']!=active[1]:raise RuntimeError('agenda/task mismatch')
            if s['phase'] in ('DONE','HALT'):
                with self.db:
                    self.db.execute('UPDATE agenda SET status=? WHERE id=?',(s['phase'],active[0]))
                    self.event(s,'AGENDA_FINISHED',agenda_id=active[0],outcome=s['phase'])
                return s
            return self.step(world)
        row=self.db.execute("SELECT id,request FROM agenda WHERE status='queued' ORDER BY position LIMIT 1").fetchone()
        if not row:return dict(self.state(),agenda='EMPTY')
        # Atomic registration/start requires start_decision's commits to be suppressed.
        # For this version use a durable 'starting' marker and reconcile on restart.
        key,request=row; request=json.loads(request)
        with self.db:self.db.execute("UPDATE agenda SET status='starting',task_id=? WHERE id=?",(self.state()['task_id']+1,key))
        self.start_decision(**request)
        with self.db:self.db.execute("UPDATE agenda SET status='active' WHERE id=?",(key,))
        return self.state()
    def recover_agenda(self):
        row=self.db.execute("SELECT id,request,task_id FROM agenda WHERE status='starting'").fetchone()
        if not row:return
        key,request,expected=row;s=self.state()
        if s['task_id']==expected-1:self.start_decision(**json.loads(request))
        elif s['task_id']!=expected:raise RuntimeError('cannot reconcile agenda start')
        # A partially committed start_decision must not run with previous task evidence.
        elif s['phase']=='ASSESS':
            req=json.loads(request)
            s.update(evidence=[],certified=False,scope=[],actions=[1,2],
                     costs={p:'1/10' for p in ('CAL','U1','U2')},penalty='2',policy='decision',
                     decision_contract='finite-minimax-v1',target=req['target'],budget=req['budget'])
            with self.db:self.save(s)
        else:raise RuntimeError('unexpected phase during agenda recovery')
        with self.db:self.db.execute("UPDATE agenda SET status='active' WHERE id=?",(key,))
