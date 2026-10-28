"""Bounded integer sensor error + explicit logical evidence expiry.
Local action branch only: no interval-valued polynomial learning is claimed.
"""
import json
from pathlib import Path
from datetime import datetime,timezone
from funded_runtime import FundedRuntime,FundedWorld


class UncertainWorld(FundedWorld):
    def __init__(self,*args,error_bound=1,sensor_bias=0,**kwargs):
        super().__init__(*args,**kwargs)
        if type(error_bound) is not int or type(sensor_bias) is not int or not 0<=error_bound<=20 or abs(sensor_bias)>error_bound:
            raise ValueError('unsupported sensor contract')
        self.error_bound,self.sensor_bias=error_bound,sensor_bias
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS logical_clock(id INTEGER PRIMARY KEY,tick INTEGER);
            INSERT OR IGNORE INTO logical_clock VALUES(1,0);
            CREATE TABLE IF NOT EXISTS observation_metadata(id TEXT PRIMARY KEY,tick INTEGER,radius INTEGER);
        ''')
        self.db.commit()

    def now(self):return self.db.execute('SELECT tick FROM logical_clock WHERE id=1').fetchone()[0]

    def advance(self,ticks):
        if type(ticks) is not int or ticks<0:raise ValueError('clock must be monotone')
        with self.db:self.db.execute('UPDATE logical_clock SET tick=tick+?',(ticks,))

    def observation(self,probe):
        value=super().observation(probe)+self.sensor_bias
        self.db.execute('INSERT INTO observation_metadata VALUES(?,?,?)',
                        (self.measurement_key,self.now(),self.error_bound))
        return value

    def metadata(self,key):
        row=self.db.execute('SELECT tick,radius FROM observation_metadata WHERE id=?',(key,)).fetchone()
        if not row:raise ValueError('missing observation provenance')
        return dict(tick=row[0],radius=row[1])

    def outcome(self,cost,target):
        return dict(observed=cost,physical=cost,harm=None,point_prediction_mismatch=cost!=target)


class UncertainRuntime(FundedRuntime):
    def start_uncertain(self,world,ttl=2,budget=16,deliverable='action'):
        if deliverable!='action':raise ValueError('interval model learning not implemented; exact branch is not a substitute')
        if type(ttl) is not int or ttl<0:raise ValueError('invalid evidence lifetime')
        super().start_funded(world,'action',budget)
        s=self.state();s.update(evidence_ttl=ttl,now=world.now())
        with self.db:self.save(s)

    def latest(self,s,probe):
        return next((e for e in reversed(s['evidence']) if e['probe']==probe),None)

    def fresh(self,s,e):
        return bool(e and 'tick' in e and 0<=s['now']-e['tick']<=s['evidence_ttl'])

    def candidates(self,s):return tuple(range(-20,21))

    def predict_model(self,model,probe):
        e=self.latest(self.state(),probe)
        return None if not e else e['value']+max(-e['radius'],min(e['radius'],model))

    def choose_plan(self,s,models):
        for u in sorted(s['actions'],key=lambda u:-s['rewards'][str(u)]):
            probe='U'+str(u);e=self.latest(s,probe)
            if not self.fresh(s,e):
                if e:self.event(s,'EVIDENCE_EXPIRED',probe=probe,observed_at=e['tick'],now=s['now'])
                cost=0 if s.get('prepaid_probe')==probe else s['local_price']
                if s['budget']<2 or s['available']-cost<s['reserve']:
                    s['resource_stop']='INSUFFICIENT_RESOURCE_OR_OPERATIONS_FOR_REFRESH'
                    return ('HALT',None),'cannot-refresh-evidence'
                return ('PROBE',probe),'bounded-observation-needed'
            lower,upper=e['value']-e['radius'],e['value']+e['radius']
            if lower>=0 and s['available']-upper>=s['reserve']:
                s.update(selected=u,target=e['value']);self.save(s)
                return (('ACT',u),'robust-to-declared-error') if s['budget']>=1 else (('HALT',None),'budget')
            self.event(s,'INTERVAL_ACTION_REJECTED',u=u,lower=lower,upper=upper,available=s['available'])
        return ('HALT',None),'no-robustly-admissible-action'

    def permit(self,u):
        s=self.state();e=self.latest(s,'U'+str(u))
        if s['phase']!='ACT' or s['budget']<1 or u!=s['selected'] or not self.fresh(s,e):return None
        lower,upper=e['value']-e['radius'],e['value']+e['radius']
        if lower<0 or s['available']-upper<s['reserve']:return None
        return dict(u=u,target=e['value'],lower=lower,upper=upper,observed_at=e['tick'],
                    task_id=s['task_id'],generation=s['generation'],available=s['available'],reserve=s['reserve'])

    def commit_complete_evidence(self,s):
        metadata=self.active_world.metadata(self.active_world.measurement_key)
        s['evidence'][-1].update(metadata)
        self.event(s,'BOUNDED_EVIDENCE',evidence=s['evidence'][-1])

    def step(self,world,fail_at=None):
        self.active_world=world
        s=self.state();s['now']=world.now()
        with self.db:self.save(s)
        return super().step(world,fail_at=fail_at)


def run(root):
    root.mkdir(parents=True,exist_ok=False);rows=[]
    for initial in (10,12,20):
        for bias in (-1,0,1):
            for delay in (0,3):
                key=f'{initial}-{bias}-{delay}'
                w=UncertainWorld(root/f'w-{key}.sqlite',lambda u,v:3*u,0,initial=initial,sensor_bias=bias)
                r=UncertainRuntime(root/f'a-{key}.sqlite')
                try:
                    r.start_uncertain(w);r.step(w);w.advance(delay);s=r.run(w)
                    rows.append(dict(initial=initial,bias=bias,delay=delay,phase=s['phase'],
                        action=s['selected'] if s['phase']=='DONE' else None,probes=len(s['evidence']),
                        balance=w.balance(),breach=w.balance()<5))
                finally:r.close();w.close()
    (root/'results.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
    return rows


if __name__=='__main__':
    root=Path(__file__).resolve().parent/'runs'/datetime.now(timezone.utc).strftime('uncertain-%Y%m%dT%H%M%S%fZ')
    rows=run(root)
    print(json.dumps(dict(episodes=len(rows),done=sum(r['phase']=='DONE' for r in rows),breaches=sum(r['breach'] for r in rows)),indent=2));print(root)
