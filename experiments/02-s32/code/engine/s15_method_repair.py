"""S15: construct a bounded counterexample-directed research method in the living cycle.

On an independently observed contradiction for a newly constructed actuator
candidate, quarantine only that candidate, re-measure it with a NEW paid receipt,
then use the preserved baseline only as a proposal generator. Any later control
still needs its own observation and internal Compass authorisation.
No world law, hidden intervention label, or receiver-side norm is read here.
"""
import json
from engine.s14_adaptive_compass import AdaptiveCompassCycle


class MethodRepairCycle(AdaptiveCompassCycle):
    def __init__(self, *args, method_enabled=True, **kwargs):
        if type(method_enabled) is not bool:
            raise ValueError('method_enabled must be boolean')
        super().__init__(*args, **kwargs)
        self.db.execute('CREATE TABLE IF NOT EXISTS s15_contract (id INTEGER PRIMARY KEY,body TEXT NOT NULL)')
        contract=dict(method_enabled=method_enabled,version=1)
        old=self.db.execute('SELECT body FROM s15_contract WHERE id=1').fetchone()
        if old and json.loads(old[0])!=contract:
            self.close()
            raise ValueError('S15 method contract mismatch on reopen')
        if not old:
            with self.db:self.db.execute('INSERT INTO s15_contract VALUES(1,?)',(json.dumps(contract),))
        self.method_enabled=method_enabled

    def consistent(self,m,s):
        # A quarantined local counterexample is NOT silently explained away.
        # It is held separately as explicit unresolved/confirmed residual evidence.
        method=s.get('s15_method')
        ignored=(method['probe'] if method and method['task_id']==s['task_id']
                 and method['stage'] in ('RECHECK','CONFIRMED','UNSTABLE') else None)
        return all((e['probe']==ignored or
                    abs(self.predict_model(m,e['probe'])-e['value'])<=e['radius'])
                   for e in s['evidence'] if self.fresh(s,e))

    def commit_complete_evidence(self,s):
        prior_models=list(s.get('pool',[]));prior_verified=bool(s.get('verified'))
        method=s.get('s15_method')
        probe=s['evidence'][-1]['probe']
        # Only one repair attempt per task; first diagnose an actual residual.
        eligible=(self.method_enabled and not method and prior_verified and prior_models and
            any(x['task_id']==s['task_id'] and probe=='U'+str(x['u']) and
                not x.get('locally_checked') for x in s.get('s14_constructed_actions',[])))
        super().commit_complete_evidence(s)
        e=s['evidence'][-1]
        if method and method['task_id']==s['task_id'] and method['stage']=='RECHECK' and probe==method['probe']:
            # A fresh distinct receiver receipt, not reusing the initial measurement.
            comparable=(abs(e['value']-method['first']['value'])<=
                        e['radius']+method['first']['radius'] and
                        e.get('operation_id')!=method['first']['operation_id'])
            method.update(stage='CONFIRMED' if comparable else 'UNSTABLE',
                second=dict(value=e['value'],radius=e['radius'],operation_id=e.get('operation_id')),
                interpretation='stable local counterexample; baseline not globally certified' if comparable
                    else 'inconsistent repeated evidence; no local law assumption permitted')
            s['pool']=prior_models;s['verified']=True
            if comparable:
                # No proposal may ACT on the quarantined control; it may only
                # propose a different control and is then checked against reality.
                self.db.execute('UPDATE forecasts SET valid=0')
                self.db.execute("UPDATE beliefs SET version=version+1 WHERE name='process'")
            self.event(s,'S15_DIFFERENTIAL_METHOD_RESULT',method=method)
        elif eligible and not s['s14_constructed_actions'][-1].get('prediction_confirmed',True):
            initial=s['s14_constructed_actions'][-1]
            first=dict(value=e['value'],radius=e['radius'],operation_id=e.get('operation_id'))
            s['s15_method']=dict(task_id=s['task_id'],stage='RECHECK',
                question='Is the new actuator discrepancy reproducible or transient?',
                origin='observed mismatch for a locally measured new candidate',
                probe=probe,first=first,second=None,source_models=prior_models,
                plan=['fresh repeat of exactly the contradicted control',
                      'if stable, quarantine control-specific exception',
                      'propose another permitted control, measure locally before action'],
                limits=['finite integer actuator contract','one candidate exception per task',
                        'no assertion of global law; no physical action from untested prediction'])
            s['pool']=prior_models;s['verified']=True
            self.event(s,'S15_DIFFERENTIAL_METHOD_CONSTRUCTED',method=s['s15_method'])
        # The parent's generic model search is overridden only for the concrete
        # witnessed residual. The new method is stored with provenance in state.
        self.save(s)

    def choose_plan(self,s,models):
        method=s.get('s15_method')
        if method and method['task_id']==s['task_id']:
            if method['stage']=='RECHECK':
                return self.probe_plan(s,method['probe'],'s15-differential-repeat')
            if method['stage']=='UNSTABLE':
                self.event(s,'S15_METHOD_REFUSED',reason='REPEAT_DISAGREES_WITH_FIRST')
                return ('HALT',None),'S15_UNSTABLE_EVIDENCE'
        return super().choose_plan(s,models)

    def tick(self,world):
        result=super().tick(world)
        method=result.get('s15_method')
        if (method and method['stage']=='UNSTABLE' and result.get('phase')=='HALT'
                and result.get('reason')=='NO_WORTHWHILE_CERTIFIED_PLAN'):
            with self.db:
                result['reason']='S15_UNSTABLE_EVIDENCE'
                self.event(result,'S15_METHOD_STOP',reason=result['reason'],method=method)
                self.save(result)
        return result
