"""S32 preregistered candidate vs unchanged StrongB2 under S31 worlds.

The original S31 code/data is not modified. Host law is private. Same public
measure/act operations, budgets and schedule. This is an internal comparison.
"""
from __future__ import annotations
import json,sqlite3,tempfile
from pathlib import Path
from s31_comparison import S31World,PublicWorldView,StrongB2,canon
from s32_core_sufficiency import S32Agent
from s21_campaign import source,SHARED


def run_pair32(law,budget,variant,*,ticks=28,goal=False,drift=False,restart=False,local_sufficiency=True):
    names=[('p','q','r'),('u','v','w'),('e','f','g')][variant%3]
    binding={'a':names[(variant+1)%3],'b':names[(variant+2)%3],'c':names[variant%3]}
    with tempfile.TemporaryDirectory(prefix='FoR_S32_pair_') as root:
        p=Path(root)
        hosts={'T32':S31World(p/'T32_world.sqlite',names,binding,law),
               'B2':S31World(p/'B2_world.sqlite',names,binding,law)}
        a=S32Agent(p/'T32_agent',source(),provenance_roots=SHARED,budget=budget,
                   local_sufficiency=local_sufficiency)
        b=StrongB2(p/'B2_agent.sqlite',budget)
        public={k:PublicWorldView(v) for k,v in hosts.items()}
        a.add_task('main',public['T32'],output_floor=0);b.add_task('main',public['B2'],floor=0)
        events={'T32':[],'B2':[]};changes=[]
        try:
            for step in range(ticks):
                if goal and step==12:
                    a.revise_goal('tighten','main',2);b.revise_goal('main',2)
                    changes.append({'tick':step,'kind':'goal','floor':2})
                if goal and step==20:
                    a.revise_goal('relax','main',0);b.revise_goal('main',0)
                    changes.append({'tick':step,'kind':'goal','floor':0})
                if drift and step==24:
                    newlaw={'xor':'and_not','and_not':'majority','majority':'exactly_one',
                            'exactly_one':'nand','even_parity':'and_not','nand':'xor'}[law]
                    for h in hosts.values():h.change_law(newlaw)
                    changes.append({'tick':step,'kind':'drift'}) # no private law to either candidate
                if restart and step in (8,22,35):
                    a.close();b.close()
                    a=S32Agent(p/'T32_agent',source(),provenance_roots=SHARED,budget=budget,
                               local_sufficiency=local_sufficiency)
                    b=StrongB2(p/'B2_agent.sqlite',budget)
                events['T32'].append(a.tick_concepts({'main':public['T32']}))
                events['B2'].append(b.tick({'main':public['B2']}))
            results={}
            for name,agent in [('T32',a),('B2',b)]:
                host=hosts[name];state=agent.state()
                receipts=host.db.execute('SELECT kind,value,epoch FROM receipts ORDER BY rowid').fetchall()
                decisions=[(v,e) for k,v,e in receipts if k=='ACT']
                results[name]={
                    'acts':len(decisions),'measures':sum(k=='MEASURE' for k,_,_ in receipts),
                    'failed_actions':sum(v==0 for v,e in decisions),
                    'actions_by_epoch':decisions,'remaining':(state['shared_budget'] if name=='T32' else state['budget']),
                    'integrity':host.integrity(),
                    'agent_integrity':(agent.conn.execute('PRAGMA integrity_check').fetchone()[0]
                                       if name=='T32' else agent.integrity()),
                    'events':events[name],
                    'local_scoped_models':sum(n.get('evidence_scope')=='LOCAL_POSITIVE_POINT'
                        for n in state['s22']['nodes'].values()) if name=='T32' else None,
                }
            return {'case':{'law':law,'budget':budget,'variant':variant,'ticks':ticks,
                            'goal':goal,'drift':drift,'restart':restart,'local_sufficiency':local_sufficiency},
                    'public_changes':changes,'results':results}
        finally:
            a.close();b.close()
            for h in hosts.values():h.close()


def cases():
    # Predeclared 12 low-budget + 12 medium-budget + 12 higher-budget
    # + 12 event/restart comparisons, same law classes and role permutations.
    laws=('xor','and_not','majority','exactly_one','even_parity','nand')
    cases=[]
    for budget in (4,12,50):
        for law in laws:
            for variant in (0,1):cases.append(dict(law=law,budget=budget,variant=variant,ticks=30))
    for law in laws:
        for variant in (0,1):
            cases.append(dict(law=law,budget=50,variant=variant,ticks=60,
                goal=(variant==1),drift=True,restart=True))
    return cases


def campaign():
    raw=[run_pair32(**kwargs) for kwargs in cases()]
    groups={}
    for r in raw:
        key='events' if r['case']['drift'] else 'b'+str(r['case']['budget'])
        g=groups.setdefault(key,{'pairs':0,'T32':{'acts':0,'measures':0,'fails':0},
                                 'B2':{'acts':0,'measures':0,'fails':0}})
        g['pairs']+=1
        for name in ('T32','B2'):
            res=r['results'][name];g[name]['acts']+=res['acts'];g[name]['measures']+=res['measures']
            g[name]['fails']+=res['failed_actions']
    return {'summary':groups,'cases':raw}

if __name__=='__main__':
    import sys
    out=Path(__file__).resolve().parent
    result=campaign()
    (out/'S32_RAW_RESULTS.json').write_text(json.dumps(result['cases'],ensure_ascii=False,indent=2),encoding='utf8')
    (out/'S32_SUMMARY.json').write_text(json.dumps(result['summary'],ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(result['summary'],ensure_ascii=False,indent=2))
