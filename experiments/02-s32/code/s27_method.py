"""S27 bounded compositional inquiry: derive -> verify -> remember -> role-rebind.

World laws, source readings and physical samples are supplied only to a separate
host. Public schemas are an explicit finite typed operator language, not AGI.
"""
import hashlib,json,sqlite3,heapq

FACTS=('START','PRIMARY_OBSERVED','INDEPENDENT_OBSERVED','SOURCES_AGREE','REVISED_MODEL')

class StructuralLimit(Exception): pass

def canonical(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))

def _spec(op):
    if type(op.get('cost')) is not int or op['cost']<1:raise ValueError('invalid operation cost')
    if op.get('kind') not in ('MEASURE','COMPARE','MODEL'):raise ValueError('invalid operator kind')
    if not op.get('name') or not isinstance(op['name'],str):raise ValueError('operator name')
    req=tuple(op.get('requires',[])); add=tuple(op.get('adds',[]))
    if len(set(req))!=len(req) or len(set(add))!=len(add) or not add or not set(req+add)<=set(FACTS):raise ValueError('bad typed facts')
    if op['kind']=='MEASURE' and (op.get('role') is None or op.get('quantity') is None or op.get('root') is None):raise ValueError('missing measurement metadata')
    return (op['kind'],req,add)

def candidates(ops):
    ids=[x['name'] for x in ops]
    if len(set(ids))!=len(ids):raise ValueError('duplicate op names')
    for x in ops:_spec(x)
    return sorted(ops,key=lambda x:x['name'])

def structurally_applicable(op, observations, *, phase):
    if op['kind']!='MEASURE':return True
    # At planning time compare roles and declared measurement provenance,
    # never the host-private measurements themselves.
    if phase=='INDEPENDENT_OBSERVED':
        first=next((x for x in observations if x.get('type')=='primary'),None)
        return first is not None and first['quantity']==op['quantity'] and first['root']!=op['root']
    return True

def find_plan(ops,*,start=('START',),goal='REVISED_MODEL',budget=30,max_nodes=1000):
    """Dijkstra over typed fact sets. Independent-root condition checked by state."""
    ops=candidates(ops)
    if type(budget) is not int or budget<0:raise ValueError('invalid budget')
    initial=(frozenset(start),None,None,None) # facts, primary (root,quantity), independent root, first role
    q=[(0,0,(),initial)]; best={initial:0}; examined=0
    while q:
        cost,steps,names,state=heapq.heappop(q)
        if cost!=best.get(state):continue
        examined+=1
        if examined>max_nodes:raise StructuralLimit('search node cap')
        facts,primary,independent,first_role=state
        if goal in facts:return {'names':list(names),'cost':cost,'examined':examined}
        for op in ops:
            req=set(op['requires']); adds=set(op['adds'])
            if not req.issubset(facts) or adds.issubset(facts) or cost+op['cost']>budget:continue
            prim,other,first=primary,independent,first_role
            if op['kind']=='MEASURE':
                if 'PRIMARY_OBSERVED' in adds:
                    prim=(op['root'],op['quantity']);first=op['role']
                if 'INDEPENDENT_OBSERVED' in adds:
                    if prim is None or op['quantity']!=prim[1] or op['root']==prim[0] or op['role']==first:continue
                    other=op['root']
            elif op['kind'] in ('COMPARE','MODEL'):
                if 'SOURCES_AGREE' in adds and (prim is None or other is None):continue
            following=(frozenset(facts|adds),prim,other,first)
            newcost=cost+op['cost']
            if newcost<best.get(following,float('inf')):
                best[following]=newcost
                heapq.heappush(q,(newcost,steps+1,names+(op['name'],),following))
    return None

def signature(op):
    # Roles are generalized; public causal preconditions/effects remain binding.
    return {'kind':op['kind'],'requires':sorted(op['requires']),'adds':sorted(op['adds'])}

def bind_macro(signatures,ops,budget):
    """Rebind operator names via public type/effects; do not relax root checks."""
    available=candidates(ops); chosen=[]; used=set();facts={'START'};primary=None;cost=0
    for sig in signatures:
        options=[]
        for op in available:
            if op['name'] in used or signature(op)!=sig or not set(op['requires']).issubset(facts):continue
            if op['kind']=='MEASURE' and 'INDEPENDENT_OBSERVED' in op['adds']:
                if primary is None or primary[0]==op['root'] or primary[1]!=op['quantity'] or primary[2]==op['role']:continue
            options.append(op)
        if not options:return None
        op=min(options,key=lambda x:(x['cost'],x['name']))
        cost+=op['cost']
        if cost>budget:return None
        used.add(op['name']);chosen.append(op['name']);facts.update(op['adds'])
        if op['kind']=='MEASURE' and 'PRIMARY_OBSERVED' in op['adds']:
            primary=(op['root'],op['quantity'],op['role'])
    if 'REVISED_MODEL' not in facts:return None
    return {'names':chosen,'cost':cost,'examined':len(chosen)}

class MethodMemory:
    def __init__(self,conn):
        self.db=conn
        self.db.execute('CREATE TABLE IF NOT EXISTS s27_methods (id TEXT PRIMARY KEY, source TEXT, method TEXT, valid INTEGER, evidence TEXT)')
        self.db.execute('CREATE TABLE IF NOT EXISTS s27_runs (id TEXT PRIMARY KEY, contract TEXT, outcome TEXT, record TEXT)')
    def learn(self,source,ops,trace,evidence):
        if not trace or not evidence or evidence.get('status')!='VERIFIED':raise ValueError('unverified result cannot train method')
        mapping={x['name']:x for x in ops}
        seq=[signature(mapping[n]) for n in trace]
        ident=hashlib.sha256(canonical(seq).encode()).hexdigest()[:16]
        prev=self.db.execute('SELECT method,valid FROM s27_methods WHERE id=?',(ident,)).fetchone()
        if prev and prev[0]!=canonical(seq):raise ValueError('method hash collision')
        if prev is None:
            with self.db:self.db.execute('INSERT INTO s27_methods VALUES(?,?,?,?,?)',(ident,source,canonical(seq),1,canonical(evidence)))
        elif prev[1]==0:
            # A method may be re-learned only from a new successful trajectory.
            with self.db:self.db.execute('UPDATE s27_methods SET source=?,valid=1,evidence=? WHERE id=?',
                                          (source,canonical(evidence),ident))
        return ident
    def transfer(self,ops,budget):
        for ident,source,body in self.db.execute('SELECT id,source,method FROM s27_methods WHERE valid=1 ORDER BY id'):
            plan=bind_macro(json.loads(body),ops,budget)
            if plan:return dict(plan,source='LEARNED_TRANSFER',method_id=ident,from_case=source)
        return None
    def revoke(self,id):
        with self.db:self.db.execute('UPDATE s27_methods SET valid=0 WHERE id=?',(id,))
    def count(self):return self.db.execute('SELECT COUNT(*) FROM s27_methods WHERE valid=1').fetchone()[0]
