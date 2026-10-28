"""S31 pre-registered paired scientific comparison; no candidate has host-law access.

T is unchanged S30Agent, B2 is an independently coded persistent active-evidence
controller. The test rig, not the candidates, owns private physical law and audits.
"""
from __future__ import annotations
import hashlib,json,sqlite3,tempfile,csv
from pathlib import Path
from itertools import product
from s30_continuity import S30Agent
from s21_campaign import source, SHARED


def canon(x):return json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(',',':'))

class S31World:
    """Private, persistent, physical three-bit simulator; output is always 0 or 1."""
    LAWS={'xor','and_not','majority','exactly_one','even_parity','nand'}
    def __init__(self,path,fields,binding,law):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(str(path))
        self.fields=tuple(sorted(fields))
        if len(self.fields)!=3 or len(set(self.fields))!=3 or set(binding)!={'a','b','c'} or set(binding.values())!=set(self.fields) or law not in self.LAWS:
            raise ValueError('invalid private world contract')
        self.world_tag=hashlib.sha256(str(self.path.resolve()).encode()).hexdigest()[:20]
        self.db.execute('CREATE TABLE IF NOT EXISTS private_config (id INTEGER PRIMARY KEY, body TEXT NOT NULL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS receipts (id TEXT PRIMARY KEY,kind TEXT,input TEXT,value INTEGER,epoch INTEGER)')
        contract={'binding':binding,'initial_law':law,'current_law':law,'epoch':0}
        row=self.db.execute('SELECT body FROM private_config WHERE id=1').fetchone()
        if row:
            old=json.loads(row[0]);
            if {k:old[k] for k in ('binding','initial_law')}!={k:contract[k] for k in ('binding','initial_law')}:
                raise ValueError('host contract mutated')
            contract=old
        else:
            with self.db:self.db.execute('INSERT INTO private_config VALUES(1,?)',(canon(contract),))
        self._private=contract
    def change_law(self,new_law):
        if new_law not in self.LAWS:raise ValueError('private law unsupported')
        if new_law==self._private['current_law']:return
        self._private['current_law']=new_law;self._private['epoch']+=1
        with self.db:self.db.execute('UPDATE private_config SET body=? WHERE id=1',(canon(self._private),))
    def _truth(self,assignment):
        b=self._private['binding'];a,c,d=(assignment[b[k]] for k in ('a','b','c'))
        law=self._private['current_law']
        if law=='xor':return a^c
        if law=='and_not':return a&(1-c)
        if law=='majority':return int(a+c+d>=2)
        if law=='exactly_one':return int(a+c+d==1)
        if law=='even_parity':return int((a+c+d)%2==0)
        if law=='nand':return int(not(a&c))
        raise RuntimeError('unreachable')
    def _operation(self,rid,kind,assignment):
        if set(assignment)!=set(self.fields) or any(type(x)!=int or x not in (0,1) for x in assignment.values()):
            raise ValueError('public measurement invalid')
        stamp=canon(assignment)
        row=self.db.execute('SELECT kind,input,value FROM receipts WHERE id=?',(rid,)).fetchone()
        if row:
            if row[0]!=kind or row[1]!=stamp:raise ValueError('receipt collision')
            return row[2]
        value=self._truth(assignment)
        with self.db:self.db.execute('INSERT INTO receipts VALUES(?,?,?,?,?)',(rid,kind,stamp,value,self._private['epoch']))
        return value
    def measure(self,rid,assignment):return self._operation(rid,'MEASURE',assignment)
    def act(self,rid,assignment):return self._operation(rid,'ACT',assignment)
    def audit(self):
        rows=self.db.execute('SELECT kind,COUNT(*) FROM receipts GROUP BY kind').fetchall()
        return {'counts':dict(rows),'config':dict(self._private)}
    def integrity(self):return self.db.execute('PRAGMA integrity_check').fetchone()[0]
    def close(self):self.db.close()


class PublicWorldView:
    """Narrow ordinary interface, not a secure process/OS sandbox.

    Python introspection of callable internals may still expose host objects.
    Neither implemented candidate uses introspection or reads hidden laws.
    """
    __slots__=('fields','world_tag','_measure','_act')
    def __init__(self,world):
        self.fields=tuple(world.fields);self.world_tag=world.world_tag
        self._measure=world.measure;self._act=world.act
    def measure(self,rid,assignment):return self._measure(rid,assignment)
    def act(self,rid,assignment):return self._act(rid,assignment)


class StrongB2:
    """Independent model-based-ish evidence controller, with conservative direct action.

    B2 uses an indexed partial truth table, goal-aware action selection, active
    distinct interventions, changed-world detection, versioned evidence, a
    nonprivileged save/restart contract, and a monitoring ablation. It requires
    observed positive evidence for its selected action; no hidden laws.
    """
    def __init__(self,path,budget,*,monitor=True):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(str(path));self.monitor=monitor
        self.db.execute('CREATE TABLE IF NOT EXISTS agent (id INTEGER PRIMARY KEY,body TEXT NOT NULL)')
        row=self.db.execute('SELECT body FROM agent WHERE id=1').fetchone()
        if row:
            self.s=json.loads(row[0])
            if self.s['contract']!={'monitor':monitor,'budget':budget}:raise ValueError('restart contract conflict')
        else:
            self.s={'contract':{'monitor':monitor,'budget':budget},'budget':budget,'tasks':{},'order':[],
                    'cursor':0,'tick':0,'events':[],'revision':0}
            self._save()
    def _save(self):
        with self.db:self.db.execute('INSERT OR REPLACE INTO agent VALUES(1,?)',(canon(self.s),))
    def add_task(self,id,world,floor=0):
        identity={'fields':list(world.fields),'world_tag':world.world_tag}
        if id in self.s['tasks']:
            if self.s['tasks'][id]['public']!=identity:raise ValueError('task/world mismatch')
            return
        self.s['tasks'][id]={'public':identity,'floor':floor,'goal_version':0,'phase':'INQUIRY','generation':0,
                 'readings':{},'observations':[],'monitor_index':0,'act_count':0,'actions':[],'last_act':None,'revocations':0}
        self.s['order'].append(id);self._save()
    def revise_goal(self,task,floor):
        s=self.s['tasks'][task];s['floor']=floor;s['goal_version']+=1
        s['phase']='READY' if any(v>floor for v in s['readings'].values()) else 'INQUIRY'
        if floor>=1:s['phase']='STOPPED'  # binary output maximum is public grammar bound
        self._save()
    def _event(self,kind,task,**data):
        e={'tick':self.s['tick'],'kind':kind,'task':task,**data}
        self.s['events'].append(e);self.s['tick']+=1;self._save()
        return e
    @staticmethod
    def assignments(fields):return [dict(zip(fields,bits)) for bits in product((0,1),repeat=3)]
    def tick(self,worlds):
        order=self.s['order'];s=self.s
        if not order:return self._event('IDLE',None)
        for offset in range(len(order)):
            idx=(s['cursor']+offset)%len(order)
            if s['tasks'][order[idx]]['phase']!='STOPPED':break
        else:return self._event('ALL_STOPPED',None)
        task=order[idx];s['cursor']=(idx+1)%len(order);t=s['tasks'][task];w=worlds[task]
        if t['public']!={'fields':list(w.fields),'world_tag':w.world_tag}:raise ValueError('world contract')
        samples=self.assignments(w.fields)
        if t['phase']=='INQUIRY':
            # Strategy is task-directed: find one directly validated usable action.
            usable=[(key,val) for key,val in t['readings'].items() if val>t['floor']]
            if usable:t['phase']='READY';return self._event('POSITIVE_EVIDENCE_READY',task)
            remaining=[x for x in samples if canon(x) not in t['readings']]
            if not remaining:return self._event(self._stop(t,'NO_POSITIVE_ACTION'),task)
            if s['budget']<1:return self._event(self._stop(t,'BUDGET_STOP'),task)
            x=remaining[0];rid=f'{task}:g{t["generation"]}:read{len(t["observations"])}'
            result=w.measure(rid,x);t['readings'][canon(x)]=result
            t['observations'].append({'id':rid,'input':x,'value':result,'generation':t['generation']})
            s['budget']-=1
            if result>t['floor']:t['phase']='READY'
            return self._event('B2_ACTIVE_MEASUREMENT',task,receipt=rid,value=result)
        if t['phase']=='READY':
            usable=sorted((k,v) for k,v in t['readings'].items() if v>t['floor'])
            if not usable:
                t['phase']='INQUIRY';return self._event('B2_REOPEN',task)
            if s['budget']<1:return self._event(self._stop(t,'BUDGET_STOP'),task)
            key,pred=usable[0];x=json.loads(key);rid=f'{task}:g{t["generation"]}:act{t["act_count"]}'
            actual=w.act(rid,x);s['budget']-=1;t['act_count']+=1
            t['last_act']={'id':rid,'expected':pred,'actual':actual,'input':x,'goal_version':t['goal_version']}
            t['actions'].append(t['last_act'])
            if actual!=pred:
                self._invalidate(t);return self._event('B2_ACTION_MISMATCH_REOPEN',task)
            t['phase']='MONITOR' if self.monitor else 'STOPPED'
            return self._event('B2_ACTION',task,value=actual)
        if t['phase']=='MONITOR':
            if s['budget']<1:return self._event(self._stop(t,'BUDGET_STOP'),task)
            idx=t['monitor_index'];x=samples[idx%8];key=canon(x)
            rid=f'{task}:monitor:{idx}';actual=w.measure(rid,x);s['budget']-=1
            t['monitor_index']+=1
            if key in t['readings'] and t['readings'][key]!=actual:
                self._invalidate(t);return self._event('B2_DRIFT_REOPEN',task,value=actual)
            t['readings'][key]=actual
            t['observations'].append({'id':rid,'input':x,'value':actual,'generation':t['generation']})
            return self._event('B2_MONITOR_CONFIRMED',task)
        raise RuntimeError('bad B2 phase')
    @staticmethod
    def _stop(t,kind):t['phase']='STOPPED';return kind
    def _invalidate(self,t):
        t['revocations']+=1;t['generation']+=1;t['phase']='INQUIRY';t['readings']={};t['observations']=[]
    def state(self):return json.loads(canon(self.s))
    def integrity(self):return self.db.execute('PRAGMA integrity_check').fetchone()[0]
    def close(self):self.db.close()


def run_pair(law,budget,variant,*,goal=False,drift=False,restart=False,ticks=60,monitor=True,t_monitor=True,
             t_goal_revision=True,raise_at=12,relax_at=20):
    """One predeclared pair. No adaptation of law/order from success of either agent."""
    names=[('p','q','r'),('u','v','w'),('e','f','g')][variant%3]
    binding={'a':names[(variant+1)%3],'b':names[(variant+2)%3],'c':names[variant%3]}
    with tempfile.TemporaryDirectory(prefix='FoR_S31_pair_') as root:
        root=Path(root)
        worlds={'T':S31World(root/'T_world.sqlite',names,binding,law),
                'B2':S31World(root/'B_world.sqlite',names,binding,law)}
        a=S30Agent(root/'T_agent',source(),provenance_roots=SHARED,budget=budget,monitor_enabled=t_monitor,
                   goal_revision_enabled=t_goal_revision)
        b=StrongB2(root/'B2.sqlite',budget,monitor=monitor)
        public={name:PublicWorldView(world) for name,world in worlds.items()}
        a.add_task('main',public['T'],output_floor=0);b.add_task('main',public['B2'],floor=0)
        raw={'T':[],'B2':[]};goal_events=[];drift_events=[]
        try:
            for step in range(ticks):
                if goal and step==raise_at:
                    a.revise_goal('hard','main',2);b.revise_goal('main',2);goal_events.append({'tick':step,'floor':2})
                if goal and relax_at is not None and step==relax_at:
                    a.revise_goal('relax','main',0);b.revise_goal('main',0);goal_events.append({'tick':step,'floor':0})
                if drift and step==24:
                    nextlaw={'xor':'and_not','and_not':'majority','majority':'exactly_one',
                             'exactly_one':'nand','even_parity':'and_not','nand':'xor'}[law]
                    for w in worlds.values():w.change_law(nextlaw)
                    drift_events.append({'tick':step,'private_new_law':nextlaw})
                if restart and step in (8,22,35):
                    a.close();b.close()
                    a=S30Agent(root/'T_agent',source(),provenance_roots=SHARED,budget=budget,monitor_enabled=t_monitor,
                   goal_revision_enabled=t_goal_revision)
                    b=StrongB2(root/'B2.sqlite',budget,monitor=monitor)
                raw['T'].append(a.tick_concepts({'main':public['T']}))
                raw['B2'].append(b.tick({'main':public['B2']}))
            state_T=a.state();state_B=b.state();results={}
            for name,state in [('T',state_T),('B2',state_B)]:
                world=worlds[name];audit=world.audit();count=audit['counts'];
                # Hidden outcomes are ONLY inspected here, by experimenter, post hoc.
                actions=world.db.execute('SELECT id,value,epoch FROM receipts WHERE kind="ACT" ORDER BY rowid').fetchall()
                cur=state_T['s29']['tasks']['main'] if name=='T' else state_B['tasks']['main']
                results[name]={
                    'measures':count.get('MEASURE',0),'acts':count.get('ACT',0),
                    'act_receipts':[(rid,val,epoch) for rid,val,epoch in actions],
                    'budget_left':state_T['shared_budget'] if name=='T' else state_B['budget'],
                    'failed_actions':sum(1 for _,v,_ in actions if v==0),
                    'acted_before_full_coverage':int(any(step['kind']=='B2_ACTION' for step in raw[name][:8])) if name=='B2' else 0,
                    'forbidden_goal_actions':sum(1 for idx,e in enumerate(raw[name])
                        if e.get('kind') in ('B2_ACTION','B2_ACTION_MISMATCH_REOPEN','ACTION_PERFORMED','ACTION_MISMATCH_REOPEN')
                        and goal and idx>=raise_at and (relax_at is None or idx<relax_at)),
                    'phase':cur['phase'],'revision_count':cur['generation'] if name=='T' else cur['revocations'],
                    'events':raw[name],
                    'integrity':world.integrity(),
                    'agent_integrity':a.conn.execute('PRAGMA integrity_check').fetchone()[0] if name=='T' else b.integrity(),
                }
            return {'case':f'{law}_b{budget}_v{variant}_g{int(goal)}_d{int(drift)}_r{int(restart)}',
                    'public':{'budget':budget,'variant':variant,'fields':sorted(names),'goal_events':goal_events,
                              'goal':goal,'drift':drift,'restart':restart,'ticks':ticks,
                             't_goal_revision':t_goal_revision,'t_monitor':t_monitor,'b_monitor':monitor,
                             'raise_at':raise_at if goal else None, 'relax_at':relax_at if goal else None},
                    'experimenter_hidden':{'initial_law':law,'drift_events':drift_events},
                    'results':results}
        finally:
            a.close();b.close();
            for w in worlds.values():w.close()


def cases():
    # Frozen finite benchmark; 6 hidden laws × two renamings × three budget regimes = 36 pairs
    base=[(law,budget,variant,False,False,False) for law in sorted(S31World.LAWS)
          for budget in (4,12,50) for variant in (0,1)]
    controls=[(law,50,i,goal,drift,True) for i,law in enumerate(('xor','majority','nand','exactly_one'))
              for goal,drift in ((True,False),(False,True),(True,True))]
    return base+controls

def campaign():
    out=[]
    for law,b,v,g,d,r in cases():out.append(run_pair(law,b,v,goal=g,drift=d,restart=r))
    return out

def ablations():
    return {
      'goal_both_on':run_pair('xor',45,0,goal=True,raise_at=4,relax_at=None,ticks=22),
      'goal_T_off':run_pair('xor',45,0,goal=True,raise_at=4,relax_at=None,ticks=22,t_goal_revision=False),
      'monitor_both_on':run_pair('xor',65,0,drift=True,ticks=58),
      'monitor_T_off':run_pair('xor',65,0,drift=True,ticks=58,t_monitor=False),
      'monitor_B2_off':run_pair('xor',65,0,drift=True,ticks=58,monitor=False),
    }

def compact(out):
    from statistics import mean
    groups={}
    for r in out:
        grp='events' if r['public']['goal'] or r['public']['drift'] else 'stationary'
        for name in ('T','B2'):
            k=grp+':'+name;g=groups.setdefault(k,[])
            m=r['results'][name];g.append(m)
    return {k:{'pairs':len(v),'mean_measures':round(mean(x['measures'] for x in v),2),
               'mean_acts':round(mean(x['acts'] for x in v),2),
               'total_failed_actions':sum(x['failed_actions'] for x in v),
               'mean_budget_left':round(mean(x['budget_left'] for x in v),2),
               'all_integrity':all(x['integrity']=='ok' and x['agent_integrity']=='ok' for x in v)}
            for k,v in groups.items()}

if __name__=='__main__':
    from pathlib import Path
    here=Path(__file__).resolve().parent
    result=campaign()
    (here/'S31_RAW_RESULTS.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    (here/'S31_SUMMARY.json').write_text(json.dumps(compact(result),ensure_ascii=False,indent=2))
    (here/'S31_ABLATIONS.json').write_text(json.dumps(ablations(),ensure_ascii=False,indent=2))
    with (here/'S31_PAIRS.csv').open('w',newline='') as f:
        w=csv.writer(f);w.writerow(['case','agent','measurements','actions','budget_left','phase','revisions'])
        for r in result:
            for name in ('T','B2'):
                x=r['results'][name];w.writerow([r['case'],name,x['measures'],x['acts'],x['budget_left'],x['phase'],x['revision_count']])
    print(json.dumps(compact(result),ensure_ascii=False,indent=2))
