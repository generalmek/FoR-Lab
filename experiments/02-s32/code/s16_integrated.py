"""S16 host. Candidate never receives private world variants or law parameters."""
import json
from s15_integrated import S15Experiment
from engine.s16_constructive_method import ConstructiveMethodCycle

class S16Experiment(S15Experiment):
    def __init__(self,data_dir=None,*,composer_enabled=True,**kwargs):
        if type(composer_enabled) is not bool:raise ValueError('composer_enabled must be bool')
        self.composer_enabled=composer_enabled
        super().__init__(data_dir,**kwargs)
        self.host.execute('CREATE TABLE IF NOT EXISTS s16_host_contract(id INTEGER PRIMARY KEY,body TEXT)')
        proposed={'composer_enabled':composer_enabled}
        row=self.host.execute('SELECT body FROM s16_host_contract WHERE id=1').fetchone()
        if row and json.loads(row[0])!=proposed:
            self.close();raise ValueError('S16 host contract mismatch')
        if not row:
            with self.host:self.host.execute('INSERT INTO s16_host_contract VALUES(1,?)',(json.dumps(proposed),))

    def open_engine(self):
        agent,world=super().open_engine()
        if not self.composer_enabled or self.config()['scenario']!='exploration':return agent,world
        agent.close()
        try:
            new=ConstructiveMethodCycle(self.root/self.session/'agent.sqlite',
                output_floor=self.output_floor,enabled=self.compass_enabled,
                max_control=self.max_control,method_enabled=self.method_enabled)
        except BaseException:
            world.close();raise
        return new,world
