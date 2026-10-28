"""Virtual S17 sensor host. Private world never returned to the candidate agent."""
import json
import sqlite3
from pathlib import Path
from engine.s17_transfer import SensorTransferAgent, json_hash

VARIANTS={
    'bias_A':([17,17],[12,12],12),
    'process_change':([17,17],[17,17],17),
    'unstable_A':([17,12],[12,12],12),
    'unstable_B':([17,17],[12,17],12),
    'danger':([13,13],[8,8],8),
    'no_gap':([12,12],[12,12],12),
    'shared_uncertified':([17,17],[17,17],12),
    'misleading_certification':([17,17],[17,17],8),
}
DEFAULT_PUBLIC={'baseline':12,'output_floor':10,'B_available':True,'B_certified':True,
                'read_cost':2,'action_cost':1}

class PrivateSensorWorld:
    def __init__(self,path,variant,public):
        if variant not in VARIANTS:raise ValueError('unknown PRIVATE host variant')
        self.db=sqlite3.connect(str(path))
        self.db.execute('CREATE TABLE IF NOT EXISTS contract(id INTEGER PRIMARY KEY,body TEXT NOT NULL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS readings(key TEXT PRIMARY KEY,body TEXT NOT NULL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS physical_actions(key TEXT PRIMARY KEY,body TEXT NOT NULL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS counters(channel TEXT PRIMARY KEY,n INTEGER NOT NULL)')
        contract={'private_variant':variant,'public':public}
        row=self.db.execute('SELECT body FROM contract WHERE id=1').fetchone()
        if row and json.loads(row[0])!=contract:
            self.db.close();raise ValueError('S17 private world contract mismatch')
        if not row:
            with self.db:self.db.execute('INSERT INTO contract VALUES(1,?)',(json.dumps(contract,sort_keys=True),))
        self.variant=variant;self.public=public
    def close(self):self.db.close()
    def read(self,channel,key):
        if channel not in ('A','B') or (channel=='B' and not self.public['B_available']):
            raise ValueError('unsupported sensor channel')
        old=self.db.execute('SELECT body FROM readings WHERE key=?',(key,)).fetchone()
        if old:
            obs=json.loads(old[0]);
            if obs['channel']!=channel:raise ValueError('receipt key reused across channels')
            return obs
        current=self.db.execute('SELECT n FROM counters WHERE channel=?',(channel,)).fetchone()
        n=current[0] if current else 0
        observations=VARIANTS[self.variant][0 if channel=='A' else 1]
        if n>=len(observations):raise ValueError('no more samples in controlled world')
        obs={'channel':channel,'value':observations[n],'radius':0,'receipt_id':key,'sample_index':n+1}
        with self.db:
            self.db.execute('INSERT INTO readings VALUES(?,?)',(key,json.dumps(obs,sort_keys=True)))
            self.db.execute('INSERT OR REPLACE INTO counters VALUES(?,?)',(channel,n+1))
        return obs
    def execute(self,key,predicted,reference_receipts):
        old=self.db.execute('SELECT body FROM physical_actions WHERE key=?',(key,)).fetchone()
        if old:
            receipt=json.loads(old[0]);
            if receipt['prediction']!=predicted or receipt['reference_receipts']!=reference_receipts:
                raise ValueError('changed idempotent action request')
            return receipt
        value=VARIANTS[self.variant][2]
        receipt=dict(key=key,prediction=predicted,actual=value,
                     reference_receipts=reference_receipts,physical_actions=1)
        with self.db:self.db.execute('INSERT INTO physical_actions VALUES(?,?)',(key,json.dumps(receipt,sort_keys=True)))
        return receipt
    def receipts(self):
        return [json.loads(r[0]) for r in self.db.execute('SELECT body FROM physical_actions ORDER BY key')]

class S17SensorExperiment:
    def __init__(self,path,source,*,variant='bias_A',transfer_enabled=True,budget=12,**capability_changes):
        self.root=Path(path);self.root.mkdir(parents=True,exist_ok=True)
        pub=dict(DEFAULT_PUBLIC);pub.update(capability_changes)
        if pub['output_floor']<0 or pub['read_cost']<1 or pub['action_cost']<1:raise ValueError('invalid public contract')
        if variant=='shared_uncertified' and pub['B_certified']:
            raise ValueError('shared_uncertified host cannot publish false certification')
        self.agent=SensorTransferAgent(self.root/'agent.sqlite',source,pub,transfer_enabled=transfer_enabled,budget=budget)
        try:self.world=PrivateSensorWorld(self.root/'world.sqlite',variant,pub)
        except BaseException:self.agent.close();raise
    def close(self):self.agent.close();self.world.close()
    def step(self):
        kind,request=self.agent.proposal()
        if kind=='READ':
            receipt=self.world.read(request['channel'],request['key'])
            self.agent.commit_read(receipt)
        elif kind=='ACT':
            receipt=self.world.execute(request['key'],request['predicted'],request['reference_receipts'])
            self.agent.commit_act(receipt)
        return self.snapshot()
    def snapshot(self):
        return dict(state=self.agent.state(),receipts=self.world.receipts(),
                    sensor_readings=[json.loads(r[0]) for r in self.world.db.execute('SELECT body FROM readings ORDER BY rowid')])
    def run(self,max_steps=20):
        for _ in range(max_steps):
            x=self.step()
            if x['state']['status']!='ACTIVE':return x
        raise RuntimeError('S17 run exceeded declared step cap')
