"""S32: bounded *local* epistemic sufficiency for a task-directed action.

Reuses the same S30 Worldview, persistent life-cycle and Compass. It does not
claim a full three-bit truth model from one positive observation, and never
acts on a value it has not itself measured in the current generation.
"""
from __future__ import annotations
import json
from s30_continuity import S30Agent
from s28_concepts import all_inputs, canonical, evaluate
from s22_semantic_kernel import valid_dependency_path, revoke

class S32Agent(S30Agent):
    def __init__(self,*args,local_sufficiency=True,**kwargs):
        if type(local_sufficiency) is not bool:raise ValueError('local_sufficiency must be bool')
        self.local_sufficiency=local_sufficiency
        super().__init__(*args,**kwargs)
        try:
            s=self.state();contract={'version':'S32-local-evidence-1','local_sufficiency':local_sufficiency}
            if 's32' not in s:
                s['s32']={'contract':contract,'events':[],'monitor_records':{}}
                self.save(s)
            elif s['s32']['contract']!=contract:raise ValueError('changed S32 contract on restart')
            else:
                s['s32'].setdefault('monitor_records',{})
                self.save(s)
        except BaseException:
            self.close();raise

    def _local_basis(self,nodes,model):
        """Return source point for local model or its later goal-revised alias."""
        seen=set();p=model
        while p and p not in seen:
            seen.add(p)
            node=nodes.get(p)
            if not node or not node.get('valid',False):return None
            if node.get('evidence_scope')=='LOCAL_POSITIVE_POINT':
                deps=node.get('depends',[])
                if len(deps)!=1 or not valid_dependency_path(nodes,deps[0]):return None
                return (node.get('point'),node.get('value'),p)
            if node.get('scope')=='goal-reauthorized model view':
                deps=node.get('depends',[])
                if len(deps)!=1:return None
                p=deps[0]
                continue
            return None
        return None

    def tick_concepts(self,worlds):
        if not self.local_sufficiency:return super().tick_concepts(worlds)
        s=self.state();order=s['s29']['order'];cy=s['s29']
        if not order:return super().tick_concepts(worlds)
        current=None
        for offset in range(len(order)):
            idx=(cy['cursor']+offset)%len(order)
            tid=order[idx]
            if cy['tasks'][tid]['phase']!='STOPPED':
                current=(idx,tid);break
        if current is None:return super().tick_concepts(worlds)
        idx,tid=current;t=cy['tasks'][tid]
        if t['phase'] not in ('INQUIRY','MONITOR'):return super().tick_concepts(worlds)
        w=worlds.get(tid)
        if w is None or t['public']['fields']!=list(w.fields) or t['public']['world_tag']!=w.world_tag:
            raise ValueError('public world mismatch')
        if t['phase']=='MONITOR':
            basis=self._local_basis(s['s22']['nodes'],t.get('model'))
            if not basis:return super().tick_concepts(worlds)
            point,expected,root=basis
            cy['cursor']=(idx+1)%len(order)
            if s['shared_budget']<1:
                t['phase']='STOPPED';evt=self._event(s,'BUDGET_STOP',tid)
            else:
                # Two distinct epistemic claims: the action point is established
                # positively; other points are only monitor baselines, not
                # predicted negatives. Cycling lets changed unmodeled regions be
                # noticed without pretending a complete world model exists.
                records=s['s32']['monitor_records'].setdefault(root,{canonical(point):expected})
                i=t['monitor_index'];probe=all_inputs(w.fields)[i%8]
                rid=f'{tid}:local_monitor:{i}'
                result=w.measure(rid,probe)
                s['shared_budget']-=1;t['monitor_index']+=1
                nodes=s['s22']['nodes'];nodes['s29:receipt:'+rid]={
                    'kind':'monitor_measurement','valid':True,'domain':'s32','task':tid,
                    'input':probe,'value':result,'depends':[]}
                key=canonical(probe);before=records.get(key)
                if before is not None and result!=before:
                    invalidated=revoke(nodes,root,'OBSERVED_WORLD_DRIFT')
                    if t['model']!=root:invalidated+=revoke(nodes,t['model'],'OBSERVED_WORLD_DRIFT')
                    t['generation']+=1;t['observations']=[];t['model']=None;t['question']=None
                    t['phase']='INQUIRY';evt=self._event(s,'LOCAL_CONTRADICTION_REOPEN',tid,revoked=invalidated)
                elif before is None:
                    records[key]=result
                    evt=self._event(s,'LOCAL_MONITOR_NEW_BASELINE',tid,receipt=rid)
                else:evt=self._event(s,'LOCAL_MONITOR_CONFIRMED',tid,receipt=rid)
            self._persist(s)
            return dict(evt,phase=t['phase'],remaining=s['shared_budget'])
        # INQUIRY: one fresh intervention at a time. If it is directly usable,
        # a single-point model is enough to license ONLY that same point.
        cy['cursor']=(idx+1)%len(order)
        if s['shared_budget']<1:
            t['phase']='STOPPED';evt=self._event(s,'BUDGET_STOP',tid)
        else:
            samples=all_inputs(w.fields);i=len(t['observations'])
            if i>=len(samples):
                t['phase']='CONSTRUCT';evt=self._event(s,'FULL_COVERAGE_CONSTRUCTION',tid)
            else:
                x=samples[i];rid=f'{tid}:g{t["generation"]}:read{i}'
                y=w.measure(rid,x);t['observations'].append({'id':rid,'input':x,'value':y})
                nodes=s['s22']['nodes'];nodes['s29:receipt:'+rid]={
                    'kind':'intervention_observation','domain':'s32','valid':True,'depends':[],
                    'value':y,'input':x,'task':tid,'generation':t['generation']}
                s['shared_budget']-=1
                if y>t['public']['output_floor']:
                    key=f's29:concept:{tid}:{t["generation"]}'
                    nodes[key]={'kind':'constructed_predicate','valid':True,'domain':'s32',
                        'depends':['s29:receipt:'+rid],'clauses':[dict(x)],'task':tid,
                        'generation':t['generation'],'scope':'one directly measured positive intervention',
                        'evidence_scope':'LOCAL_POSITIVE_POINT','point':dict(x),'value':y}
                    t['model']=key;t['phase']='READY';t['question']=None
                    evt=self._event(s,'LOCAL_SUFFICIENT_EVIDENCE',tid,receipt=rid,model=key)
                else:
                    evt=self._event(s,'ACTIVE_MEASUREMENT',tid,receipt=rid,value=y)
                    if len(t['observations'])>=8:t['phase']='CONSTRUCT'
        self._persist(s)
        return dict(evt,phase=t['phase'],remaining=s['shared_budget'])
