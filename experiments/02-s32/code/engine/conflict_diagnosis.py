"""Finite diagnostic hypotheses; no universal attribution or memory reset.

Assume a trusted calibration standard: CAL has true response zero.
Hypotheses describe a stable process gain and a constant additive sensor bias.
Joint changes are retained, so process/sensor explanations are not exclusive.
"""
from itertools import product

HYPOTHESES=tuple(product((1,2,3),(-1,0,1)))
PROBES=('CAL','U1','U2')

def predicted(model,probe):
    gain,bias=model
    return bias if probe=='CAL' else gain*int(probe[1:])+bias

def explain(model):
    gain,bias=model
    if gain!=1 and bias!=0: return 'JOINT_CHANGE'
    if gain!=1: return 'PROCESS_CHANGE'
    if bias!=0: return 'SENSOR_BIAS'
    return 'UNCHANGED'

class Diagnosis:
    def __init__(self,budget=2,probes=PROBES):
        if type(budget) is not int or budget<0 or any(p not in PROBES for p in probes):
            raise ValueError('invalid diagnostic contract')
        self.budget=budget
        self.probes=tuple(probes)
        self.models=HYPOTHESES
        self.evidence=[]
        self.pending=None

    def observe(self,probe,value):
        if probe not in PROBES: raise ValueError('invalid measurement')
        if self.pending is not None and probe!=self.pending: raise ValueError('unexpected measurement')
        self.models=tuple(m for m in self.models if predicted(m,probe)==value)
        self.evidence.append({'probe':probe,'value':value,'remaining':self.models})
        self.pending=None

    def status(self):
        if not self.models: return 'UNEXPLAINED_BY_CLASS'
        if len(self.models)==1: return explain(self.models[0])
        return 'AMBIGUOUS'

    def next_probe(self):
        if self.pending is not None: raise RuntimeError('awaiting measurement')
        if not self.models or self.budget==0: return None
        if len(self.models)==1:
            # Identification within a class is not validation of that class.
            # Spend remaining budget on an unused intervention before stopping.
            seen={e['probe'] for e in self.evidence}
            unused=[p for p in self.probes if p not in seen]
            if not unused: return None
            self.pending=unused[-1]
            self.budget-=1
            return self.pending
        # Distinct predictions; tie uses a fixed public probe order.
        ranked=[(len({predicted(m,p) for m in self.models}),-i,p) for i,p in enumerate(self.probes)]
        if not ranked or max(ranked)[0]<2: return None
        self.pending=max(ranked)[2]
        self.budget-=1
        return self.pending

def diagnose(sensor,budget=2,probes=PROBES):
    d=Diagnosis(budget,probes)
    d.observe('U1',sensor('U1')) # previously observed contradiction, no extra cost
    used=0
    while (p:=d.next_probe()) is not None:
        used+=1
        d.observe(p,sensor(p))
    return {'status':d.status(),'candidates':d.models,'extra_measurements':used,
            'evidence':d.evidence,'assumption':'trusted CAL, stable integer gain and constant bias'}
