"""S17 limited cross-domain research-method transfer.

Source: real validated S16 programs, not a human-written result label.
Target: a distinct sensor provenance problem, not actuator U3/U4.
Only a public capability contract and receipted observations enter this agent.
Private scenario names are kept exclusively in the virtual receiver.
"""
import hashlib
import json
import sqlite3
from pathlib import Path

OP_BINDINGS = {
    'FRESH_REPEAT': 'REPEAT_SUSPECT_SOURCE',
    'ISOLATE_PERSISTENT_RESIDUAL': 'QUARANTINE_PERSISTENT_SOURCE_RESIDUAL',
    'ISOLATE_AMBIGUOUS_CONTROL': 'QUARANTINE_UNSTABLE_SOURCE',
    'PROPOSE_INDEPENDENT_CONTROL': 'SELECT_INDEPENDENT_MEASUREMENT_SOURCE',
    'REQUEST_LOCAL_VALIDATION': 'VALIDATE_INDEPENDENT_SOURCE_TWICE',
}
REQUIRED_STABLE = ['REPEAT_SUSPECT_SOURCE', 'QUARANTINE_PERSISTENT_SOURCE_RESIDUAL',
                   'SELECT_INDEPENDENT_MEASUREMENT_SOURCE','VALIDATE_INDEPENDENT_SOURCE_TWICE']
REQUIRED_UNSTABLE = ['REPEAT_SUSPECT_SOURCE', 'QUARANTINE_UNSTABLE_SOURCE',
                     'SELECT_INDEPENDENT_MEASUREMENT_SOURCE','VALIDATE_INDEPENDENT_SOURCE_TWICE']

def json_hash(obj):
    return hashlib.sha256(json.dumps(obj,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()

def extract_source_motifs(stable,unstable):
    """Use actual terminal state + action receipts, not prepackaged programs."""
    motifs = {}
    for kind, snapshot, isolator in (
        ('stable',stable,'ISOLATE_PERSISTENT_RESIDUAL'),
        ('unstable',unstable,'ISOLATE_AMBIGUOUS_CONTROL')):
        s=snapshot['state']; p=s.get('s16_program')
        if snapshot['life']['status']!='DONE' or not p or p['status']!='validated_by_action_and_receipt':
            raise ValueError('S16 training source did not finish with validated result')
        if len(p['evidence_ids'])!=2 or len(set(p['evidence_ids']))!=2:
            raise ValueError('S16 diagnostic evidence missing distinct receipts')
        steps=[o for stage in p['stages'] for o in stage['operators']]
        if steps!=['FRESH_REPEAT',isolator,'PROPOSE_INDEPENDENT_CONTROL','REQUEST_LOCAL_VALIDATION']:
            raise ValueError('unexpected source plan: cannot establish structural transfer')
        if not any(r['request'][0]==4 for r in snapshot['receipts']):
            raise ValueError('source lacks independent U4 physical completion')
        motifs[kind]={'source_operator_sequence':steps,'transfer_operator_sequence':[OP_BINDINGS[o] for o in steps],
                      'source_evidence_ids':list(p['evidence_ids']),
                      'source_outcome':'validated_by_action_and_receipt',
                      'source_receipt_count':len(snapshot['receipts']),
                      'source_task_id':p['task_id'],
                      'meaning_mapping':'control-specific residual -> source-specific measurement residual'}
    return {'provenance':'S16 executed/composed and receipted trials, rebind roles in S17',
            'motifs':motifs,'fingerprint':json_hash(motifs)}

class SensorTransferAgent:
    """Pure control loop against observations. No reference to private world object."""
    def __init__(self, db_path, source, public, *, transfer_enabled=True, budget=12):
        self.db=sqlite3.connect(str(db_path))
        self.db.execute('CREATE TABLE IF NOT EXISTS s17_contract(id INTEGER PRIMARY KEY,body TEXT NOT NULL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS s17_state(id INTEGER PRIMARY KEY,body TEXT NOT NULL)')
        self.contract=dict(source_digest=json_hash(source),public=public,enabled=bool(transfer_enabled),budget=budget,version=1)
        row=self.db.execute('SELECT body FROM s17_contract WHERE id=1').fetchone()
        if row and json.loads(row[0])!=self.contract:
            self.db.close();raise ValueError('S17 agent contract mismatch on reopen')
        if not row:
            state=dict(phase='START',status='ACTIVE',reason=None,budget=budget,evidence=[],events=[],
                       candidate=None,diagnosis=None,source_digest=json_hash(source),selected_program=None,
                       action_receipt=None)
            with self.db:
                self.db.execute('INSERT INTO s17_contract VALUES(1,?)',(json.dumps(self.contract,sort_keys=True),))
                self.db.execute('INSERT INTO s17_state VALUES(1,?)',(json.dumps(state,sort_keys=True),))
        self.source=source; self.public=public
    def close(self):self.db.close()
    def state(self):return json.loads(self.db.execute('SELECT body FROM s17_state WHERE id=1').fetchone()[0])
    def save(self,s):
        with self.db:self.db.execute('UPDATE s17_state SET body=? WHERE id=1',(json.dumps(s,sort_keys=True),))
    def event(self,s,kind,**kw):s['events'].append(dict(index=len(s['events'])+1,kind=kind,**kw))
    def halt(self,s,reason):
        s.update(status='STOPPED',phase='HALT',reason=reason)
        self.event(s,'STOP',reason=reason);self.save(s);return ('NONE',None)
    def proposal(self):
        s=self.state(); phase=s['phase'];pub=self.public
        if s['status']!='ACTIVE':return ('NONE',None)
        if phase=='START':
            s['phase']='EXPECT_A_FIRST';self.save(s)
            phase=s['phase']
        if phase=='EXPECT_A_FIRST':return self.propose_read(s,'A')
        if phase=='AFTER_A_FIRST':
            a=s['evidence'][-1]['value'];r=s['evidence'][-1]['radius']
            if abs(a-pub['baseline'])<=r:return self.halt(s,'NO_UNEXPECTED_SENSORY_GAP')
            if not self.contract['enabled']:return self.halt(s,'TRANSFER_ABLATED_NO_METHOD')
            if not self.source.get('motifs'):return self.halt(s,'NO_VALIDATED_TRANSFER_SOURCE')
            # A fresh repeat is required by both source motifs. No cause diagnosis yet.
            plans=[v['transfer_operator_sequence'] for v in self.source['motifs'].values()]
            if not plans or any(p[0]!='REPEAT_SUSPECT_SOURCE' for p in plans):
                return self.halt(s,'SOURCE_METHOD_NOT_TRANSFERABLE')
            self.event(s,'S17_QUESTION',question='Does the source discrepancy persist, and what independently distinguishes causes?',
                       origin='prediction-observation discrepancy',source_digest=s['source_digest'])
            s['transfer_repeat_origin']='S16_FRESH_REPEAT'
            self.event(s,'S17_OPERATOR_EXECUTED',operator='REPEAT_SUSPECT_SOURCE',role='A')
            s['phase']='EXPECT_A_REPEAT';self.save(s)
            return self.propose_read(s,'A')
        if phase=='EXPECT_A_REPEAT':return self.propose_read(s,'A')
        if phase=='AFTER_A_REPEAT':
            a=s['evidence'][-2:]
            kind='stable' if abs(a[0]['value']-a[1]['value'])<=a[0]['radius']+a[1]['radius'] else 'unstable'
            motif=self.source.get('motifs',{}).get(kind)
            expected=REQUIRED_STABLE if kind=='stable' else REQUIRED_UNSTABLE
            if not motif or motif['transfer_operator_sequence']!=expected:
                return self.halt(s,'NO_APPLICABLE_TRANSFERRED_PROGRAM')
            s['selected_program']=dict(source_kind=kind,steps=expected,source_digest=s['source_digest'],
                                       evidence_receipts=[e['receipt_id'] for e in a],status='selected')
            self.event(s,'S17_PROGRAM_REBOUND',branch=kind,operations=expected,
                       evidence_receipts=[e['receipt_id'] for e in a])
            # Interpret the transferred operator list, rather than merely
            # annotating a hard-coded host path. Public role bindings supply B.
            for operator in s['selected_program']['steps'][1:]:
                if operator=='QUARANTINE_PERSISTENT_SOURCE_RESIDUAL':
                    if kind!='stable':raise AssertionError('persistent operator requires stable repeat')
                    s['quarantined_source']='A';s['quarantine_reason']='reproducible residual'
                elif operator=='QUARANTINE_UNSTABLE_SOURCE':
                    if kind!='unstable':raise AssertionError('unstable operator requires conflicting repeat')
                    s['quarantined_source']='A';s['quarantine_reason']='inconsistent source readings'
                elif operator=='SELECT_INDEPENDENT_MEASUREMENT_SOURCE':
                    if s.get('quarantined_source')!='A':raise AssertionError('independent source needs localized question')
                    if not pub['B_available']:return self.halt(s,'NO_INDEPENDENT_SENSOR')
                    if not pub['B_certified']:return self.halt(s,'INDEPENDENT_SENSOR_NOT_CERTIFIED')
                    s['selected_independent_source']='B'
                elif operator=='VALIDATE_INDEPENDENT_SOURCE_TWICE':
                    if s.get('selected_independent_source')!='B':raise AssertionError('no independent source bound')
                    s['validation_remaining']=2
                else:raise ValueError('transfer language unknown operation: '+operator)
                self.event(s,'S17_OPERATOR_EXECUTED',operator=operator,role=s.get('selected_independent_source','A'))
            if s.get('validation_remaining')!=2:return self.halt(s,'TRANSFER_PROGRAM_INCOMPLETE')
            s['phase']='EXPECT_B_FIRST';self.save(s)
            return self.propose_read(s,'B')
        if phase=='EXPECT_B_FIRST':return self.propose_read(s,'B')
        if phase=='AFTER_B_FIRST':
            s['validation_remaining']-=1
            if s['validation_remaining']!=1:return self.halt(s,'TRANSFER_VALIDATION_COUNTER_INVALID')
            s['phase']='EXPECT_B_REPEAT';self.save(s)
            return self.propose_read(s,'B')
        if phase=='EXPECT_B_REPEAT':return self.propose_read(s,'B')
        if phase=='AFTER_B_REPEAT':
            s['validation_remaining']-=1
            if s['validation_remaining']!=0:return self.halt(s,'TRANSFER_VALIDATION_COUNTER_INVALID')
            a=[e for e in s['evidence'] if e['channel']=='A'];b=[e for e in s['evidence'] if e['channel']=='B']
            if len(a)!=2 or len(b)!=2 or len(set(x['receipt_id'] for x in s['evidence']))!=4:
                return self.halt(s,'INCOMPLETE_DIFFERENTIAL_EVIDENCE')
            if abs(b[0]['value']-b[1]['value'])>b[0]['radius']+b[1]['radius']:
                return self.halt(s,'INDEPENDENT_SENSOR_CONTRADICTS_ITSELF')
            a_stable=abs(a[0]['value']-a[1]['value'])<=a[0]['radius']+a[1]['radius']
            if not a_stable:diagnosis='SUSPECT_SENSOR_UNSTABLE; PHYSICAL_CAUSE_NOT_IDENTIFIED'
            elif abs(a[-1]['value']-b[-1]['value'])<=a[-1]['radius']+b[-1]['radius']:
                diagnosis='PROCESS_OR_SHARED_SOURCE_CHANGE_WITHIN_CERTIFIED_B_CONTRACT'
            else:
                diagnosis='SUSPECT_SENSOR_BIAS_RELATIVE_TO_CERTIFIED_B'
            s['diagnosis']=diagnosis
            s['selected_program']['status']='independent_evidence_validated'
            self.event(s,'S17_DIFFERENTIAL_EVIDENCE',diagnosis=diagnosis,reference_receipts=[x['receipt_id'] for x in b])
            if min(x['value']-x['radius'] for x in b)<=pub['output_floor']:
                return self.halt(s,'INTERNAL_COMPASS_DENIED')
            if s['budget']<pub['action_cost']:
                return self.halt(s,'ACTION_BUDGET_INSUFFICIENT')
            s['phase']='READY_TO_ACT';self.save(s)
            return ('ACT',{'key':'S17-ACT-1','predicted':b[-1]['value'],
                           'reference_receipts':[x['receipt_id'] for x in b]})
        if phase=='READY_TO_ACT':
            b=[e for e in s['evidence'] if e['channel']=='B']
            if len(b)!=2 or not pub['B_certified'] or b[0]['value']!=b[1]['value'] or min(e['value']-e['radius'] for e in b)<=pub['output_floor']:
                return self.halt(s,'ACTION_LOST_CAUSAL_BASIS')
            if s['budget']<pub['action_cost']:return self.halt(s,'ACTION_BUDGET_INSUFFICIENT')
            return ('ACT',{'key':'S17-ACT-1','predicted':b[-1]['value'],
                           'reference_receipts':[e['receipt_id'] for e in b]})
        return self.halt(s,'INVALID_AGENT_PHASE')
    def propose_read(self,s,channel):
        if channel=='B' and (not self.public['B_available'] or not self.public['B_certified']):
            return self.halt(s,'UNTRUSTED_SENSOR_READ')
        if s['budget']<self.public['read_cost']:return self.halt(s,'INSUFFICIENT_SENSOR_BUDGET')
        key=f'S17-READ-{len(s["evidence"])+1}-{channel}'
        return ('READ',{'channel':channel,'key':key})
    def commit_read(self, obs):
        s=self.state()
        if s['status']!='ACTIVE' or not s['phase'].startswith('EXPECT_'):raise ValueError('not expecting evidence')
        channel=s['phase'].split('_')[1]
        if obs['channel']!=channel or obs['receipt_id']!=f'S17-READ-{len(s["evidence"])+1}-{channel}':
            raise ValueError('evidence receipt does not match requested channel/id')
        if s['budget']<self.public['read_cost']:raise ValueError('budget changed before observation')
        s['budget']-=self.public['read_cost'];s['evidence'].append(obs)
        s['phase']={'EXPECT_A_FIRST':'AFTER_A_FIRST','EXPECT_A_REPEAT':'AFTER_A_REPEAT',
                    'EXPECT_B_FIRST':'AFTER_B_FIRST','EXPECT_B_REPEAT':'AFTER_B_REPEAT'}[s['phase']]
        self.event(s,'S17_OBSERVATION_RECEIVED',channel=channel,receipt=obs['receipt_id'],value=obs['value'])
        self.save(s)
    def commit_act(self,receipt):
        s=self.state()
        if s['status']!='ACTIVE' or s['phase']!='READY_TO_ACT' or receipt['key']!='S17-ACT-1':
            raise ValueError('unmatched physical receipt')
        if s['budget']<self.public['action_cost']:raise ValueError('budget changed before action')
        s['budget']-=self.public['action_cost'];s['action_receipt']=receipt
        if receipt['actual']!=receipt['prediction']:
            s['phase']='HALT';s['status']='STOPPED';s['reason']='EXECUTION_MISMATCH'
            s['question_after_mismatch']='Which apparently independent measurement guarantee failed?'
            if s['selected_program'] is not None:s['selected_program']['status']='revoked_after_outcome_mismatch'
            self.event(s,'S17_ACTION_OUTCOME_CONTRADICTION',receipt=receipt,
                       question=s['question_after_mismatch'])
        else:
            s['phase']='DONE';s['status']='DONE'
            if s['selected_program'] is not None:s['selected_program']['status']='validated_by_action_and_receipt'
            self.event(s,'S17_ACTION_COMPLETED',receipt=receipt)
        self.save(s)
