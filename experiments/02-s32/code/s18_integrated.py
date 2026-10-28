"""S18 virtual host: source trust inquiry added to S17, private outcomes remain host-only."""
import json
import sqlite3
from pathlib import Path
from s17_integrated import S17SensorExperiment, PrivateSensorWorld, DEFAULT_PUBLIC
from engine.s18_source_trust import SourceTrustAgent

# All private assignments are host-only. The agent receives no variant labels.
CHALLENGE_VARIANTS={
    'bias_A':('bias_A',(12,12)),
    'process_change':('process_change',(17,17)),
    'misleading_certification':('misleading_certification',(8,8)),
    'colluding_sources':('misleading_certification',(17,17)),
    'unstable_C':('bias_A',(12,17)),
    'below_norm':('danger',(8,8)),
    'unstable_B':('unstable_B',(12,12)),
    'no_gap':('no_gap',(12,12)),
}

class PrivateS18World(PrivateSensorWorld):
    def __init__(self, path, variant, public):
        if variant not in CHALLENGE_VARIANTS:
            raise ValueError('unknown private S18 variant')
        parent,values=CHALLENGE_VARIANTS[variant]
        super().__init__(path,parent,public)
        # A separate contract prevents private experiment replacement on reopen.
        self.db.execute('CREATE TABLE IF NOT EXISTS s18_host_contract(id INTEGER PRIMARY KEY, body TEXT NOT NULL)')
        body=json.dumps({'private_variant':variant,'C_values':values,'public':public},sort_keys=True)
        old=self.db.execute('SELECT body FROM s18_host_contract WHERE id=1').fetchone()
        if old and old[0]!=body:
            self.close();raise ValueError('S18 private host contract mismatch')
        if not old:
            with self.db:self.db.execute('INSERT INTO s18_host_contract VALUES(1,?)',(body,))
        self.c_values=values
    def read(self,channel,key):
        if channel!='C':return super().read(channel,key)
        if not self.public.get('C_available',True):raise ValueError('C unavailable')
        old=self.db.execute('SELECT body FROM readings WHERE key=?',(key,)).fetchone()
        if old:
            obs=json.loads(old[0])
            if obs['channel']!='C':raise ValueError('receipt key reused across channels')
            return obs
        current=self.db.execute('SELECT n FROM counters WHERE channel=?',('C',)).fetchone()
        n=current[0] if current else 0
        if n>=len(self.c_values):raise ValueError('C samples exhausted')
        obs={'channel':'C','value':self.c_values[n],'radius':0,'receipt_id':key,'sample_index':n+1}
        with self.db:
            self.db.execute('INSERT INTO readings VALUES(?,?)',(key,json.dumps(obs,sort_keys=True)))
            self.db.execute('INSERT OR REPLACE INTO counters VALUES(?,?)',('C',n+1))
        return obs

class S18Experiment(S17SensorExperiment):
    def __init__(self,path,source,*,variant='bias_A',transfer_enabled=True,
                 challenge_enabled=True,budget=16,**capability_changes):
        self.root=Path(path);self.root.mkdir(parents=True,exist_ok=True)
        pub=dict(DEFAULT_PUBLIC,C_available=True,C_certified=True,trust_challenge_enabled=bool(challenge_enabled))
        pub.update(capability_changes)
        if pub['output_floor']<0 or pub['read_cost']<1 or pub['action_cost']<1:raise ValueError('invalid public contract')
        self.agent=SourceTrustAgent(self.root/'agent.sqlite',source,pub,transfer_enabled=transfer_enabled,budget=budget)
        try:self.world=PrivateS18World(self.root/'world.sqlite',variant,pub)
        except BaseException:self.agent.close();raise
