"""S12 host-level integration: run an epistemic preflight *inside* S10 step.

No change to procedural executor. Ablation is counterfactual only; it makes
no physical action and never marks a context completed.
"""
import json
from sample2_runtime import ObservableExperiment
from event_agenda import propose_from_observed_contexts
from engine.s12_sufficiency import assess
from funded_runtime import ResourceDenied


class S12Experiment(ObservableExperiment):
    def __init__(self, data_dir=None, *, output_floor=10, ignore_scope=False):
        self.output_floor=output_floor
        self.ignore_scope=ignore_scope
        super().__init__(data_dir)
        self.host.execute('''CREATE TABLE IF NOT EXISTS s12_decisions (
            id INTEGER PRIMARY KEY, session TEXT NOT NULL,
            observed_event_id INTEGER NOT NULL, body TEXT NOT NULL,
            UNIQUE(session, observed_event_id))''')
        self.host.execute('''CREATE TABLE IF NOT EXISTS s12_denials (
            id INTEGER PRIMARY KEY, session TEXT NOT NULL, context INTEGER NOT NULL,
            body TEXT NOT NULL)''')
        self.host.commit()

    def denial_log(self):
        return [json.loads(b) for (b,) in self.host.execute('SELECT body FROM s12_denials WHERE session=? ORDER BY id',(self.session,))]

    def open_engine(self):
        r,w=super().open_engine()
        orig=w.apply_once
        def receiver_gate(operation_id,u,target):
            c=self.config()
            # Only novelty research opened by the observed-event S10 pipeline.
            origin=(c.get('research') or [{}])[-1].get('question_origin')
            fresh=(c['scenario']=='exploration' and
                   origin=='observed_novelty_not_allowed_contexts' and
                   c['context'] not in c.get('completed_contexts',[]))
            if fresh and target <= self.output_floor:
                denial=dict(operation_id=operation_id,action=u,predicted_target=target,
                            threshold=self.output_floor,context=c['context'],
                            reason='S12_EXTERNAL_OUTPUT_FLOOR_INTERLOCK',
                            source='declared_norm_and_agent_target_no_hidden_law')
                with self.host:
                    self.host.execute('INSERT INTO s12_denials(session,context,body) VALUES(?,?,?)',
                                      (self.session,c['context'],json.dumps(denial,sort_keys=True)))
                raise ResourceDenied('S12_EXTERNAL_OUTPUT_FLOOR_INTERLOCK')
            return orig(operation_id,u,target)
        w.apply_once=receiver_gate
        return r,w

    def gate_log(self):
        return [json.loads(b) for (b,) in self.host.execute('SELECT body FROM s12_decisions WHERE session=? ORDER BY id',(self.session,))]

    def step(self, automatic=False):
        if automatic and self.paused:
            return self.snapshot()
        before=self.snapshot()
        c=before['config']; life=before['life'] or {}
        if (c['scenario']=='exploration' and not c['inflight'] and
                life.get('status')=='DONE' and before['state'].get('context')==c['context']):
            completed=sorted(set(c['completed_contexts']+[before['state']['context']]))
            # Built-in S10 finite menu takes priority, as in original runtime.
            from research_agenda import propose
            question=propose(before['state'],completed)
            if question is None:
                question=propose_from_observed_contexts(before['state'],completed,self.public_context_observations())
            if question and question.get('question_origin')=='observed_novelty_not_allowed_contexts':
                event_id=question['selected']['event_id']
                recorded=self.host.execute('SELECT body FROM s12_decisions WHERE session=? AND observed_event_id=?',
                                           (self.session,event_id)).fetchone()
                if recorded is None:
                    verdict=assess(before,question,output_floor=self.output_floor,ignore_scope=self.ignore_scope)
                    with self.host:
                        self.host.execute('INSERT INTO s12_decisions(session,observed_event_id,body) VALUES(?,?,?)',
                                          (self.session,event_id,json.dumps(verdict,sort_keys=True)))
                else:
                    verdict=json.loads(recorded[0])
                # Counterfactual ablation stops; does not send a physical action.
                if verdict['decision']=='SKIP_SCOPE_CHECK_ABLATION':
                    # Never pretend that a new observed context was covered.
                    c['research_status']='COUNTERFACTUAL_SKIP_UNVERIFIED'
                    c['deferred_context']=verdict['context']
                    self.save_config(c)
                    return self.snapshot()
        after=super().step(automatic=automatic)
        if ((after['life'] or {}).get('status')=='STOPPED' and self.denial_log()
                and after['config'].get('research_status')=='ACTIVE'):
            c=after['config']
            c['research_status']='EXTERNAL_ACTION_DENIED'
            self.save_config(c)
            return self.snapshot()
        return after
