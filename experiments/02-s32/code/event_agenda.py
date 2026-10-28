"""S10 limited question formation from *observed public novelty*, not an allowed-context menu.
The context sensor and question grammar are developer supplied. No hidden world law accessed.
"""

def propose_from_observed_contexts(state, completed_contexts, public_events):
    if not state or not state.get('verified') or not state.get('pool'):
        return None
    completed=set(completed_contexts)
    seen=set()
    candidates=[]
    for observation in public_events:
        value=observation.get('context')
        if type(value) is not int or not 1<=value<=256 or value in completed or value in seen:
            continue
        seen.add(value)
        models=state['pool']
        preds={}
        for u in state['actions']:
            values=[]
            for m in models:
                b,a,q=m[:3]
                values.append(b+a*u+q*u*value+(m[3]*u**m[4]*value**m[5] if len(m)==6 else 0))
            preds[str(u)]=sorted(set(values))
        ambiguity=max(map(len,preds.values()),default=0)
        candidates.append(dict(context=value, predictions=preds,ambiguity=ambiguity,
              event_id=observation['id'],source='PUBLIC_CONTEXT_OBSERVATION',
              question=f'Does the learned process relation transfer to newly observed context {value}?',
              reason='new-observed-context-unverified-transfer'))
    if not candidates:return None
    selected=min(candidates,key=lambda x:(-x['ambiguity'],x['event_id']))
    return dict(selected=selected,alternatives=candidates,
       rule='require witnessed new context, prefer model disagreement then earliest event',
       source_task=state['task_id'],source_models=state['pool'],
       question_origin='observed_novelty_not_allowed_contexts')
