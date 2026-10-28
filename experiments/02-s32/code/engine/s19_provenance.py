"""S19: agent-initiated provenance challenge when B and C share a declared lineage.

This class has no access to private worlds, hidden outcomes, or scenario identifiers.
The declared provenance is itself an assumption, not an oracle.
"""
from .s18_source_trust import SourceTrustAgent


class ProvenanceInquiryAgent(SourceTrustAgent):
    def proposal(self):
        s=self.state()
        if s['status']!='ACTIVE':
            return ('NONE',None)
        if s['phase'] in ('S19_EXPECT_D_FIRST','S19_EXPECT_D_REPEAT'):
            return self.propose_D(s)
        if s['phase']=='S19_AFTER_D_FIRST':
            s['phase']='S19_EXPECT_D_REPEAT';self.save(s)
            return self.propose_D(s)
        if s['phase']=='S19_AFTER_D_REPEAT':
            return self.evaluate_D(s)

        kind,request=super().proposal()
        if kind!='ACT' or not self.public.get('provenance_challenge_enabled',True):
            return (kind,request)
        s=self.state()
        roots=self.public.get('provenance_roots',{})
        if not isinstance(roots,dict) or not roots.get('B') or not roots.get('C'):
            return self.halt(s,'S19_SOURCE_PROVENANCE_NOT_AVAILABLE')
        if roots['B']!=roots['C']:
            self.event_once(s,'S19_DECLARED_ROOTS_DIFFER',roots={'B':roots['B'],'C':roots['C']})
            self.save(s)
            return (kind,request)
        att=s.get('s19_provenance_attestation')
        if att:
            b=[e for e in s['evidence'] if e['channel']=='B']
            c=[e for e in s['evidence'] if e['channel']=='C']
            d=[e for e in s['evidence'] if e['channel']=='D']
            if (len(b)!=2 or len(c)!=2 or len(d)!=2 or
                att.get('basis_receipts')!=[e['receipt_id'] for e in b+c+d] or
                att.get('status')!='DECLARED_SEPARATE_ROOT_AND_MATCHING_EVIDENCE'):
                return self.halt(s,'S19_PROVENANCE_BASIS_REVOKED')
            request=dict(request)
            request['reference_receipts']=[e['receipt_id'] for e in b+c+d]
            return ('ACT',request)
        self.event(s,'S19_PROVENANCE_QUESTION',question='Are B and C really independent if both inherit the same calibration root?',
                   basis={'B':roots['B'],'C':roots['C']},origin='declared shared provenance detected before action')
        if not self.public.get('D_available',False):
            return self.halt(s,'S19_NO_DISTINCT_SOURCE_AVAILABLE')
        if not self.public.get('D_certified',False):
            return self.halt(s,'S19_D_NOT_CERTIFIED')
        if not roots.get('D') or roots['D']==roots['B']:
            return self.halt(s,'S19_D_SHARES_SAME_DECLARED_ROOT')
        s['phase']='S19_EXPECT_D_FIRST';self.save(s)
        return self.propose_D(s)

    def event_once(self,s,kind,**kw):
        if not any(e['kind']==kind for e in s['events']):
            self.event(s,kind,**kw)

    def propose_D(self,s):
        if not self.public.get('D_available',False) or not self.public.get('D_certified',False):
            return self.halt(s,'S19_D_UNAVAILABLE_AFTER_INQUIRY')
        roots=self.public.get('provenance_roots',{})
        if not roots.get('D') or roots.get('D')==roots.get('B'):
            return self.halt(s,'S19_D_ROOT_NOT_DISTINCT')
        if s['budget']<self.public['read_cost']:
            return self.halt(s,'S19_BUDGET_EXHAUSTED_BEFORE_D')
        return ('READ',{'channel':'D','key':f'S19-READ-{len(s["evidence"])+1}-D'})

    def commit_read(self,obs):
        s=self.state()
        if s['phase'] not in ('S19_EXPECT_D_FIRST','S19_EXPECT_D_REPEAT'):
            return super().commit_read(obs)
        key=f'S19-READ-{len(s["evidence"])+1}-D'
        if s['status']!='ACTIVE' or obs.get('channel')!='D' or obs.get('receipt_id')!=key:
            raise ValueError('S19 D evidence does not match requested receipt')
        if not isinstance(obs.get('radius'),(float,int)) or obs['radius']<0:
            raise ValueError('S19 invalid uncertainty radius')
        if s['budget']<self.public['read_cost']:
            raise ValueError('S19 observation with exhausted budget')
        if any(e['receipt_id']==key for e in s['evidence']):
            raise ValueError('S19 duplicate receipt')
        s['budget']-=self.public['read_cost']
        s['evidence'].append(obs)
        s['phase']='S19_AFTER_D_FIRST' if s['phase']=='S19_EXPECT_D_FIRST' else 'S19_AFTER_D_REPEAT'
        self.event(s,'S19_D_OBSERVATION_RECEIVED',receipt=key,value=obs['value'])
        self.save(s)

    def evaluate_D(self,s):
        b=[e for e in s['evidence'] if e['channel']=='B']
        c=[e for e in s['evidence'] if e['channel']=='C']
        d=[e for e in s['evidence'] if e['channel']=='D']
        all_e=b+c+d
        if len(b)!=2 or len(c)!=2 or len(d)!=2 or len({e['receipt_id'] for e in all_e})!=6:
            return self.halt(s,'S19_INCOMPLETE_THIRD_SOURCE_EVIDENCE')
        roots=self.public.get('provenance_roots',{})
        if roots.get('B')!=roots.get('C') or roots.get('D') in (None,roots.get('B')):
            return self.halt(s,'S19_PROVENANCE_CHANGED_OR_NOT_DISTINCT')
        self.event(s,'S19_PROVENANCE_COMPARISON',roots=roots,receipts=[e['receipt_id'] for e in all_e])
        if abs(d[0]['value']-d[1]['value'])>d[0]['radius']+d[1]['radius']:
            s['s19_revision']={'status':'D_UNSTABLE','basis_receipts':[e['receipt_id'] for e in d]}
            self.save(s)
            return self.halt(s,'S19_D_SELF_CONTRADICTION')
        if any(abs(x['value']-y['value'])>x['radius']+y['radius'] for x in b+c for y in d):
            s['s19_revision']={'status':'B_C_COMMON_ROOT_CHALLENGED_BY_D','basis_receipts':[e['receipt_id'] for e in all_e]}
            self.save(s)
            return self.halt(s,'S19_SHARED_ROOT_EVIDENCE_CONTRADICTION')
        if min(x['value']-x['radius'] for x in all_e)<=self.public['output_floor']:
            return self.halt(s,'S19_COMPASS_DENIED_AFTER_D')
        if s['budget']<self.public['action_cost']:
            return self.halt(s,'S19_ACTION_BUDGET_INSUFFICIENT')
        s['s19_provenance_attestation']={'status':'DECLARED_SEPARATE_ROOT_AND_MATCHING_EVIDENCE',
                                       'basis_receipts':[e['receipt_id'] for e in all_e],
                                       'roots':{'B':roots['B'],'C':roots['C'],'D':roots['D']},
                                       'limit':'declared source origins may themselves be false'}
        self.event(s,'S19_PROVENANCE_BASIS_ACCEPTED',attestation=s['s19_provenance_attestation'])
        s['phase']='READY_TO_ACT';self.save(s)
        return self.proposal()
