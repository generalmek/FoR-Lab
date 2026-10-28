"""S15 host for controlled method-repair contrasts, virtual only.

The optional anomaly here belongs EXCLUSIVELY to the receiver/test host.
The candidate sees observations and public actuator capabilities, never flags.
"""
import json
from s14_integrated import S14Experiment
from engine.s15_method_repair import MethodRepairCycle

class S15Experiment(S14Experiment):
    VARIANTS=('normal','stable_u3_exception','unstable_u3','u3_u4_exception')
    def __init__(self,data_dir=None,*,world_variant='stable_u3_exception',method_enabled=True,
                 output_floor=10,compass_enabled=True,max_control=4):
        if world_variant not in self.VARIANTS:raise ValueError('unknown S15 host variant')
        self.world_variant=world_variant
        self.method_enabled=method_enabled
        super().__init__(data_dir,output_floor=output_floor,
                         compass_enabled=compass_enabled,max_control=max_control)
        self.host.execute('CREATE TABLE IF NOT EXISTS s15_host_contract(id INTEGER PRIMARY KEY,body TEXT)')
        contract=dict(variant=world_variant,method_enabled=method_enabled,max_control=max_control)
        row=self.host.execute('SELECT body FROM s15_host_contract WHERE id=1').fetchone()
        if row and json.loads(row[0])!=contract:
            self.close();raise ValueError('S15 host contract mismatch on reopen')
        if not row:
            with self.host:self.host.execute('INSERT INTO s15_host_contract VALUES(1,?)',(json.dumps(contract),))

    def open_engine(self):
        agent,world=super().open_engine()
        if self.config()['scenario']!='exploration':return agent,world
        agent.close()
        try:
            agent=MethodRepairCycle(self.root/self.session/'agent.sqlite',
                output_floor=self.output_floor,enabled=self.compass_enabled,
                max_control=self.max_control,method_enabled=self.method_enabled)
        except BaseException:
            world.close();raise
        if self.config()['context']==4 and self.world_variant!='normal':
            original_law=world.law
            world.db.execute('CREATE TABLE IF NOT EXISTS s15_host_reads(id INTEGER PRIMARY KEY,reads INTEGER NOT NULL)')
            world.db.execute('INSERT OR IGNORE INTO s15_host_reads VALUES(1,0)')
            world.db.commit()
            def substituted(u,v):
                if u==3 and v==4:
                    if self.world_variant=='unstable_u3':
                        previous=world.db.execute('SELECT reads FROM s15_host_reads WHERE id=1').fetchone()[0]
                        world.db.execute('UPDATE s15_host_reads SET reads=reads+1 WHERE id=1')
                        return 7 if previous==0 else 11
                    return 7
                if self.world_variant=='u3_u4_exception' and u==4 and v==4:
                    return 6
                return original_law(u,v)
            world.law=substituted
        return agent,world
