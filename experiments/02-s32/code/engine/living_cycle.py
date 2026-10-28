"""Persistent self-initiated repair of one supplied goal, within bounded semantics."""
import json
from outcome_revision import OutcomeRevisionCycle


class LivingCycle(OutcomeRevisionCycle):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.db.execute('CREATE TABLE IF NOT EXISTS life(id INTEGER PRIMARY KEY,body TEXT)')
        self.db.commit()

    def life(self):
        row=self.db.execute('SELECT body FROM life WHERE id=1').fetchone()
        return json.loads(row[0]) if row else None

    def save_life(self,body):
        self.db.execute('INSERT OR REPLACE INTO life VALUES(1,?)',(json.dumps(body),))

    def prepare_step(self,world,life):
        """Extension point for evidence checks using the same state and budget."""
        return True

    def begin(self,world,budget=24,repair_limit=2):
        if self.life() is not None:raise ValueError('existing life must be resumed, not reset')
        if type(budget) is not int or budget<1 or type(repair_limit) is not int or repair_limit<0:
            raise ValueError('invalid lifetime budget')
        with self.db:
            self.save_life(dict(status='STARTING',expected_task=self.state()['task_id']+1,
                remaining=budget,repair_limit=repair_limit,repairs=0,questions=[],context=world.context))
        return self.tick(world)

    def tick(self,world):
        life=self.life()
        if life is None:raise ValueError('begin required')
        if world.context!=life['context']:raise ValueError('context transition requires explicit observation')
        if life['status'] in ('DONE','STOPPED'):return dict(self.state(),life=life)
        if life['status']=='STARTING':
            s=self.state()
            if s['task_id']==life['expected_task']-1:
                self.start_cycle(world,budget=life['remaining'])
            elif s['task_id']!=life['expected_task']:
                raise RuntimeError('cannot reconcile task identity')
            # The marker prevents duplicating completed starts. A crash inside start_cycle
            # is not yet covered; do not advertise general transactional startup recovery.
            life['status']='RUNNING'
            with self.db:self.save_life(life)
        if not self.prepare_step(world,life):
            life.update(status='STOPPED',remaining=self.state()['budget'])
            with self.db:self.save_life(life)
            return dict(self.state(),life=life)
        s=super().step(world)
        life['remaining']=s['budget']
        if s['phase']=='DONE':life['status']='DONE'
        elif s['phase']=='HALT':
            reason=s.get('reason')
            if reason=='EXECUTION_MISMATCH' and life['remaining']>=2 and life['repairs']<life['repair_limit']:
                life['questions'].append(dict(source_task=s['task_id'],trigger=reason,
                    question='Which assumptions no longer support the action forecast?',
                    alternatives=['process changed','measurement unreliable','model class insufficient'],
                    implemented_check='fresh model inquiry; sensor attribution remains unresolved'))
                life.update(status='STARTING',expected_task=s['task_id']+1,repairs=life['repairs']+1)
                self.event(s,'SELF_INITIATED_REPAIR',question=life['questions'][-1])
            else:life['status']='STOPPED'
        with self.db:self.save_life(life)
        return dict(s,life=life)
