"""S23 domain-neutral active inquiry. Agent sees advertised capabilities, never private readings.
Probes represent the same measured quantity, and declared roots are only claims.
"""
import json, sqlite3
from pathlib import Path

PUBLIC_PROBES={
 'source': [{'role':'D','measurand':'source-output','root':'distinct','cost':2},
            {'role':'E','measurand':'source-output','root':'claimed-E','cost':2}],
 'actuator':[{'role':'U3','measurand':'response-at-U3','root':'claimed-control-primary','cost':2},
             {'role':'U3-alt','measurand':'response-at-U3','root':'claimed-independent-meter','cost':2}]
}

class PrivateProbeReceiver:
    """Only virtual host code owns readings; read receipts persist with idempotent keys."""
    def __init__(self,path,samples):
        self.db=sqlite3.connect(str(path))
        self.db.execute('CREATE TABLE IF NOT EXISTS contract(id INTEGER PRIMARY KEY,body TEXT NOT NULL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS receipts(id TEXT PRIMARY KEY,body TEXT NOT NULL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS counters(role TEXT PRIMARY KEY,n INTEGER NOT NULL)')
        self.samples=samples
        contract=json.dumps(samples,sort_keys=True)
        prior=self.db.execute('SELECT body FROM contract WHERE id=1').fetchone()
        if prior and prior[0]!=contract:
            self.close();raise ValueError('private probe world changed on restart')
        if not prior:
            with self.db:self.db.execute('INSERT INTO contract VALUES(1,?)',(contract,))
    def read(self,domain,role,key):
        prior=self.db.execute('SELECT body FROM receipts WHERE id=?',(key,)).fetchone()
        if prior:
            receipt=json.loads(prior[0])
            if receipt['domain']!=domain or receipt['role']!=role:
                raise ValueError('receipt reused for different probe')
            return receipt
        source=self.samples.get(domain,{}).get(role)
        if source is None:raise ValueError('private receiver role absent')
        row=self.db.execute('SELECT n FROM counters WHERE role=?',(domain+':'+role,)).fetchone()
        index=row[0] if row else 0
        if index>=len(source):raise ValueError('private sample exhausted')
        receipt={'id':key,'domain':domain,'role':role,'value':source[index],
                 'radius':0,'sequence':index+1}
        with self.db:
            self.db.execute('INSERT INTO receipts VALUES(?,?)',(key,json.dumps(receipt,sort_keys=True)))
            self.db.execute('INSERT OR REPLACE INTO counters VALUES(?,?)',(domain+':'+role,index+1))
        return receipt
    def close(self):self.db.close()


def select_probe(stage, domain, role, catalog, samples):
    """Public selection by role, measurand, lineage and price; no outcome input."""
    candidates=catalog[domain]
    target=next((p for p in candidates if p['role']==role),None)
    if target is None: return None
    if stage=='REPEAT':return target
    if stage=='INDEPENDENT':
        options=[p for p in candidates if p['role']!=role and p['measurand']==target['measurand']
                 and p.get('root') and target.get('root') and p['root']!=target['root']]
        return min(options,key=lambda p:(p['cost'],p['role'])) if options else None
    return None
