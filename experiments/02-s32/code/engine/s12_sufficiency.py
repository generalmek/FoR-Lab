"""S12 conditional scope-check for an S10 novelty question.

This is a narrow pre-inquiry gate, NOT a permission to execute physical actions.
Never reads a hidden law, intervention, ground-truth score or receiver state.
Output floor and impact come from an openly supplied experiment contract.
"""
import hashlib
import json

from epistemic_gate import _common_safe  # reuse S11 decision-relative criterion


def predict(model, u, context):
    b, a, q = model[:3]
    return b + a*u + q*u*context + (model[3]*u**model[4]*context**model[5] if len(model)==6 else 0)


def assess(pre_snapshot, question, *, output_floor=10, ignore_scope=False):
    """Pure decision on public/agent-view state and S10 event question only.

    No reference to host config['law'], world receipts, changes or physical outcomes.
    `ignore_scope=True` is an explicitly unsafe *counterfactual* policy that
    must never trigger an actual receiver action.
    """
    if not isinstance(output_floor,(int,float)) or isinstance(output_floor,bool):
        raise ValueError('output_floor must be numeric')
    state=pre_snapshot['state']; config=pre_snapshot['config']
    selected=question['selected']
    ctx=selected['context']
    if not (state.get('verified') and state.get('pool') and selected.get('source')=='PUBLIC_CONTEXT_OBSERVATION'):
        return dict(decision='NO_SUPPORTED_QUESTION', context=ctx)
    if ctx in config['completed_contexts']:
        return dict(decision='ALREADY_COMPLETED',context=ctx)
    actions=list(state.get('actions',[]))
    if not actions or not all(type(u) is int for u in actions):
        return dict(decision='UNSUPPORTED_ACTION_LANGUAGE',context=ctx)
    models=[]
    for index,m in enumerate(state['pool']):
        models.append(dict(id=f'H{index+1}',actions={str(u):predict(m,u,ctx)-output_floor for u in actions},probes={}))
    common=_common_safe(models,sorted(models[0]['actions']),objective='safe')
    local_ok=bool(common)
    # Verification is required for a *new* context, even for one known model.
    decision=('SKIP_SCOPE_CHECK_ABLATION' if ignore_scope and local_ok else
              'VERIFY_NEW_SCOPE' if not ignore_scope else 'VERIFY_DECISION_CONFLICT')
    return dict(decision=decision, context=ctx,
                observed_event_id=selected['event_id'],
                question_origin=question['question_origin'],
                expected_action=common[0] if common else None,
                local_model_agreement=local_ok,
                scope_verified_here=False,
                model_count=len(models),
                model_digest=hashlib.sha256(json.dumps(state['pool'],sort_keys=True).encode()).hexdigest(),
                output_floor=output_floor,
                basis='current_verified_models_not_verified_in_new_context',
                stop_if_unverified=not ignore_scope)


def assess_after(completed_snapshot, context, *, output_floor=10):
    """Post-investigation: examine actual resulting agent state, no host truth."""
    state=completed_snapshot['state']; life=completed_snapshot['life'] or {}
    evidence=state.get('evidence',[])
    attested=(life.get('status')=='DONE' and state.get('context')==context and
              state.get('verified') and bool(evidence) and
              any('receiver_id' in e and 'operation_id' in e for e in evidence))
    if not attested:
        return {'decision':'SCOPE_NOT_ATTESTED','context':context,'evidence_count':len(evidence)}
    models=[{'id':f'H{i}', 'actions':{str(u):predict(m,u,context)-output_floor for u in state['actions']},'probes':{}}
            for i,m in enumerate(state['pool'])]
    common=_common_safe(models,sorted(models[0]['actions']),'safe') if models else []
    return {'decision':'LOCALLY_SUFFICIENT_FOR_THRESHOLD' if common else 'NO_COMMON_THRESHOLD_ACTION',
            'context':context,'expected_action':common[0] if common else None,
            'scope_attested':True,'evidence_count':len(evidence),'model_count':len(models)}
