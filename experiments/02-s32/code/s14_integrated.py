"""S14: S13 integrated host with a bounded public third actuator setting.

No receiver target floor is used; the S13 agent Compass decides admission.
Host's explicit actuator contract is surfaced to the agent and enforced at
receiver. Hidden world law is never passed to the agent.
"""
from sample2_runtime import ObservableExperiment
from s13_integrated import S13Experiment
from engine.s14_adaptive_compass import AdaptiveCompassCycle

class S14Experiment(S13Experiment):
    def __init__(self,data_dir=None,*,output_floor=10,compass_enabled=True,max_control=3):
        self.max_control=max_control
        super().__init__(data_dir,output_floor=output_floor,compass_enabled=compass_enabled)

    def open_engine(self):
        runner,world=ObservableExperiment.open_engine(self)
        if self.config()['scenario']!='exploration':return runner,world
        runner.close()
        # Restrict the *receiver* to the published actuator contract as well.
        # Do not restrict calibration or non-U probes (T, V, C).
        original_observation=world.observation
        original_apply=world.apply_once
        limit=self.max_control
        def validated_observation(probe):
            if probe.startswith('U'):
                index=int(probe[1:])
                if not 1<=index<=limit:raise ValueError('actuator probe outside published contract')
            return original_observation(probe)
        def validated_apply(operation_id,u,target):
            if type(u) is not int or not 1<=u<=limit:
                raise ValueError('actuator execution outside published contract')
            return original_apply(operation_id,u,target)
        world.observation=validated_observation
        world.apply_once=validated_apply
        try:
            agent=AdaptiveCompassCycle(self.root/self.session/'agent.sqlite',
                output_floor=self.output_floor,enabled=self.compass_enabled,max_control=limit)
        except BaseException:
            world.close()
            raise
        return agent,world


class OutsideClassS14Experiment(S14Experiment):
    """Negative test world: only U3@context4 violates otherwise affine process."""
    def open_engine(self):
        agent,world=super().open_engine()
        old=world.law
        if self.config()['context']==4:
            world.law=lambda u,v: 7 if u==3 and v==4 else old(u,v)
        return agent,world
