"""Integrated finite workshop. See RUNTIME_CONTRACT.md for strict claim boundaries."""
import argparse
import json
import sqlite3
from conflict_diagnosis import HYPOTHESES, PROBES, predicted
from revision_gate import assess_revision


class Workshop:
    """Evaluator owns truth. Runtime receives only measure/execute return values."""
    def __init__(self, gain=1, bias=0, nonlinear=False, bad_cal=False):
        self.gain, self.bias = gain, bias
        self.nonlinear, self.bad_cal = nonlinear, bad_cal
        self.actions = []

    def measure(self, probe):
        if probe == 'CAL':
            return self.bias + int(self.bad_cal)
        u = int(probe[1:])
        return self.gain*u + self.bias + (3 if self.nonlinear and u == 2 else 0)

    def execute(self, u, target):
        value = self.measure('U'+str(u))
        physical = value-self.bias
        self.actions.append({'u': u, 'target': target, 'physical': physical,
                             'harm': int(physical != target)})
        return value


class Runtime:
    def __init__(self, path, mode='FoR', diagnosis=True, revision=True):
        if mode not in ('FoR', 'B2'):
            raise ValueError('unknown mode')
        self.mode, self.diagnosis, self.revision = mode, diagnosis, revision
        self.db = sqlite3.connect(str(path))
        tables={row[0] for row in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if tables and ('runtime_contract' not in tables or
                       self.db.execute('SELECT version FROM runtime_contract').fetchall()!=[('gain-bias-0.7a',)]):
            self.db.close()
            raise ValueError('incompatible database; no automatic migration')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS runtime_contract(version TEXT PRIMARY KEY);
        INSERT OR IGNORE INTO runtime_contract VALUES('gain-bias-0.7a');
        CREATE TABLE IF NOT EXISTS beliefs(name TEXT PRIMARY KEY,value INTEGER,version INTEGER);
        INSERT OR IGNORE INTO beliefs VALUES('process',1,0);
        INSERT OR IGNORE INTO beliefs VALUES('sensor',0,0);
        CREATE TABLE IF NOT EXISTS forecasts(name TEXT PRIMARY KEY,deps TEXT,valid INTEGER);
        INSERT OR IGNORE INTO forecasts VALUES('physical','["process"]',1);
        INSERT OR IGNORE INTO forecasts VALUES('zero','["sensor"]',1);
        CREATE TABLE IF NOT EXISTS runtime_state(id INTEGER PRIMARY KEY,body TEXT);
        CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,body TEXT);
        CREATE TABLE IF NOT EXISTS runtime_revisions(id INTEGER PRIMARY KEY,body TEXT);
        ''')
        if not self.db.execute('SELECT 1 FROM runtime_state').fetchone():
            state = dict(phase='IDLE', certified=False, generation=0, scope=[],
                         evidence=[], budget=0, trusted=False, target=None,
                         task_id=0, process_attempts=0, reason=None)
            self.db.execute('INSERT INTO runtime_state VALUES(1,?)',(json.dumps(state),))
        self.db.commit()

    def state(self):
        return json.loads(self.db.execute('SELECT body FROM runtime_state WHERE id=1').fetchone()[0])

    def beliefs(self):
        return {n:(v,ver) for n,v,ver in self.db.execute('SELECT * FROM beliefs')}

    def save(self, state):
        self.db.execute('UPDATE runtime_state SET body=? WHERE id=1',(json.dumps(state),))

    def event(self, state, kind, **fields):
        self.db.execute('INSERT INTO events(body) VALUES(?)',
                        (json.dumps(dict(task_id=state['task_id'], kind=kind, **fields)),))

    def start(self, target, budget=8, trusted=True):
        if type(target) is not int or type(budget) is not int or budget < 0:
            raise ValueError('invalid task')
        s=self.state()
        if s['phase'] not in ('IDLE','DONE','HALT'):
            raise RuntimeError('unfinished task must be resumed')
        s.update(target=target,budget=budget,trusted=trusted,phase='ASSESS',
                 task_id=s['task_id']+1,process_attempts=0,reason=None,validated_task=False)
        # An unresolved task keeps its evidence and uncertified status.
        with self.db:
            self.save(s)
            self.event(s,'START',target=target,budget=budget,mode=self.mode)

    def permit(self, u):
        s=self.state()
        g=self.beliefs()['process'][0]
        if (not s['certified'] or s['phase'] != 'ACT' or not s['trusted'] or
            'U'+str(u) not in s['scope'] or g*u != s['target'] or s['budget']<1):
            return None
        return dict(u=u,generation=s['generation'],task_id=s['task_id'],target=s['target'])

    def execute(self, world, permit):
        s=self.state()
        if not permit or self.permit(permit['u']) != permit:
            raise ValueError('stale, out-of-scope or ungrounded permit')
        u=permit['u']; b=self.beliefs()
        expected=b['process'][0]*u+b['sensor'][0]
        measured=world.execute(u,s['target'])
        s['budget']-=1; s['process_attempts']+=1
        self.event(s,'PROCESS',u=u,observed=measured,expected=expected,permit=permit)
        if measured != expected:
            s.update(certified=False,scope=[],generation=s['generation']+1,
                     evidence=[dict(probe='U'+str(u),value=measured)],phase='DIAGNOSE')
            self.event(s,'CONTRADICTION',expected=expected,observed=measured)
        else:
            s['phase']='DONE'
        self.save(s)

    def step(self, world, fail_revision=False):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            s=self.state(); phase=s['phase']
            if phase in ('IDLE','DONE','HALT'):
                self.db.rollback(); return s
            if phase=='ACT':
                u=next((u for u in (1,2) if self.permit(u)),None)
                if u is None:
                    s.update(phase='HALT',reason='NO_PERMIT'); self.save(s)
                else:
                    self.execute(world,self.permit(u))
            elif phase=='ASSESS':
                if not s['trusted']:
                    s.update(phase='HALT',reason='UNTRUSTED_CAL')
                elif s['certified']:
                    g=self.beliefs()['process'][0]
                    if any(g*u==s['target'] for u in (1,2)):
                        s['phase']='ACT'
                    elif not s.get('validated_task',False):
                        # A previously learned model can be stale. Recheck once;
                        # do not declare the new goal physically impossible.
                        s.update(phase='INQUIRE',evidence=[],certified=False,scope=[],
                                 generation=s['generation']+1)
                        self.event(s,'RECHECK_INFEASIBLE_GOAL')
                    else:
                        s.update(phase='HALT',reason='NO_SCOPED_ACTION')
                else:
                    s['phase']='INQUIRE'
                self.save(s)
            elif phase in ('INQUIRE','DIAGNOSE'):
                if phase=='DIAGNOSE' and not self.diagnosis:
                    s.update(phase='HALT',reason='DIAGNOSIS_DISABLED')
                elif not s['trusted']:
                    s.update(phase='HALT',reason='UNTRUSTED_CAL')
                else:
                    models=[m for m in HYPOTHESES if all(predicted(m,e['probe'])==e['value'] for e in s['evidence'])]
                    seen={e['probe'] for e in s['evidence']}
                    remaining=[p for p in PROBES if p not in seen]
                    if not models:
                        s.update(phase='HALT',reason='OUT_OF_CLASS')
                    elif not remaining:
                        s['phase']='REVISE'
                    elif s['budget']<1:
                        s.update(phase='HALT',reason='BUDGET_LIMIT')
                    else:
                        p=max(remaining,key=lambda p:len({predicted(m,p) for m in models}))
                        v=world.measure(p); s['budget']-=1
                        s['evidence'].append(dict(probe=p,value=v))
                        self.event(s,'PROBE',probe=p,value=v,phase=phase)
                self.save(s)
            elif phase=='REVISE':
                if not self.revision:
                    s.update(phase='HALT',reason='REVISION_DISABLED')
                else:
                    before=self.beliefs()
                    report=assess_revision((before['process'][0],before['sensor'][0]),s['evidence'],s['trusted'])
                    if 'model' not in report:
                        s.update(phase='HALT',reason=report['status'])
                    else:
                        changed=set(report['changed'])
                        for name,value in zip(('process','sensor'),report['model']):
                            if name in changed:
                                self.db.execute('UPDATE beliefs SET value=?,version=version+1 WHERE name=?',(value,name))
                        for name,deps in self.db.execute('SELECT name,deps FROM forecasts').fetchall():
                            if changed.intersection(json.loads(deps)):
                                self.db.execute('UPDATE forecasts SET valid=0 WHERE name=?',(name,))
                        if fail_revision:
                            raise RuntimeError('injected revision failure')
                        self.db.execute('INSERT INTO runtime_revisions(body) VALUES(?)',
                                        (json.dumps(dict(before=before,report=report,evidence=s['evidence'])),))
                        s.update(certified=True,scope=report['scope'],generation=s['generation']+1,phase='ASSESS',validated_task=True)
                        self.event(s,'REVISION',report=report)
                self.save(s)
            else:
                raise RuntimeError('unknown phase')
            self.db.commit()
            return self.state()
        except BaseException:
            self.db.rollback()
            raise

    def run(self,world,steps=100):
        for _ in range(steps):
            s=self.step(world)
            if s['phase'] in ('HALT','DONE','IDLE'): return s
        return self.state()  # persisted open task, not called success

    def close(self): self.db.close()


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--db',required=True)
    p.add_argument('--target',type=int)
    p.add_argument('--gain',type=int,default=1)
    p.add_argument('--bias',type=int,default=0)
    p.add_argument('--steps',type=int,default=100)
    p.add_argument('--mode',choices=['FoR','B2'],default='FoR')
    a=p.parse_args()
    r=Runtime(a.db,a.mode); w=Workshop(a.gain,a.bias)
    try:
        if a.target is not None: r.start(a.target)
        result=r.run(w,a.steps)
        print(json.dumps(dict(state=result,evaluator_actions=w.actions,beliefs=r.beliefs()),indent=2))
    finally: r.close()
