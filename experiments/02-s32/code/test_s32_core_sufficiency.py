import unittest,tempfile
from pathlib import Path
from s31_comparison import S31World,PublicWorldView
from s21_campaign import source,SHARED
from s32_core_sufficiency import S32Agent
from s32_comparison import run_pair32,cases
from s22_semantic_kernel import valid_dependency_path

class LocalEvidence(unittest.TestCase):
    def make(self,law='xor',budget=12,local=True):
        tmp=tempfile.TemporaryDirectory()
        p=Path(tmp.name)
        world=S31World(p/'world.db',('x','y','z'),{'a':'x','b':'y','c':'z'},law)
        view=PublicWorldView(world)
        agent=S32Agent(p/'agent',source(),provenance_roots=SHARED,budget=budget,local_sufficiency=local)
        agent.add_task('one',view)
        return tmp,world,view,agent
    def test_direct_point_only_not_unmeasured(self):
        tmp,w,v,a=self.make()
        try:
            for _ in range(3):e=a.tick_concepts({'one':v})
            self.assertEqual(e['kind'],'LOCAL_SUFFICIENT_EVIDENCE')
            s=a.state();m=s['s29']['tasks']['one']['model'];node=s['s22']['nodes'][m]
            self.assertEqual(node['evidence_scope'],'LOCAL_POSITIVE_POINT')
            self.assertEqual(len(node['depends']),1)
            self.assertTrue(valid_dependency_path(s['s22']['nodes'],m))
            self.assertEqual(len(s['s29']['tasks']['one']['observations']),3)
            e=a.tick_concepts({'one':v});self.assertEqual(e['kind'],'ACTION_PERFORMED')
            self.assertEqual(w.audit()['counts'].get('ACT'),1)
        finally:a.close();w.close();tmp.cleanup()
    def test_ablation_restores_full_model_requirement(self):
        r=run_pair32('xor',4,0,ticks=20,local_sufficiency=False)
        self.assertEqual(r['results']['T32']['acts'],0)
        self.assertGreaterEqual(r['results']['B2']['acts'],1)
    def test_small_budget_improvement(self):
        r=run_pair32('xor',4,0,ticks=20)
        self.assertEqual(r['results']['T32']['acts'],1)
        self.assertEqual(r['results']['T32']['failed_actions'],0)
    def test_never_no_evidence_action(self):
        r=run_pair32('exactly_one',2,0,ticks=15)
        self.assertEqual(r['results']['T32']['acts'],0)
        self.assertGreaterEqual(r['results']['T32']['remaining'],0)
    def test_restart_unchanged_action_receipts(self):
        r=run_pair32('nand',12,0,ticks=40,restart=True)
        self.assertEqual(r['results']['T32']['failed_actions'],0)
        self.assertEqual(r['results']['T32']['integrity'],'ok')
    def test_goal_raise_blocks_new_action(self):
        r=run_pair32('xor',50,0,ticks=30,goal=True)
        self.assertEqual(r['results']['T32']['failed_actions'],0)
        self.assertEqual(r['results']['T32']['agent_integrity'],'ok')
    def test_local_recheck_does_not_infer_global_negative(self):
        tmp,w,v,a=self.make(budget=13)
        try:
            for _ in range(5):events=[a.tick_concepts({'one':v})]
            self.assertIn(events[-1]['kind'],('LOCAL_MONITOR_CONFIRMED','LOCAL_MONITOR_NEW_BASELINE'))
            s=a.state();self.assertEqual(s['s29']['tasks']['one']['phase'],'MONITOR')
            self.assertEqual(s['s29']['tasks']['one']['model'].split(':')[-1],'0')
        finally:a.close();w.close();tmp.cleanup()
    def test_contradiction_reopens_local_point(self):
        tmp,w,v,a=self.make(budget=30)
        try:
            for _ in range(4):a.tick_concepts({'one':v})
            old=a.state()['s29']['tasks']['one']['model']
            # First monitor sweeps every public input to retain a factual baseline.
            for _ in range(8):a.tick_concepts({'one':v})
            w.change_law('and_not')
            events=[a.tick_concepts({'one':v}) for _ in range(8)]
            self.assertTrue(any(e['kind']=='LOCAL_CONTRADICTION_REOPEN' for e in events))
            self.assertFalse(a.state()['s22']['nodes'][old]['valid'])
        finally:a.close();w.close();tmp.cleanup()
    def test_campaign_has_48_distinct_predeclared(self):
        c=cases();self.assertEqual(len(c),48)
        self.assertEqual(len({str(x) for x in c}),48)

if __name__=='__main__':unittest.main()

class PairedContrasts(unittest.TestCase):
    def test_12_low_budget_pairs_equal_b2(self):
        count_T=count_B=0
        for law in ('xor','and_not','majority','exactly_one','even_parity','nand'):
            for variant in (0,1):
                r=run_pair32(law,4,variant,ticks=20)
                count_T+=r['results']['T32']['acts'];count_B+=r['results']['B2']['acts']
                self.assertEqual(r['results']['T32']['failed_actions'],0)
                self.assertGreaterEqual(r['results']['T32']['remaining'],0)
        self.assertEqual((count_T,count_B),(10,10))
    def test_drift_still_detected_with_local_scopes(self):
        r=run_pair32('exactly_one',50,0,ticks=60,drift=True,restart=True)
        e=[x['kind'] for x in r['results']['T32']['events']]
        self.assertIn('LOCAL_CONTRADICTION_REOPEN',e)
        self.assertEqual(r['results']['T32']['acts'],r['results']['B2']['acts'])
    def test_nothing_actuated_without_measured_positive_in_low_budget(self):
        for law in ('xor','and_not','majority','exactly_one','even_parity','nand'):
            r=run_pair32(law,4,0,ticks=20)
            for ev in r['results']['T32']['events']:
                if ev['kind']=='ACTION_PERFORMED':
                    self.assertTrue(any(x['kind']=='LOCAL_SUFFICIENT_EVIDENCE' for x in r['results']['T32']['events']))
    def test_goal_change_local_model_still_revision_aware(self):
        r=run_pair32('xor',50,1,ticks=40,goal=True,restart=True)
        e=[x['kind'] for x in r['results']['T32']['events']]
        self.assertIn('ACTION_PERFORMED',e)
        self.assertEqual(r['results']['T32']['failed_actions'],0)
        self.assertEqual(r['results']['T32']['integrity'],'ok')
