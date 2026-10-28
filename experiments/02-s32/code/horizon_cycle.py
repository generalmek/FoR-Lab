"""Supplied future obligation influences current action through acquired models.
Finite horizon under stationary costs; not self-created values or full Compass.
"""
from composition_cycle import CompositionCycle

class HorizonCycle(CompositionCycle):
    def start_cycle(self,world,*args,**kwargs):
        super().start_cycle(world,*args,**kwargs)
        s=self.state();s.update(base_reserve=world.reserve,future_obligation=True,
            future_action=1,future_measurement_allowance=8)
        with self.db:self.save(s)

    def choose_plan(self,s,models):
        if not s.get('verified') or not models:return super().choose_plan(s,models)
        base=s.get('base_reserve',self.active_world.reserve)
        if s.get('future_stage'):
            s['reserve']=base
            original=s['actions'];s['actions']=[1]
            result=super().choose_plan(s,models);s['actions']=original;self.save(s)
            return result
        future=max(self.predict_model(m,'U1') for m in models)+s['future_measurement_allowance']
        s['reserve']=base+future
        considered=[];eligible=[]
        for u in s['actions']:
            bound=max(self.predict_model(m,'U'+str(u)) for m in models)
            fresh=self.fresh(s,self.latest(s,'U'+str(u)))
            # If a probe is required, charge it plus the next tick's 3 references.
            prep=0 if fresh else self.active_world.price('U'+str(u))+3*self.active_world.sample_price
            enough=s['available']-prep-bound>=s['reserve']
            considered.append(dict(action=u,predicted_cost=bound,preparation=prep,
                future_requirement=future,reserve=base,admissible=enough))
            if enough:eligible.append(u)
        s['horizon_assessment']=dict(available=s['available'],alternatives=considered,
            assumptions=['stationary process','same context','8 units for future checks','future action 1 supplied'])
        self.event(s,'HORIZON_ASSESSMENT',assessment=s['horizon_assessment'])
        original=s['actions'];s['actions']=eligible
        result=super().choose_plan(s,models)
        s['actions']=original;self.save(s)
        return result

    def start_future(self,world,budget):
        # Start explicitly supplied second task without executing the first tick yet.
        with self.db:self.db.execute('DELETE FROM life WHERE id=1')
        self.start_cycle(world,budget=budget)
        s=self.state();s.update(future_stage=True,reserve=world.reserve)
        with self.db:
            self.save(s)
            self.save_life(dict(status='RUNNING',expected_task=s['task_id'],remaining=budget,
                repair_limit=2,repairs=0,questions=[],context=world.context))
        return dict(s,life=self.life())
