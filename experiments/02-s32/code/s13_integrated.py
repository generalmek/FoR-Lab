"""S13: S12 inquiry preflight + *internal* action choice, no S12 receiver floor gate.

The existing independent physical resource-reserve interlock remains.
"""
from s12_integrated import S12Experiment
from sample2_runtime import ObservableExperiment
from engine.s13_internal_compass import InternalCompassCycle

class S13Experiment(S12Experiment):
    def __init__(self,data_dir=None,*,output_floor=10,compass_enabled=True):
        self.compass_enabled=compass_enabled
        super().__init__(data_dir,output_floor=output_floor,ignore_scope=False)
        # Validate persistent agent contract at reconnect, not only on next tick.
        try: self.snapshot()
        except BaseException:
            self.close()
            raise

    def open_engine(self):
        # Bypass S12's outer receiver target gate, preserving the full native
        # execution pathway with original independent resource-reserve check.
        runner,world=ObservableExperiment.open_engine(self)
        if self.config()['scenario']!='exploration':return runner,world
        runner.close()
        try:
            new_runner=InternalCompassCycle(self.root/self.session/'agent.sqlite',
                      output_floor=self.output_floor,enabled=self.compass_enabled)
        except BaseException:
            world.close()
            raise
        return new_runner,world

    def step(self,automatic=False):
        result=super().step(automatic=automatic)
        # A witnessed S10 question can activate the externally declared norm for
        # its own task. Persist inside agent DB; subsequent action decisions are
        # made by InternalCompassCycle, with no receiver output-floor check.
        c=result['config']
        if c.get('scenario')=='exploration' and c.get('research'):
            last=c['research'][-1]
            selected=last['selected']
            if (last.get('question_origin')=='observed_novelty_not_allowed_contexts' and
                    result['state']['context']==selected['context'] and
                    result['life']['status']=='RUNNING' and
                    any(x['id']==selected.get('event_id') and x['context']==selected['context']
                        for x in self.public_context_observations())):
                runner, world=self.open_engine()
                try:
                    runner.activate_for_observed_question(selected['context'], selected['event_id'])
                finally:
                    runner.close();world.close()
                result=self.snapshot()
        if (result['config'].get('scenario')=='exploration' and
                (result['life'] or {}).get('status')=='STOPPED' and
                result['state'].get('reason')=='INTERNAL_COMPASS_DENIED'):
            cfg=result['config']
            if cfg.get('research_status')!='INTERNAL_ACTION_DENIED':
                cfg['research_status']='INTERNAL_ACTION_DENIED'
                self.save_config(cfg)
                return self.snapshot()
        return result
