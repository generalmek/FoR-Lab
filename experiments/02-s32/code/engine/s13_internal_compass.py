"""S13: internal, decision-relative norm evaluation in a persistent FoR agent.

This adds a *supplied* experimental norm to the existing causal architecture;
it does not claim that the Compass originated its own values. No privileged
world-state queries; the class sees only its own hypotheses and observations.
"""
import json
import hashlib
from procedural_cycle import ProceduralCycle

class InternalCompassCycle(ProceduralCycle):
    def __init__(self, *args, output_floor=10, enabled=True, **kwargs):
        if isinstance(output_floor, bool) or not isinstance(output_floor, (int,float)):
            raise ValueError('norm requires a numeric threshold')
        if not isinstance(enabled,bool):raise ValueError('enabled must be boolean')
        super().__init__(*args, **kwargs)
        self.db.execute('CREATE TABLE IF NOT EXISTS s13_compass_contract (id INTEGER PRIMARY KEY,body TEXT)')
        proposed={'output_floor':output_floor,'enabled':enabled,'source':'experimenter-given norm; persistent inside agent'}
        row=self.db.execute('SELECT body FROM s13_compass_contract WHERE id=1').fetchone()
        if row is not None and json.loads(row[0])!=proposed:
            self.close()
            raise ValueError('compass contract mismatch on reopening; do not silently rewrite values')
        if row is None:
            with self.db:self.db.execute('INSERT INTO s13_compass_contract VALUES(1,?)',(json.dumps(proposed),))
        self.norm=proposed
        self.db.execute('''CREATE TABLE IF NOT EXISTS s13_compass_tasks (
            task_id INTEGER PRIMARY KEY, context INTEGER, observed_event_id INTEGER,
            contract TEXT)''')
        self.db.commit()

    def activate_for_observed_question(self, context, observed_event_id):
        """Bind normative scope to a witnessed novelty question in this task."""
        state=self.state()
        if state['context']!=context or type(observed_event_id) is not int or observed_event_id<1:
            raise ValueError('incorrect task/event provenance for norm activation')
        task_id=state['task_id']
        current=self.db.execute('SELECT context,observed_event_id FROM s13_compass_tasks WHERE task_id=?',
                                (task_id,)).fetchone()
        if current is not None and current!=(context,observed_event_id):
            raise ValueError('attempted normative scope rewrite')
        if current is None:
            with self.db:
                self.db.execute('INSERT INTO s13_compass_tasks VALUES(?,?,?,?)',
                    (task_id,context,observed_event_id,json.dumps(self.norm)))
                self.event(state,'COMPASS_NORM_ACTIVATED',context=context,
                           observed_event_id=observed_event_id,norm=self.norm,
                           provenance='witnessed novelty question, persisted agent task scope')
        return task_id

    def active_norm(self, state):
        row=self.db.execute('SELECT context,contract FROM s13_compass_tasks WHERE task_id=?',
                            (state['task_id'],)).fetchone()
        return self.norm if row and row[0]==state['context'] else None

    def choose_plan(self, s, models):
        if not self.active_norm(s) or not self.norm['enabled'] or not s.get('verified') or not models:
            return super().choose_plan(s, models)
        if s.get('procedure_id') is None:
            self.compile_procedure(s, models)
        floor=self.norm['output_floor']
        alternatives=[]
        for u in sorted(s['actions'],key=lambda u:(-s['rewards'][str(u)],u)):
            pred=[self.predict_model(m,'U'+str(u)) for m in models]
            e=self.latest(s,'U'+str(u))
            fresh=self.fresh(s,e)
            interval=[e['value']-e['radius'],e['value']+e['radius']] if fresh else None
            admissible_model=(min(pred)>floor and min(pred)>=0)
            admissible_evidence=(fresh and interval[0]>floor)
            upper=max(max(pred),interval[1]) if fresh else max(pred)
            resources_ok=(s['available']-upper>=s['reserve'])
            item=dict(action=u,predicted_min=min(pred),predicted_max=max(pred),
                      local_interval=interval,locally_attested=fresh,
                      model_norm_ok=admissible_model,observation_norm_ok=admissible_evidence,
                      resources_ok=resources_ok)
            alternatives.append(item)
            if not admissible_model:
                continue
            if not fresh:
                self.event(s,'COMPASS_INTERNAL_ASSESS',norm=self.norm,alternatives=alternatives,
                           decision='REQUIRE_CURRENT_OBSERVATION',selected=u,
                           model_digest=hashlib.sha256(json.dumps(models).encode()).hexdigest())
                return self.probe_plan(s,'U'+str(u),'internal-compass-requires-local-evidence')
            if not admissible_evidence or not resources_ok:
                continue
            if s['budget']<1:
                return ('HALT',None),'budget'
            s.update(selected=u,target=pred[0])
            # Exactly the same provenance binding as the original ProceduralCycle.
            s['authorization_basis']={k:v[1] for k,v in self.beliefs().items()}
            self.save(s)
            self.event(s,'COMPASS_INTERNAL_ASSESS',norm=self.norm,alternatives=alternatives,
                       decision='ALLOW',selected=u,source='hypotheses + current local evidence',
                       model_digest=hashlib.sha256(json.dumps(models).encode()).hexdigest())
            return ('ACT',u),'internally-admissible'
        s['internal_compass_denied']=dict(floor=floor,alternatives=alternatives,
                                          reason='no-option-strictly-above-given-norm')
        self.event(s,'COMPASS_INTERNAL_ASSESS',norm=self.norm,alternatives=alternatives,
                   decision='DENY',source='hypotheses + current local evidence',
                   model_digest=hashlib.sha256(json.dumps(models).encode()).hexdigest())
        self.save(s)
        return ('HALT',None),'INTERNAL_COMPASS_DENIED'

    def permit(self,u):
        permission=super().permit(u)
        if permission is None or not self.norm['enabled'] or not self.active_norm(self.state()):return permission
        s=self.state(); models=self.candidates(s);e=self.latest(s,'U'+str(u))
        floor=self.norm['output_floor']
        if (not models or not self.fresh(s,e) or e['value']-e['radius']<=floor or
                not all(self.predict_model(m,'U'+str(u))>floor for m in models) or
                permission['target']<=floor):
            return None
        permission.update(internal_compass_norm=self.norm,
                          internal_compass_basis='current hypotheses, fresh local observation, version-bound permit')
        return permission

    def tick(self, world):
        result=super().tick(world)
        if (result.get('phase')=='HALT' and result.get('internal_compass_denied') and
                result.get('reason')=='NO_WORTHWHILE_CERTIFIED_PLAN'):
            # The inherited generic executor chooses its own HALT reason; keep
            # the actual specific internal decision in the durable agent state.
            with self.db:
                result['reason']='INTERNAL_COMPASS_DENIED'
                self.event(result,'COMPASS_INTERNAL_REFUSAL',scope=self.active_norm(result),
                           basis=result['internal_compass_denied'])
                self.save(result)
        return result
