"""S20 short falsifiable integration campaign. Raw results preserve negative controls."""
import json,sqlite3,tempfile
from pathlib import Path
from s20_unified import S20Unified

SHARED={'B':'shared','C':'shared','D':'distinct'}
CASES=[
 ('honest_joint',dict(sensor_variant='bias_A',d_values=(12,12),provenance_roots=SHARED)),
 ('correlated_wrong_interlock',dict(sensor_variant='colluding_sources',d_values=(8,8),provenance_roots=SHARED)),
 ('ablation_correlated_wrong',dict(sensor_variant='colluding_sources',d_values=(8,8),provenance_roots=SHARED,provenance_enabled=False)),
 ('restart_joint',dict(sensor_variant='bias_A',d_values=(12,12),provenance_roots=SHARED)),
 ('global_budget_stop',dict(sensor_variant='bias_A',d_values=(12,12),provenance_roots=SHARED,budget=18)),
 ('no_interleave_joint',dict(sensor_variant='bias_A',d_values=(12,12),provenance_roots=SHARED,phase_interleave=False)),
]
def source():return json.loads(Path(__file__).with_name('S17_SOURCE_MOTIFS.json').read_text(encoding='utf8'))

def run_case(name,options):
    with tempfile.TemporaryDirectory(prefix='FoR_S20_'+name+'_') as folder:
        kwargs=dict(options)
        app=S20Unified(folder,source(),**kwargs)
        try:
            if name=='restart_joint':
                for _ in range(140):
                    app.close();app=S20Unified(folder,source(),**kwargs)
                    res=app.step()
                    if res['controller']['phase']!='ACTIVE':break
                else:raise AssertionError('restart exceeded step cap')
            else:res=app.run()
            before=len(res['actuator']['s16_program'] or {})
            old=app.snapshot();again=app.step()
            assert old['controller']==again['controller'],'terminal step modified persistent state'
            checks={}
            for p in Path(folder).rglob('*.sqlite'):
                with sqlite3.connect(p) as con:checks[str(p.relative_to(folder))]=con.execute('PRAGMA integrity_check').fetchone()[0]
            assert checks and all(v=='ok' for v in checks.values())
            # Check host-private scenario labels did not leak into public controller storage.
            public_text=(Path(folder)/'s20_agent.sqlite').read_bytes()
            for leaked in ('sensor_variant','world_variant','colluding_sources','stable_u3_exception'):
                assert leaked.encode() not in public_text,leaked
            rec=list(app.sensor.world.receipts())
            return {'name':name,'host_configuration':kwargs,'controller':res['controller'],
                    'actuator':res['actuator'],'sensor':res['sensor'],
                    'sensor_physical_receipts':rec,
                    'new_actuator_receipts':res['actuator']['receipts']-(res['controller']['actuator_receipts_before_novelty'] or 0),
                    'integrity':checks}
        finally:app.close()

def campaign():return [run_case(n,options) for n,options in CASES]
if __name__=='__main__':print(json.dumps(campaign(),indent=2,ensure_ascii=False))
