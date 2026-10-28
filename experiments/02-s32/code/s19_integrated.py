"""Private S19 world: correlated B/C source and a third challenge D."""
import json
from pathlib import Path
from s17_integrated import DEFAULT_PUBLIC, S17SensorExperiment
from s18_integrated import PrivateS18World
from engine.s19_provenance import ProvenanceInquiryAgent


class PrivateS19World(PrivateS18World):
    def __init__(self,path,variant,public,d_values):
        super().__init__(path,variant,public)
        if not isinstance(d_values,(list,tuple)) or len(d_values)!=2:
            self.close();raise ValueError('S19 private D values must be two samples')
        body=json.dumps({'D_values':list(d_values)},sort_keys=True)
        self.db.execute('CREATE TABLE IF NOT EXISTS s19_private_contract(id INTEGER PRIMARY KEY, body TEXT NOT NULL)')
        row=self.db.execute('SELECT body FROM s19_private_contract WHERE id=1').fetchone()
        if row and row[0]!=body:
            self.close();raise ValueError('S19 private third-source contract mismatch')
        if not row:
            with self.db:self.db.execute('INSERT INTO s19_private_contract VALUES(1,?)',(body,))
        self.d_values=tuple(d_values)

    def read(self,channel,key):
        if channel!='D':return super().read(channel,key)
        if not self.public.get('D_available',False):raise ValueError('D unavailable')
        row=self.db.execute('SELECT body FROM readings WHERE key=?',(key,)).fetchone()
        if row:
            obs=json.loads(row[0])
            if obs['channel']!='D':raise ValueError('S19 receipt reused by wrong channel')
            return obs
        row=self.db.execute('SELECT n FROM counters WHERE channel=?',('D',)).fetchone()
        n=row[0] if row else 0
        if n>=len(self.d_values):raise ValueError('S19 D sample exhaustion')
        obs={'channel':'D','value':self.d_values[n],'radius':0,'receipt_id':key,'sample_index':n+1}
        with self.db:
            self.db.execute('INSERT INTO readings VALUES(?,?)',(key,json.dumps(obs,sort_keys=True)))
            self.db.execute('INSERT OR REPLACE INTO counters VALUES(?,?)',('D',n+1))
        return obs


class S19Experiment(S17SensorExperiment):
    def __init__(self,path,source,*,variant='bias_A',d_values=(12,12),
                 provenance_roots=None,provenance_enabled=True,trust_challenge_enabled=True,
                 transfer_enabled=True,budget=20,**capability_changes):
        self.root=Path(path);self.root.mkdir(parents=True,exist_ok=True)
        roots={'B':'lineage-B','C':'lineage-C','D':'lineage-D'} if provenance_roots is None else dict(provenance_roots)
        pub=dict(DEFAULT_PUBLIC,C_available=True,C_certified=True,
                 D_available=True,D_certified=True,
                 trust_challenge_enabled=trust_challenge_enabled,
                 provenance_challenge_enabled=provenance_enabled,
                 provenance_roots=roots)
        pub.update(capability_changes)
        if pub['output_floor']<0 or pub['read_cost']<1 or pub['action_cost']<1:
            raise ValueError('invalid public contract')
        self.agent=ProvenanceInquiryAgent(self.root/'agent.sqlite',source,pub,
                                          transfer_enabled=transfer_enabled,budget=budget)
        try:self.world=PrivateS19World(self.root/'world.sqlite',variant,pub,d_values)
        except BaseException:self.agent.close();raise
