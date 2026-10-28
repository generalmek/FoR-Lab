"""FoR S30: continuing agent coordinate, goal revisions and authorization provenance.

The environment supplies changes to its publicly expressed constraints. Goals are NOT
claimed to arise autonomously. One S29 life-cycle still does inquiry, construction,
action, monitoring and revisable Worldview, without host access to hidden physical law.
"""
import re
from s29_cycle import S29Agent
from s22_semantic_kernel import valid_dependency_path,revoke
from s28_concepts import canonical

class S30Agent(S29Agent):
    def __init__(self,*args,goal_revision_enabled=True,**kwargs):
        if type(goal_revision_enabled)!=bool:raise ValueError('goal_revision_enabled must be bool')
        self.goal_revision_enabled=goal_revision_enabled
        super().__init__(*args,**kwargs)
        try:
            s=self.state();contract={'version':'S30-goal-coordinate-v1','goal_revision':goal_revision_enabled}
            if 's30' not in s:
                s['s30']={'contract':contract,'goals':{},'events':{},'history':[],
                          'coordinate':{},'total_goal_changes':0}
                self.save(s)
            elif s['s30']['contract']!=contract:raise ValueError('changed S30 contract on restart')
        except BaseException:self.close();raise

    def add_task(self,task_id,world,*,output_floor=0):
        if type(output_floor)!=int or not 0<=output_floor<=2:raise ValueError('unsupported Compass floor')
        result=super().add_task(task_id,world,output_floor=output_floor)
        s=self.state();g=s['s30']['goals']
        if task_id not in g:
            node=f's30:goal:{task_id}:v0'
            s['s22']['nodes'][node]={'kind':'goal_constraint','valid':True,'depends':[],
                'task':task_id,'version':0,'floor':output_floor,'origin':'PUBLIC_TASK'}
            g[task_id]={'node':node,'version':0,'floor':output_floor}
            self._update_coordinate(s)
            self.save(s)
        return result

    def _update_coordinate(self,s):
        tasks=s['s29']['tasks'];goals=s['s30']['goals']
        s['s30']['coordinate']={
          'tick':s['s29']['tick'],'budget_left':s['shared_budget'],
          'active_tasks':[tid for tid,t in tasks.items() if t['phase'] not in ('DONE','STOPPED')],
          'tasks':{tid:{'phase':t['phase'],'generation':t['generation'],
              'current_model':t['model'],'goal_version':goals.get(tid,{}).get('version'),
              'goal_floor':goals.get(tid,{}).get('floor'),
              'question':t['question'],'last_action':t['last_action']}
                for tid,t in tasks.items()}}

    def revise_goal(self,event_id,task_id,new_floor):
        """Observe a public goal/constraint event. Never observes hidden host truth.

        An event ID is immutable. Replayed same content is idempotent. Goal revision
        leaves physical model untouched; reauthorizes via a new dependent model view.
        """
        if not isinstance(event_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,48}',event_id):
            raise ValueError('invalid event identifier')
        if type(new_floor)!=int or not 0<=new_floor<=2:raise ValueError('invalid public floor')
        s=self.state();cy=s['s30'];goals=cy['goals'];tasks=s['s29']['tasks']
        if task_id not in goals or task_id not in tasks:raise ValueError('unknown task')
        record={'task':task_id,'new_floor':new_floor}
        previous=cy['events'].get(event_id)
        if previous is not None:
            if previous!=record:raise ValueError('event ID collision')
            return {'kind':'GOAL_EVENT_REPLAY','task':task_id,'event_id':event_id}
        if not self.goal_revision_enabled:
            cy['events'][event_id]=record;self.save(s)
            return {'kind':'GOAL_CHANGE_IGNORED_ABLATION','task':task_id,'event_id':event_id}
        g=goals[task_id];old=g['node'];t=tasks[task_id];nodes=s['s22']['nodes']
        cy['events'][event_id]=record
        if new_floor==g['floor']:
            self.save(s)
            return {'kind':'GOAL_UNCHANGED','task':task_id,'event_id':event_id}
        revoked=revoke(nodes,old,'PUBLIC_GOAL_REPLACED')
        version=g['version']+1;node=f's30:goal:{task_id}:v{version}'
        nodes[node]={'kind':'goal_constraint','valid':True,'depends':[],
                     'task':task_id,'version':version,'floor':new_floor,'origin':'PUBLIC_GOAL_EVENT',
                     'event_id':event_id}
        g.update({'version':version,'node':node,'floor':new_floor})
        t['public']['output_floor']=new_floor
        # Reuse a still-valid factual model across a normative goal change. A new
        # model *view* has a fresh action identity and a graph edge to the old model.
        old_model=t.get('model')
        if old_model and valid_dependency_path(nodes,old_model):
            generation=t['generation']+1
            alias=f's29:concept:{task_id}:{generation}'
            if alias in nodes:raise ValueError('duplicate model generation')
            source=nodes[old_model]
            nodes[alias]={'kind':'constructed_predicate','domain':'s30','valid':True,
                'depends':[old_model],'clauses':source['clauses'],'task':task_id,
                'generation':generation,'scope':'goal-reauthorized model view'}
            t['generation']=generation;t['model']=alias;t['phase']='READY';t['question']=None
            t['observations']=[]
        elif t['phase'] in ('DONE','STOPPED','READY','MONITOR'):
            t['generation']+=1;t['observations']=[];t['model']=None;t['question']=None
            t['phase']='INQUIRY'
        cy['total_goal_changes']+=1
        entry={'tick':s['s29']['tick'],'kind':'GOAL_REVISED','task':task_id,
               'old_goal':old,'new_goal':node,'new_floor':new_floor,'revoked':revoked,
               'reused_physical_model':bool(old_model and t['model'] and t['model']!=old_model)}
        cy['history'].append(entry)
        self._update_coordinate(s)
        self.save(s)
        return entry

    def _persist(self,s):
        # S29 creates permission BEFORE physical effect is persisted. This hook
        # establishes a goal provenance edge in the SAME sqlite state commit as
        # that effect/permission, rather than in a later transaction.
        evt=s['s29']['events'][-1] if s['s29']['events'] else None
        if evt and evt['kind']=='LATE_CONTRADICTION_REOPEN':
            # A goal-specific model view can depend on an earlier physical model.
            # When fresh evidence falsifies its prediction, invalidate that old
            # continuing physical claim as well, not only the newest alias.
            root=evt['old_model'];nodes=s['s22']['nodes'];seen=set()
            while root in nodes and root not in seen and nodes[root].get('scope')=='goal-reauthorized model view':
                seen.add(root)
                parent=nodes[root].get('depends',[])
                if len(parent)!=1:break
                root=parent[0]
            if root in nodes and nodes[root].get('valid',False):
                changed=revoke(nodes,root,'S30_LATE_WORLD_CHANGE')
                s['s30']['history'].append({'tick':s['s29']['tick'],
                    'kind':'HISTORICAL_MODEL_INVALIDATED','task':evt['task'],
                    'model':root,'revoked':changed})
        if evt and evt['kind'] in ('ACTION_PERFORMED','ACTION_MISMATCH_REOPEN'):
            tid=evt['task'];goal=s['s30']['goals'][tid]['node']
            if not valid_dependency_path(s['s22']['nodes'],goal):
                raise RuntimeError('permission cannot depend on an invalid goal')
            aid=s['s29']['tasks'][tid]['act_id'];permission=f's29:decision:{aid}'
            if permission not in s['s22']['nodes']:raise RuntimeError('missing executed permission')
            deps=s['s22']['nodes'][permission]['depends']
            if goal not in deps:deps.append(goal)
        self._update_coordinate(s)
        if evt and evt['kind'] not in ('MONITOR_CONFIRMED','ACTIVE_MEASUREMENT'):
            s['s30']['history'].append({'tick':s['s29']['tick'],'kind':evt['kind'],
                 'task':evt['task'],'budget':s['shared_budget']})
        super()._persist(s)

    def tick_concepts(self,worlds):
        s=self.state();goals=s['s30']['goals']
        for tid,t in s['s29']['tasks'].items():
            if tid not in goals:raise ValueError('missing public goal provenance')
            if t['phase']=='READY' and not valid_dependency_path(s['s22']['nodes'],goals[tid]['node']):
                t['phase']='STOPPED';self._update_coordinate(s);self.save(s)
                return {'kind':'INVALID_GOAL_STOP','task':tid}
        return super().tick_concepts(worlds)
