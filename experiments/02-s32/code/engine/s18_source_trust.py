"""S18 agent-level source trust inquiry; based only on public contract and receipted evidence.

The host's true law/outcome and scenario name are inaccessible to this class.
"""
from .s17_transfer import SensorTransferAgent


class SourceTrustAgent(SensorTransferAgent):
    """Construct a second-source validity test before irreversible ACT."""

    def proposal(self):
        s = self.state()
        if s['status'] != 'ACTIVE':
            return ('NONE', None)
        phase = s['phase']
        if phase == 'S18_EXPECT_C_FIRST' or phase == 'S18_EXPECT_C_REPEAT':
            return self.propose_challenge(s)
        if phase == 'S18_AFTER_C_FIRST':
            s['phase'] = 'S18_EXPECT_C_REPEAT'
            self.save(s)
            return self.propose_challenge(s)
        if phase == 'S18_AFTER_C_REPEAT':
            return self.evaluate_challenge(s)

        # The unmodified S17 agent makes its own proposal; this layer never
        # inserts a privileged choice of physical action or a hidden answer.
        kind, request = super().proposal()
        if kind != 'ACT' or not self.public.get('trust_challenge_enabled', True):
            return kind, request

        s = self.state()
        if not s.get('s18_trust_attestation'):
            if not self.public.get('C_available', True):
                return self.halt(s, 'S18_NO_INDEPENDENT_CHALLENGE')
            if not self.public.get('C_certified', True):
                return self.halt(s, 'S18_CHALLENGE_UNTRUSTED')
            self.event(s, 'S18_TRUST_QUESTION', question='Does the apparently reliable B agree with an independently sampled C before action?',
                       origin='B has only contract-based source trust; cross-check demanded before consequence')
            s['phase'] = 'S18_EXPECT_C_FIRST'
            self.save(s)
            return self.propose_challenge(s)

        b = [e for e in s['evidence'] if e['channel'] == 'B']
        c = [e for e in s['evidence'] if e['channel'] == 'C']
        att = s['s18_trust_attestation']
        if len(b) != 2 or len(c) != 2 or att.get('basis_receipts') != [x['receipt_id'] for x in b+c]:
            return self.halt(s, 'S18_ATTESTATION_LOST_BASIS')
        request['reference_receipts'] = [x['receipt_id'] for x in b+c]
        return ('ACT', request)

    def propose_challenge(self, s):
        if not self.public.get('C_available', True) or not self.public.get('C_certified', True):
            return self.halt(s, 'S18_CHALLENGE_UNAVAILABLE')
        if s['budget'] < self.public['read_cost']:
            return self.halt(s, 'S18_BUDGET_EXHAUSTED_BEFORE_C')
        key = f'S18-READ-{len(s["evidence"])+1}-C'
        return ('READ', {'channel':'C', 'key':key})

    def commit_read(self, obs):
        s = self.state()
        if s['phase'] not in ('S18_EXPECT_C_FIRST','S18_EXPECT_C_REPEAT'):
            return super().commit_read(obs)
        key = f'S18-READ-{len(s["evidence"])+1}-C'
        if s['status'] != 'ACTIVE' or obs.get('receipt_id') != key or obs.get('channel') != 'C':
            raise ValueError('S18 evidence does not match requested C receipt')
        if not isinstance(obs.get('radius'), (float,int)) or obs['radius'] < 0:
            raise ValueError('invalid uncertainty radius')
        if s['budget'] < self.public['read_cost']:
            raise ValueError('S18 observation with exhausted budget')
        s['budget'] -= self.public['read_cost']
        s['evidence'].append(obs)
        s['phase'] = 'S18_AFTER_C_FIRST' if s['phase'] == 'S18_EXPECT_C_FIRST' else 'S18_AFTER_C_REPEAT'
        self.event(s, 'S18_C_OBSERVATION_RECEIVED', receipt=key, value=obs['value'])
        self.save(s)

    def evaluate_challenge(self,s):
        b=[e for e in s['evidence'] if e['channel']=='B']
        c=[e for e in s['evidence'] if e['channel']=='C']
        if len(b)!=2 or len(c)!=2 or len({x['receipt_id'] for x in b+c})!=4:
            return self.halt(s, 'S18_INCOMPLETE_TRUST_EVIDENCE')
        if abs(c[0]['value']-c[1]['value']) > c[0]['radius']+c[1]['radius']:
            s['trust_revision']={'B':'unresolved','C':'unstable','basis_receipts':[x['receipt_id'] for x in c]}
            self.event(s,'S18_TRUST_REVISION',revision=s['trust_revision'])
            return self.halt(s,'S18_C_SELF_CONTRADICTION')
        if any(abs(v['value']-w['value'])>v['radius']+w['radius'] for v in b for w in c):
            s['trust_revision']={'B':'challenged_by_C','C':'not_proven_true','basis_receipts':[x['receipt_id'] for x in b+c]}
            self.event(s,'S18_TRUST_REVISION',revision=s['trust_revision'])
            return self.halt(s,'S18_TRUST_B_C_CONTRADICTION')
        if min(x['value']-x['radius'] for x in b+c)<=self.public['output_floor']:
            return self.halt(s,'S18_COMPASS_DENIED_AFTER_CHALLENGE')
        if s['budget']<self.public['action_cost']:
            return self.halt(s,'S18_ACTION_BUDGET_INSUFFICIENT')
        s['s18_trust_attestation']={'status':'B_C_AGREE_UNDER_DECLARED_INDEPENDENCE',
                                      'basis_receipts':[x['receipt_id'] for x in b+c],
                                      'limit':'agreement does not prove both sources truthful'}
        self.event(s,'S18_TRUST_BASIS_ACCEPTED',basis=s['s18_trust_attestation'])
        s['phase']='READY_TO_ACT'
        self.save(s)
        return self.proposal()

    def commit_act(self, receipt):
        super().commit_act(receipt)
        s = self.state()
        if s.get('reason') == 'EXECUTION_MISMATCH':
            revision={'B':'revoked_on_outcome','basis_receipts':receipt['reference_receipts']}
            if any(e['channel']=='C' for e in s['evidence']):
                revision['C']='revoked_on_outcome'
            s['trust_revision']=revision
            if s.get('s18_trust_attestation'):
                s['s18_trust_attestation']['status']='REVOKED_BY_OUTCOME'
            self.event(s,'S18_TRUST_REVOKED_AFTER_OUTCOME',revision=s['trust_revision'])
            self.save(s)
