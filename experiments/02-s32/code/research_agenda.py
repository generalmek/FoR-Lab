"""Bounded autonomous coverage inquiry. Domain/priority are supplied, not learned values."""
def propose(state, completed_contexts, allowed_contexts=(1,2,3)):
    models=state.get('pool',[])
    if not models or not state.get('verified'):
        return None
    options=[]
    for context in allowed_contexts:
        if context in completed_contexts:continue
        predictions={}
        for u in state['actions']:
            values=[]
            for m in models:
                b,a,q=m[:3]
                values.append(b+a*u+q*u*context+(m[3]*u**m[4]*context**m[5] if len(m)==6 else 0))
            predictions[str(u)]=sorted(set(values))
        ambiguity=max(len(v) for v in predictions.values())
        options.append(dict(context=context,predictions=predictions,ambiguity=ambiguity,
            reason='unverified-context-transfer',question=f'Do acquired process predictions hold in context {context}?'))
    if not options:return None
    selected=min(options,key=lambda o:(-o['ambiguity'],o['context']))
    return dict(selected=selected,alternatives=options,
        rule='largest prediction disagreement, then lowest untested context; finite supplied domain',
        source_task=state['task_id'],source_models=models)
