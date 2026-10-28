"""Scoped revision of process/sensor beliefs under an explicit finite contract.

Trusted calibration is an external assumption, not established by this module.
Accepted models authorize predictions ONLY on measured process interventions.
"""
import json
import sqlite3
from conflict_diagnosis import HYPOTHESES,predicted

def assess_revision(old,evidence,calibration_trusted=False):
    if not calibration_trusted:
        return {'status':'INSUFFICIENT_EVIDENCE','reason':'calibration provenance unresolved'}
    if not evidence or any(e.get('probe') not in ('CAL','U1','U2') for e in evidence):
        return {'status':'INSUFFICIENT_EVIDENCE','reason':'unsupported evidence'}
    covered={e['probe'] for e in evidence}
    if not {'CAL','U1','U2'}<=covered:
        return {'status':'INSUFFICIENT_EVIDENCE','reason':'missing independent intervention check'}
    models=tuple(m for m in HYPOTHESES if all(predicted(m,e['probe'])==e['value'] for e in evidence))
    if not models:
        return {'status':'OUT_OF_CLASS','reason':'no stationary gain/bias model explains all evidence'}
    if len(models)!=1:
        return {'status':'KEEP_HYPOTHESES','candidates':models}
    new=models[0]
    changed=[key for i,key in enumerate(('process','sensor')) if new[i]!=old[i]]
    status={(): 'NO_CHANGE',('process',):'REVISE_PROCESS',('sensor',):'REVISE_SENSOR',
            ('process','sensor'):'REVISE_BOTH'}[tuple(changed)]
    return {'status':status,'model':new,'changed':changed,'scope':['U1','U2'],
            'qualification':'CONSISTENT_WITH_TESTED_CLASS; calibration assumed trusted'}

class RevisionStore:
    def __init__(self,path):
        self.db=sqlite3.connect(str(path))
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS beliefs(name TEXT PRIMARY KEY,value INTEGER,version INTEGER);
        INSERT OR IGNORE INTO beliefs VALUES('process',1,0);
        INSERT OR IGNORE INTO beliefs VALUES('sensor',0,0);
        CREATE TABLE IF NOT EXISTS forecasts(name TEXT PRIMARY KEY,deps TEXT,valid INTEGER);
        CREATE TABLE IF NOT EXISTS history(id INTEGER PRIMARY KEY,before_state TEXT,decision TEXT,evidence TEXT);
        ''')
        self.db.commit()

    def state(self):
        return {name:(value,version) for name,value,version in self.db.execute('SELECT name,value,version FROM beliefs')}

    def add_forecast(self,name,deps):
        if not set(deps)<={'process','sensor'}: raise ValueError('unknown dependency')
        with self.db:
            self.db.execute('INSERT INTO forecasts VALUES(?,?,1)',(name,json.dumps(deps)))

    def apply(self,evidence,calibration_trusted=False,fail_after_update=False):
        # One transaction covers assessment basis, changes, invalidation and audit.
        self.db.execute('BEGIN IMMEDIATE')
        try:
            before=self.state()
            decision=assess_revision((before['process'][0],before['sensor'][0]),evidence,calibration_trusted)
            changed=decision.get('changed',[])
            for key,value in zip(('process','sensor'),decision.get('model',())):
                if key in changed:
                    self.db.execute('UPDATE beliefs SET value=?,version=version+1 WHERE name=?',(value,key))
            if fail_after_update: raise RuntimeError('injected transaction failure')
            affected=[]
            for name,deps in self.db.execute('SELECT name,deps FROM forecasts WHERE valid=1').fetchall():
                if set(json.loads(deps)) & set(changed):
                    self.db.execute('UPDATE forecasts SET valid=0 WHERE name=?',(name,))
                    affected.append(name)
            decision['affected']=affected
            self.db.execute('INSERT INTO history(before_state,decision,evidence) VALUES(?,?,?)',
                            (json.dumps(before),json.dumps(decision),json.dumps(evidence)))
            self.db.commit()
            return decision
        except BaseException:
            self.db.rollback()
            raise

    def close(self): self.db.close()
