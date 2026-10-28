"""S14: generate and check an additional action after an internal Compass refusal.

The public actuator limit is an interface contract, not a hidden world law.
All candidate controls are subject to a paid local observation before execution.
The current representation supports integer controls only, not new semantics.
"""
import json
from engine.s13_internal_compass import InternalCompassCycle


class AdaptiveCompassCycle(InternalCompassCycle):
    def __init__(self,*args,max_control=3,**kwargs):
        if type(max_control) is not int or not 2 <= max_control <= 8:
            raise ValueError('public actuator contract must be integer in [2,8]')
        super().__init__(*args,**kwargs)
        desired=dict(max_control=max_control,source='published actuator integer range, NOT hidden world law')
        self.db.execute('CREATE TABLE IF NOT EXISTS s14_actuator_contract (id INTEGER PRIMARY KEY,body TEXT NOT NULL)')
        r=self.db.execute('SELECT body FROM s14_actuator_contract WHERE id=1').fetchone()
        if r and json.loads(r[0])!=desired:
            self.close()
            raise ValueError('S14 actuator contract mismatch on reopening')
        if not r:
            with self.db:self.db.execute('INSERT INTO s14_actuator_contract VALUES(1,?)',(json.dumps(desired),))
        self.actuator=desired

    def commit_complete_evidence(self,s):
        super().commit_complete_evidence(s)
        evidence=s['evidence'][-1]
        for candidate in s.get('s14_constructed_actions',[]):
            if candidate['task_id'] != s['task_id'] or evidence['probe'] != 'U'+str(candidate['u']) or candidate.get('locally_checked'):
                continue
            confirmed=all(abs(evidence['value']-y)<=evidence['radius'] for y in candidate['prediction'])
            candidate.update(locally_checked=True, prediction_confirmed=confirmed,
                             local_observation=dict(value=evidence['value'], radius=evidence['radius'],
                                 operation_id=evidence.get('operation_id'), tick=evidence.get('tick')))
            self.event(s,'ACTION_CANDIDATE_LOCAL_CHECK',u=candidate['u'],
                       prediction_confirmed=confirmed,local_observation=candidate['local_observation'],
                       provenance='paid independent receiver measurement')

    def choose_plan(self,s,models):
        original,reason=super().choose_plan(s,models)
        # Only a *verified* denied action task can initiate this alternative search.
        if (original[0]!='HALT' or reason!='INTERNAL_COMPASS_DENIED'
                or not models or not s.get('verified') or not self.norm['enabled']
                or not self.active_norm(s)):
            return original,reason
        available=set(s['actions'])
        next_u=max(available)+1
        if next_u>self.actuator['max_control']:
            return original,reason
        # Do not read receiver's process law. Model extrapolation gives a reason
        # to try a new actuator input, but never grants physical permission.
        predicted=[self.predict_model(m,'U'+str(next_u)) for m in models]
        floor=self.norm['output_floor']
        with self.db:
            self.event(s,'ACTION_SPACE_QUESTION',
                question='Can a currently unused actuator setting satisfy the existing task under its norm?',
                trigger='internal Compass rejected all previously tried actions',
                bounds=self.actuator, source_models=models,proposed_control=next_u,
                predicted_range=[min(predicted),max(predicted)],norm_floor=floor,
                needs='fresh paid local observation before permitted execution')
            # Candidate in a given actuator grammar: not an invented semantic operator.
            s['actions']=list(s['actions'])+[next_u]
            s['rewards'][str(next_u)]=1  # explicitly minimal exploratory priority, not discovered utility
            s.setdefault('s14_constructed_actions',[]).append({
                'task_id':s['task_id'],'u':next_u,'source':'successor in declared integer actuator range',
                'norm_floor':floor,'prediction':predicted,'verified_at_construction':False})
            s.pop('internal_compass_denied',None)
            self.event(s,'ACTION_CANDIDATE_CONSTRUCTED',u=next_u,contract=self.actuator,
                reason='prior actions norm-inadmissible',predictions=predicted)
            self.save(s)
        # Immediate replan using the existing agent policy; no new host goal,
        # extra operation, external oracle or unguarded execution.
        return super().choose_plan(s,models)
