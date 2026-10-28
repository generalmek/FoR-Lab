"""S16: method composition from evidence facts, using the S15 living agent.

Neither plans nor the agent see receiver hidden laws/variant flags. A conflicting
repeat quarantines an actuator (does not pretend to resolve the contradiction),
then tries another publicly allowed input with a fresh local check and Compass.
"""
import json
from engine.s15_method_repair import MethodRepairCycle
from engine.s14_adaptive_compass import AdaptiveCompassCycle
from engine.s16_method_language import compose

class ConstructiveMethodCycle(MethodRepairCycle):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.db.execute('CREATE TABLE IF NOT EXISTS s16_contract (id INTEGER PRIMARY KEY,body TEXT NOT NULL)')
        contract={'language':'typed-evidence-operators-v1','budget_cost':'symbolic plus receiver-paid reads'}
        old=self.db.execute('SELECT body FROM s16_contract WHERE id=1').fetchone()
        if old is not None and json.loads(old[0])!=contract:
            self.close();raise ValueError('S16 language contract mismatch')
        if old is None:
            with self.db:self.db.execute('INSERT INTO s16_contract VALUES(1,?)',(json.dumps(contract),))

    def consistent(self,m,s):
        # Treat all observations of an *explicitly quarantined* control as a local
        # unresolved exception; never infer from them that the entire model fits.
        method=s.get('s16_program')
        ignored=(method.get('quarantined_probe') if method and
                 method.get('task_id')==s.get('task_id') else None)
        if ignored:
            return all(e['probe']==ignored or
                abs(self.predict_model(m,e['probe'])-e['value'])<=e['radius']
                for e in s['evidence'] if self.fresh(s,e))
        return super().consistent(m,s)

    def commit_complete_evidence(self,s):
        # Parent first verifies a real, independently receipted measurement.
        previous=s.get('s15_method')
        old_stage=previous['stage'] if previous else None
        super().commit_complete_evidence(s)
        method=s.get('s15_method')
        if not method or method['task_id']!=s['task_id']:return
        if old_stage is None and method['stage']=='RECHECK' and not s.get('s16_program'):
            plan=compose({'contradiction'},'repeat_requested')
            if not plan or plan['operators']!=['FRESH_REPEAT']:
                raise AssertionError('method language cannot assemble a fresh repeat')
            s['s16_program']=dict(task_id=s['task_id'],origin='locally observed candidate prediction mismatch',
                evidence_ids=[method['first']['operation_id']],status='repeat_pending',
                stages=[dict(phase='evidence', **plan)],quarantined_probe=None)
            self.event(s,'S16_METHOD_COMPOSED',plan=plan,phase='repeat',source=method['first'])
            self.save(s)
        if old_stage=='RECHECK' and method['stage'] in ('CONFIRMED','UNSTABLE'):
            stable=method['stage']=='CONFIRMED'
            contradictory_probe=method['probe']
            control=int(contradictory_probe[1:])
            public_alternative=(control<self.actuator['max_control'])
            facts={'repeated','stable_residual' if stable else 'conflicting_residual'}
            if public_alternative:facts.add('public_alternative')
            plan=compose(facts,'validation_required')
            program=s['s16_program']
            if program['task_id']!=s['task_id']:
                raise ValueError('S16 stale program task')
            program['evidence_ids'].append(method['second']['operation_id'])
            program['quarantined_probe']=contradictory_probe
            program['stages'].append(dict(phase='post_repeat', **(plan or {'operators':[],'cost':0,'facts':sorted(facts),'expanded':0})))
            # An interpreter, rather than a fixed post-repeat script: state
            # transitions are dispatched from the composed operator program.
            # The inherited physical executor still owns ACT/PROBE/receipts.
            if not stable:
                # Safety invariant independent of availability of any plan.
                method['stage']='UNRESOLVED'
                method['interpretation']='conflicting repeated U3 values; no local-law claim; candidate quarantined'
                s['actions']=[u for u in s['actions'] if u!=control]
            if plan:
                for operator in plan['operators']:
                    if operator=='ISOLATE_PERSISTENT_RESIDUAL':
                        if not stable:raise AssertionError('cannot call stable on contradictory evidence')
                        self.event(s,'S16_OPERATOR_EXECUTED',operator=operator,scope=contradictory_probe)
                    elif operator=='ISOLATE_AMBIGUOUS_CONTROL':
                        if stable:raise AssertionError('cannot call ambiguous on stable evidence')
                        self.event(s,'S16_OPERATOR_EXECUTED',operator=operator,scope=contradictory_probe)
                    elif operator=='PROPOSE_INDEPENDENT_CONTROL':
                        next_u=control+1
                        if next_u>self.actuator['max_control']:
                            raise AssertionError('compiler proposed inaccessible control')
                        models=list(s['pool'])
                        predictions=[self.predict_model(m,'U'+str(next_u)) for m in models]
                        if next_u not in s['actions']:s['actions'].append(next_u)
                        s['rewards'][str(next_u)]=1
                        s.setdefault('s14_constructed_actions',[]).append({
                            'task_id':s['task_id'],'u':next_u,
                            'source':'S16 composed operators from evidence + public actuator grammar',
                            'norm_floor':self.norm['output_floor'],'prediction':predictions,
                            'verified_at_construction':False})
                        self.event(s,'S16_OPERATOR_EXECUTED',operator=operator,control=next_u)
                    elif operator=='REQUEST_LOCAL_VALIDATION':
                        if not any(c['task_id']==s['task_id'] and
                                   c['u']==control+1 for c in s['s14_constructed_actions']):
                            raise AssertionError('local validation requires a constructed candidate')
                        program['status']='independent_validation_pending'
                        self.event(s,'S16_OPERATOR_EXECUTED',operator=operator,control=control+1)
                    else:raise AssertionError('unknown compiled operator: '+operator)
                self.event(s,'S16_ALTERNATIVE_FROM_COMPOSITION',u=control+1,plan=plan,
                           quarantined=contradictory_probe,local_validation_required=True)
            else:
                program['status']='no_public_alternative'
                self.event(s,'S16_METHOD_NO_ALTERNATIVE',quarantined=contradictory_probe)
            self.event(s,'S16_METHOD_REVISED_FROM_EVIDENCE',stable=stable,
                       first=method['first'],second=method['second'],plan=plan)
            self.save(s)

    def choose_plan(self,s,models):
        method=s.get('s15_method'); p=s.get('s16_program')
        if p and method and p['task_id']==s['task_id']:
            if method['stage']=='RECHECK':
                if not any('FRESH_REPEAT' in st['operators'] for st in p['stages']):
                    raise AssertionError('cannot run repeat not composed')
                return self.probe_plan(s,method['probe'],'s16-composed-repeat')
            if method['stage']=='UNRESOLVED':
                if p['status']=='no_public_alternative':
                    self.event(s,'S16_REFUSED_NO_NEW_CONTROL',uncertainty='U3 unresolved')
                    return ('HALT',None),'S16_NO_INDEPENDENT_ALTERNATIVE'
                # S15 would halt here. Re-enter S14's already guarded policy,
                # which always demands a new local observation of U4 before ACT.
                return AdaptiveCompassCycle.choose_plan(self,s,models)
        return super().choose_plan(s,models)

    def tick(self,world):
        result=super().tick(world)
        program=result.get('s16_program')
        if program and result.get('phase') in ('DONE','HALT'):
            with self.db:
                if program['status']=='independent_validation_pending':
                    if result['phase']=='DONE':
                        selected=result.get('selected')
                        constructed=[c for c in result.get('s14_constructed_actions',[])
                                     if c['task_id']==program['task_id'] and c['u']==selected]
                        if not constructed or not constructed[-1].get('locally_checked') or not constructed[-1].get('prediction_confirmed'):
                            raise AssertionError('S16 must not mark success without independently attested candidate')
                        program['status']='validated_by_action_and_receipt'
                    else:
                        program['status']='stopped_without_validated_action'
                    self.event(result,'S16_PROGRAM_OUTCOME',status=program['status'],
                               terminal_phase=result['phase'])
                    self.save(result)
                if result['phase']=='HALT' and program['status']=='no_public_alternative' and result.get('reason')=='NO_WORTHWHILE_CERTIFIED_PLAN':
                    result['reason']='S16_NO_INDEPENDENT_ALTERNATIVE'
                    self.event(result,'S16_PROGRAM_STOP',reason=result['reason'])
                    self.save(result)
        return result
