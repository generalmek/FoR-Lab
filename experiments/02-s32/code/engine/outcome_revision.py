"""Revoke disproved transferred knowledge; execution receipts are not training oracles."""
import json
from expanding_cycle import ExpandingCycle
from full_cycle import HYPOTHESES


class OutcomeRevisionCycle(ExpandingCycle):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.db.execute('CREATE TABLE IF NOT EXISTS model_revocations(task INTEGER PRIMARY KEY,through_id INTEGER,body TEXT)')
        self.db.commit()

    def start_cycle(self, world, *args, **kwargs):
        super().start_cycle(world, *args, **kwargs)
        latest = self.db.execute('SELECT COALESCE(MAX(id),0) FROM worldview_sets').fetchone()[0]
        revoked = self.db.execute('SELECT COALESCE(MAX(through_id),-1) FROM model_revocations').fetchone()[0]
        if latest <= revoked:
            s = self.state()
            s.update(pool=HYPOTHESES, verified=False, transferred=False, worldview_saved=False)
            with self.db:
                self.event(s, 'RESEARCH_REQUIRED_AFTER_OUTCOME', revoked_through=revoked)
                self.save(s)

    def step(self, world, fail_at=None):
        result = super().step(world, fail_at)
        if result.get('reason') == 'EXECUTION_MISMATCH':
            with self.db:
                latest = self.db.execute('SELECT COALESCE(MAX(id),0) FROM worldview_sets').fetchone()[0]
                intent = self.db.execute('SELECT id,body FROM intents WHERE status=\'done\' ORDER BY rowid DESC LIMIT 1').fetchone()
                evidence = dict(context=result['context'], receiver_id=world.receiver_id,
                                operation_id=intent[0] if intent else None,
                                request=json.loads(intent[1]) if intent else None,
                                receipt=world.lookup(intent[0]) if intent else None,
                                scope='outcome contradiction only; no assumption of stationary law or perfect real sensor')
                inserted = self.db.execute('INSERT OR IGNORE INTO model_revocations VALUES(?,?,?)',
                                           (result['task_id'], latest, json.dumps(evidence))).rowcount
                self.db.execute('UPDATE forecasts SET valid=0')
                result.update(verified=False, worldview_saved=False)
                if inserted:
                    self.event(result, 'OUTCOME_REVOKED_MODEL', evidence=evidence, revoked_through=latest)
                self.save(result)
        return result
