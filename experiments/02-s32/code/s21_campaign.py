"""Predeclared causal contrasts for S21 (no independent performance claim)."""
import json, sqlite3, tempfile
from pathlib import Path
from s21_unified import S21Unified
from s20_campaign import SHARED,source

CASES=[
    ('baseline',dict(),False),
    ('late_agreement',dict(late_values=(12,12)),True),
    ('late_disagreement',dict(late_values=(8,8)),True),
    ('late_unstable',dict(late_values=(8,12)),True),
    ('late_shared_lineage',dict(late_values=(12,12),late_root='shared'),True),
    ('late_ablation',dict(late_values=(8,8),late_enabled=False),True),
    ('late_restart',dict(late_values=(12,12)),True),
    ('late_budget_stop',dict(late_values=(12,12),budget=70),True),
]

def run_case(name,overrides=None,announce=True):
    overrides=dict(overrides or {})
    options=dict(sensor_variant='bias_A',d_values=(12,12),provenance_roots=SHARED,**overrides)
    with tempfile.TemporaryDirectory(prefix='FoR_S21_'+name+'_') as directory:
        app=S21Unified(directory,source(),**options)
        try:
            announce_done=False
            for _ in range(140):
                if name=='late_restart':
                    app.close();app=S21Unified(directory,source(),**options)
                st=app.state()
                if announce and not announce_done and st['actuator_calibrated'] and st['tick']>=22 and st['phase']=='ACTIVE':
                    app.announce_E('PUBLIC-E-001');announce_done=True
                snap=app.step()
                if snap['controller']['phase']!='ACTIVE':break
            else:raise AssertionError('S21 step cap exceeded')
            assert not announce or announce_done, (name,'E event never announced')
            final=app.snapshot();ctrl=final['controller'];graph=ctrl['s21']
            prior=ctrl['actuator_receipts_before_novelty'] or 0
            new_act=final['actuator']['receipts']-prior
            checks={}
            for p in Path(directory).rglob('*.sqlite'):
                with sqlite3.connect(p) as db:checks[str(p.relative_to(directory))]=db.execute('PRAGMA integrity_check').fetchone()[0]
            assert all(x=='ok' for x in checks.values()),checks
            out={'name':name,'host_configuration':options,'phase':ctrl['phase'],'tick':ctrl['tick'],
                 'global_budget':ctrl['shared_budget'],'late':graph['late'],'permission':graph['permission'],
                 'worldview_revision':graph['revision'],'nodes':graph['nodes'],
                 'events':ctrl['events'],'question_agenda':ctrl['question_agenda'],
                 'new_actuator_receipts':new_act,'actuator_status':final['actuator']['life'],
                 'sensor_status':final['sensor']['status'],'integrity':checks}
            # Reopening a terminal never creates an ACT.
            before=ctrl['events'];app.step()
            assert app.state()['events']==before
            return out
        finally:app.close()

def campaign():return [run_case(*c) for c in CASES]
if __name__=='__main__':print(json.dumps(campaign(),ensure_ascii=False,indent=2))
