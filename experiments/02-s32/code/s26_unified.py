"""S26: shared typed planning for source inquiry, local revision, and actions.

The S16 legacy plan generator still constructs its own proposals; S26
independently plans admissible actions from its measured evidence before S25
allows effects. This is intentionally not a complete S16 replacement.
"""
import json
from s25_unified import S25Unified
from s25_gate import ActionDenied
from s26_planner import probe,validation,action
from s20_unified import canonical

class S26Unified(S25Unified):
    def __init__(self,*args,planning_enabled=True,**kwargs):
        if type(planning_enabled) is not bool:raise ValueError('planning_enabled must be bool')
        self._s26_enabled=planning_enabled
        super().__init__(*args,**kwargs)
        try:
            self.conn.execute('''CREATE TABLE IF NOT EXISTS s26_plan_audit
                (plan_id TEXT PRIMARY KEY, family TEXT, decision TEXT, provenance TEXT)''')
            s=self.state();contract={'enabled':planning_enabled,'language':'S26/typed-ops-v1'}
            if 's26' not in s:
                s['s26']={'contract':contract,'status':'ACTIVE' if planning_enabled else 'DISABLED'}
                self.save(s)
            elif s['s26']['contract']!=contract:
                raise ValueError('S26 planning contract changed on restart')
        except BaseException:
            self.close();raise
    def _audit(self,plan_id,family,decision,provenance=None):
        record=canonical(decision) if decision is not None else 'null'
        row=self.conn.execute('SELECT family,decision,provenance FROM s26_plan_audit WHERE plan_id=?',(plan_id,)).fetchone()
        args=(family,record,canonical(provenance))
        if row and row!=args:raise ActionDenied('S26_PLAN_ID_REUSED_WITH_DIFFERENT_CONTENT')
        if row is None:
            with self.conn:self.conn.execute('INSERT INTO s26_plan_audit VALUES(?,?,?,?)',(plan_id,*args))
    def plan_probe(self,stage,domain,role,catalog,readings):
        if not self._s26_enabled:return None
        state=self.state()
        p=probe(stage,domain,role,catalog,readings,budget=None)
        current=state['s23']['active']
        if current:
            plan_id='S26:PROBE:'+current['event_id']+':'+stage+':'+str(len(readings[stage])+1)
            self._audit(plan_id,'MEASURE',p,{'domain':domain,'role':role,'stage':stage})
        return p
    def plan_validation_probe(self,state,index):
        if not self._s26_enabled:return None
        catalog=[{'role':'U4','cost':2,'control':4,'root':'claimed-secondary'}]
        p=validation(catalog,None)
        self._audit('S26:VALIDATE:'+state['s24']['inquiry']+':'+str(index+1),'MEASURE',p,{'stage':'VALIDATE'})
        return p
    def plan_scoped_action(self,state,model,floor):
        if not self._s26_enabled:return None
        result=action(model['outputs'],floor,scope_ok=(model['scope']['context']==4),
                      permitted=True,budget=1)
        self._audit('S26:ACTION:'+state['s24']['inquiry'],'ACT',result,
                    {'basis':list(model['evidence']),'scope':model['scope']})
        return result
    def _synchronize(self,s):
        super()._synchronize(s)
        # S21's projection is older than S23: do not overwrite its new source
        # authorization with a pointer to the historically revoked attestation.
        episode=s.get('s23',{})
        history=episode.get('history',[])
        if (episode.get('status')=='VALIDATED' and episode.get('active') is None
            and history and history[-1].get('domain')=='source'
            and history[-1].get('status')=='VALIDATED'
            and s['s21']['permission'].get('status')=='VALID'):
            from s22_semantic_kernel import valid_dependency_path
            origin=history[-1]['event_id']
            root='source:s23:revised_basis:'+origin
            decision='decision:s23:reissued:'+origin
            nodes=s['s22']['nodes']
            if (valid_dependency_path(nodes,root) and valid_dependency_path(nodes,decision)
                and root in nodes[decision].get('depends',[])):
                s['s21']['permission']={'status':'VALID','basis':[decision],
                                        'revision':s['s22']['revision']}
                s['worldview']['cross_domain_gate']='S26_REISSUED_SOURCE_BASIS'

    def _physical_gate(self,op,u,expected):
        s=self.state()
        if s['actuator_calibrated']:
            if not self._s26_enabled:raise ActionDenied('S26_PLANNER_DISABLED')
            if self._s25_token:
                model=s['s24']['local_models'][-1] if s['s24']['local_models'] else None
                if model is None:raise ActionDenied('S26_MODEL_ABSENT')
                planned=action(model['outputs'],self.act.output_floor,
                    scope_ok=model['scope']['context']==self.act.snapshot()['state']['context'],
                    permitted=True,budget=1)
            else:
                evidence=self.act.snapshot()['state'].get('evidence',[])
                model=s['s22']['nodes'].get('actuator:model',{})
                scoped={}
                for e in evidence:
                    if e.get('probe') and str(e['probe']).startswith('U') and 'operation_id' in e:
                        key='actuator:receipt:'+str(e['operation_id'])
                        if key in model.get('depends',[]) and s['s22']['nodes'].get(key,{}).get('valid'):
                            scoped[e['probe'][1:]]=e['value']
                planned=action(scoped,self.act.output_floor,
                    scope_ok=model.get('context')==self.act.snapshot()['state']['context'],
                    permitted=True,budget=1)
            if planned!=(u,expected):raise ActionDenied('S26_EXECUTOR_DIFFERS_FROM_UNIFIED_PLAN')
            self._audit('S26:EXECUTE:'+op,'ACT',planned,
                        {'control':u,'expected':expected,'state_revision':s['s22']['revision']})
        return super()._physical_gate(op,u,expected)
    def snapshot(self):
        snap=super().snapshot()
        if 's26' in snap['controller']:snap['planning']=snap['controller']['s26']
        return snap
