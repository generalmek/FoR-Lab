"""Host adapter: pinned baseline plus explicitly selected experimental subclasses."""
import json
import sqlite3
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'engine'))
from procedural_cycle import ProceduralCycle, ProcedureWorld
from research_agenda import propose
from event_agenda import propose_from_observed_contexts
from composition_cycle import CompositionCycle
from horizon_cycle import HorizonCycle


class ObservableExperiment:
    def __init__(self, data_dir=None):
        self.root = Path(data_dir or ROOT / 'data')
        self.root.mkdir(parents=True, exist_ok=True)
        self.host = sqlite3.connect(self.root / 'host.sqlite')
        self.host.executescript('''CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY,config TEXT);
            CREATE TABLE IF NOT EXISTS current(id INTEGER PRIMARY KEY,session TEXT);
            CREATE TABLE IF NOT EXISTS observations(id INTEGER PRIMARY KEY,session TEXT,body TEXT);
            CREATE TABLE IF NOT EXISTS interventions(id INTEGER PRIMARY KEY,session TEXT,body TEXT);
            CREATE TABLE IF NOT EXISTS public_context_events(id INTEGER PRIMARY KEY,session TEXT,context INTEGER);''')
        self.host.commit()
        row = self.host.execute('SELECT session FROM current WHERE id=1').fetchone()
        self.session = row[0] if row else None
        self.paused = True
        if not self.session:
            self.start_episode('recovery')

    def config(self):
        return json.loads(self.host.execute('SELECT config FROM sessions WHERE id=?',(self.session,)).fetchone()[0])

    def save_config(self, c):
        with self.host:
            self.host.execute('UPDATE sessions SET config=? WHERE id=?',(json.dumps(c),self.session))

    def start_episode(self, scenario='recovery', budget=160):
        if scenario not in ('stable','recovery','resource_stop','exploration','quadratic','outside_grammar','constructive','horizon') or type(budget) is not int or not 1 <= budget <= 300:
            raise ValueError('Invalid bounded scenario/budget')
        self.paused = True
        self.session = uuid.uuid4().hex
        (self.root / self.session).mkdir()
        c = dict(scenario=scenario,budget=budget,law=[1,2,0],context=1,gain=1,bias=0,
                 sample_price=10000 if scenario=='resource_stop' else 1,
                 surprise=scenario=='recovery',ticks=0,inflight=False)
        if scenario=='exploration':c.update(law=[1,2,1],research=[],completed_contexts=[],research_status='ACTIVE')
        if scenario=='horizon':c.update(future_stage=False,initial_resource=38)
        with self.host:
            self.host.execute('INSERT INTO sessions VALUES(?,?)',(self.session,json.dumps(c)))
            self.host.execute('INSERT OR REPLACE INTO current VALUES(1,?)',(self.session,))
        r,w = self.open_engine()
        r.close(); w.close()
        return self.snapshot()

    def open_engine(self):
        c = self.config(); b,a,q = c['law']
        folder = self.root / self.session
        power=2 if c['scenario']=='quadratic' else (4 if c['scenario'] in ('outside_grammar','constructive') else None)
        law=lambda u,v:b+a*u+q*u*v+(u**power if power else 0)
        w = ProcedureWorld(folder/'world.sqlite',law,c['context'],
                           initial=c.get('initial_resource',1000),error_bound=0,gain=c['gain'],bias=c['bias'],sample_price=c['sample_price'])
        cls=HorizonCycle if c['scenario']=='horizon' else (CompositionCycle if c['scenario']=='constructive' else ProceduralCycle)
        return cls(folder/'agent.sqlite'),w

    def intervention(self, kind):
        self.pause()
        c=self.config()
        if c['inflight']: raise RuntimeError('Interrupted tick: preserve evidence; manual reconciliation required')
        if kind=='sensor': c.update(gain=2,bias=3)
        elif kind=='process': c['law']=[2,3,0]
        elif kind=='cost': c['sample_price']=10000
        else: raise ValueError('Unknown intervention')
        with self.host:
            self.host.execute('INSERT INTO interventions(session,body) VALUES(?,?)',
                              (self.session,json.dumps(dict(kind=kind,config=c))))
            self.host.execute('UPDATE sessions SET config=? WHERE id=?',(json.dumps(c),self.session))

    def observe_context(self, value):
        """Sensor simulation: publish context value, not hidden process or status.
        An observed context is NOT automatically counted as completed research.
        """
        if type(value) is not int or not 1 <= value <= 256:
            raise ValueError('context sensor value outside experimental range')
        c=self.config()
        if c['scenario']!='exploration' or c['inflight']:
            raise RuntimeError('not a safe observation point')
        with self.host:
            cursor=self.host.execute('INSERT INTO public_context_events(session,context) VALUES(?,?)',(self.session,value))
        return cursor.lastrowid

    def public_context_observations(self):
        return [dict(id=i,context=v) for i,v in self.host.execute(
            'SELECT id,context FROM public_context_events WHERE session=? ORDER BY id',(self.session,))]

    def pause(self): self.paused=True
    def resume(self): self.paused=False

    def step(self, automatic=False):
        if automatic and self.paused: return self.snapshot()
        c=self.config()
        if c['inflight']: raise RuntimeError('Previous tick interrupted; no automatic replay. Export and inspect this session.')
        before=self.snapshot()
        # Agent task context is the authoritative provenance of completed research.
        # A host configuration edit alone is not an observation or verification.
        if (c['scenario']=='exploration' and before['life'] is not None
                and before['state'].get('context') != c['context']):
            c['research_status']='HOST_CONTEXT_MISMATCH'
            self.save_config(c)
            return self.snapshot()
        start_research=None
        if before['life'] and before['life']['status']=='DONE' and c['scenario']=='horizon' and not c['future_stage']:
            c.update(inflight=True,future_stage=True);self.save_config(c)
            r,w=self.open_engine()
            try:r.start_future(w,budget=before['state']['budget'])
            finally:r.close();w.close()
            c['inflight']=False;self.save_config(c)
            return self.snapshot()
        if before['life'] and before['life']['status'] in ('DONE','STOPPED'):
            if c['scenario']!='exploration' or before['life']['status']=='STOPPED':return before
            completed=sorted(set(c['completed_contexts']+[before['state']['context']]))
            start_research=propose(before['state'],completed)
            if start_research is None:
                start_research=propose_from_observed_contexts(
                    before['state'],completed,self.public_context_observations())
            if not start_research or before['state']['budget']<8:
                c.update(completed_contexts=completed,research_status='COVERAGE_COMPLETE' if not start_research else 'BUDGET_STOP')
                self.save_config(c);return self.snapshot()
            c.update(context=start_research['selected']['context'],completed_contexts=completed,
                     research_status='ACTIVE')
            c['research'].append(start_research)
        if c['ticks']>=100: self.pause(); raise RuntimeError('Host tick limit reached')
        c['inflight']=True; self.save_config(c)
        r,w=self.open_engine()
        original=w.apply_once
        def apply(op,u,target):
            current=self.config()
            if current['surprise']:
                current.update(law=[2,3,0],surprise=False)
                self.save_config(current)
                with self.host:
                    self.host.execute('INSERT INTO interventions(session,body) VALUES(?,?)',
                        (self.session,json.dumps(dict(kind='process_at_first_execution',law=[2,3,0]))))
                w.law=lambda u,v:2+3*u
            return original(op,u,target)
        w.apply_once=apply
        try:
            if start_research:
                # Continue with remaining operations, never a fresh per-question budget.
                r.next_goal(w,budget=before['state']['budget'])
            elif r.life() is None: r.begin(w,budget=c['budget'])
            else: r.tick(w)
        finally:
            r.close(); w.close()
        c=self.config(); c.update(inflight=False,ticks=c['ticks']+1)
        self.save_config(c)
        after=self.snapshot()
        record=dict(tick=c['ticks'],before_budget=before['state'].get('budget'),
                    resource_delta=after['balance']-before['balance'],snapshot=after)
        with self.host:
            self.host.execute('INSERT INTO observations(session,body) VALUES(?,?)',(self.session,json.dumps(record)))
        return after

    def snapshot(self):
        r,w=self.open_engine()
        try:
            s=r.state(); life=r.life()
            records={}
            for table in ('events','procedures','worldview_sets','model_revocations'):
                if table=='model_revocations':
                    records[table]=[dict(task=row[0],through_id=row[1],body=json.loads(row[2])) for row in r.db.execute('SELECT * FROM model_revocations')]
                else:
                    records[table]=[dict(id=row[0],body=json.loads(row[1])) for row in r.db.execute(f'SELECT * FROM {table}')]
            return dict(session=self.session,config=self.config(),state=s,life=life,beliefs=r.beliefs(),
                        balance=w.balance(),reserve=w.reserve,records=records,
                        intents=[dict(id=i,body=json.loads(b),status=t) for i,b,t in r.db.execute('SELECT * FROM intents')],
                        receipts=[dict(id=i,request=json.loads(q),result=json.loads(b)) for i,q,b in w.db.execute('SELECT * FROM receipts')])
        finally: r.close(); w.close()

    @staticmethod
    def finished(snap):
        life=snap['life'] or {}
        if life.get('status')=='STOPPED':return True
        if snap['config']['scenario']=='exploration':
            return snap['config'].get('research_status') in ('COVERAGE_COMPLETE','BUDGET_STOP','HOST_CONTEXT_MISMATCH')
        if snap['config']['scenario']=='horizon':
            return life.get('status')=='DONE' and snap['config'].get('future_stage',False)
        return life.get('status')=='DONE'

    def export_current_session(self):
        report=self.snapshot()
        report['observations']=[json.loads(x[0]) for x in self.host.execute('SELECT body FROM observations WHERE session=? ORDER BY id',(self.session,))]
        report['interventions']=[json.loads(x[0]) for x in self.host.execute('SELECT body FROM interventions WHERE session=? ORDER BY id',(self.session,))]
        path=self.root/self.session/'export.json'
        path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        return path

    def close(self): self.host.close()
