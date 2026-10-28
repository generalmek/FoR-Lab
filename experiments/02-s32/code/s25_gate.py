"""S25 common action permission check for both legacy S16 and revised S24.

Pure causal adjudication: no host variant, private world law, or disk access.
Return a proof of permission, not proof of a successful future outcome.
"""
from math import isfinite
from s22_semantic_kernel import valid_dependency_path

class ActionDenied(RuntimeError):pass

def effective_source_basis(state):
    """Proof-carrying replacement of a revoked source claim, not an unearned reset.

    Only the latest *finished and validated* source inquiry can provide a
    replacement, and its cross-domain reissue must be presently valid.
    """
    nodes=state['s22']['nodes']
    if valid_dependency_path(nodes,'source:attestation'):
        return 'source:attestation'
    episode=state.get('s23',{})
    if episode.get('active') is not None or episode.get('status')!='VALIDATED':
        return None
    history=episode.get('history',[])
    if not history or history[-1].get('domain')!='source' or history[-1].get('status')!='VALIDATED':
        return None
    origin=history[-1]['event_id']
    root='source:s23:revised_basis:'+origin
    reissued='decision:s23:reissued:'+origin
    if (valid_dependency_path(nodes,root) and valid_dependency_path(nodes,reissued)
        and root in nodes[reissued].get('depends',[])
        and state['s21']['permission']['status']=='VALID'
        and reissued in state['s21']['permission'].get('basis',[])):
        return root
    return None


def authorize(state, *, route, operation_id, control, expected, output_floor, current_context, local_token=None, legacy_evidence=None):
    if not isinstance(operation_id,str) or not operation_id:raise ActionDenied('INVALID_OPERATION_ID')
    if type(control) is not int or control<1:raise ActionDenied('INVALID_CONTROL')
    if type(expected) not in (float,int) or not isfinite(expected):raise ActionDenied('INVALID_PREDICTION')
    if type(output_floor) not in (float,int) or not isfinite(output_floor):raise ActionDenied('INVALID_FLOOR')
    if expected<=output_floor:raise ActionDenied('COMPASS_PREDICTION_BELOW_FLOOR')
    if state['phase']!='ACTIVE':raise ActionDenied('EPISODE_NOT_ACTIVE')
    if state['shared_budget']<1:raise ActionDenied('GLOBAL_BUDGET_EXHAUSTED')
    nodes=state['s22']['nodes']
    source_basis=effective_source_basis(state)
    if source_basis is None:
        raise ActionDenied('SOURCE_BASIS_INVALID')
    if route=='revised':
        a=state['s24']['action']
        if state['s24']['status']!='READY_TO_ACT' or a is None:
            raise ActionDenied('NO_ACTIVE_REVISED_DECISION')
        if (local_token is None or (operation_id,control,expected)!=local_token
            or (operation_id,control,expected)!=(a['id'],a['control'],a['expected'])):
            raise ActionDenied('DIRECT_EXECUTOR_BYPASS')
        if not valid_dependency_path(nodes,a['decision']):raise ActionDenied('REVISED_PROOF_INVALID')
        decision=nodes[a['decision']]
        if decision.get('control')!=control or decision.get('expected')!=expected:
            raise ActionDenied('PERMISSION_CONTENT_MISMATCH')
        if state['s21']['permission']['status']!='VALID' or a['decision'] not in state['s21']['permission'].get('basis',[]):
            raise ActionDenied('MISSING_SHARED_PERMISSION')
        revised=state['s24']['local_models'][-1]
        if revised['scope']['context']!=current_context:
            raise ActionDenied('CHANGED_CONTEXT')
        if revised['outputs'].get(str(control))!=expected:
            raise ActionDenied('PREDICTION_NOT_LOCALLY_MEASURED')
        return {'route':route,'decision':a['decision'],'control':control,'expected':expected,
                'evidence':list(decision['depends']),'worldview_revision':state['s22']['revision']}
    if route=='legacy':
        if state['s24']['status']!='IDLE':raise ActionDenied('LEGACY_EXECUTOR_DURING_REVISION')
        if state['s23']['active'] is not None:raise ActionDenied('OPEN_DIAGNOSTIC_QUESTION')
        if not valid_dependency_path(nodes,'actuator:model'):
            raise ActionDenied('LEGACY_MODEL_INVALID')
        legacy_decision='decision:actuator_authorization' if valid_dependency_path(nodes,'decision:actuator_authorization') else None
        if legacy_decision is None and source_basis.startswith('source:s23:revised_basis:'):
            origin=source_basis.removeprefix('source:s23:revised_basis:')
            reissued='decision:s23:reissued:'+origin
            if valid_dependency_path(nodes,reissued) and 'actuator:model' in nodes[reissued].get('depends',[]):
                legacy_decision=reissued
        # S25 historical authorization accepted a valid original decision
        # under VALID status; only the *new* substitute requires an exact
        # cross-domain reissue in the active permission basis.
        if (state['s21']['permission']['status']!='VALID' or legacy_decision is None or
            (legacy_decision!='decision:actuator_authorization' and
             legacy_decision not in state['s21']['permission'].get('basis',[]))):
            raise ActionDenied('LEGACY_SHARED_PERMISSION_INVALID')
        if not state['actuator_calibrated']:raise ActionDenied('LEGACY_NOT_CALIBRATED')
        model=nodes['actuator:model']
        if model.get('context')!=current_context:raise ActionDenied('LEGACY_SCOPE_MISMATCH')
        measured=[ob for ob in (legacy_evidence or [])
                  if ob.get('probe')=='U'+str(control) and ob.get('value')==expected
                  and 'actuator:receipt:'+str(ob.get('operation_id')) in model.get('depends',[])
                  and valid_dependency_path(nodes,'actuator:receipt:'+str(ob.get('operation_id')))
                  and nodes['actuator:receipt:'+str(ob.get('operation_id'))].get('context')==current_context
                  and nodes['actuator:receipt:'+str(ob.get('operation_id'))].get('task_id')==model.get('task')]
        if not measured:raise ActionDenied('LEGACY_EXPECTATION_NOT_FRESHLY_MEASURED')
        return {'route':route,'decision':legacy_decision,'control':control,
                'expected':expected,'evidence':list(nodes[legacy_decision]['depends']),
                'worldview_revision':state['s22']['revision']}
    raise ActionDenied('UNKNOWN_GATE_ROUTE')
