#!/usr/bin/env python3
"""Instrumented simulation of the FIXED design: watch R1/R2/R3 machines during UART input."""
import sys, json, re
sys.path.insert(0, '/home/xiaoshabi/lessons/ctf/qwb/crp-11741_bc69f9111bd2916dbcfd027469492846/work')

D = json.load(open('/home/xiaoshabi/lessons/ctf/qwb/crp-11741_bc69f9111bd2916dbcfd027469492846/work/gates_fixed.json'))
TOP = D['modules']['top']
CELLS = {n: c for n, c in TOP['cells'].items() if c['type'] != '$scopeinfo'}

bitnames = {}
for nn, nd in TOP['netnames'].items():
    for i, b in enumerate(nd['bits']):
        if isinstance(b, int):
            bitnames.setdefault(b, []).append(nn if len(nd['bits']) == 1 else '%s[%d]' % (nn, i))

def qname(bit):
    ns = bitnames.get(bit)
    if not ns: return None
    m = re.match(r'CLBL[LM]_[LR]_X\d+Y(\d+)_SLICE_X(\d+)Y\d+_(\w)(\d?)Q$', ns[0])
    if m: return 'Q%s%s%s' % (m.group(1), m.group(3), m.group(2))
    return None

# map FF Q bit -> name
qmap = {}
for n, c in CELLS.items():
    if c['type'] in ('$dff', '$dffe'):
        for i, b in enumerate(c['connections']['Q']):
            if isinstance(b, int) and len(c['connections']['Q']) == 1:
                qm = qname(b)
                if qm: qmap[b] = qm

drv = {}
for n, c in CELLS.items():
    for port in ('Y', 'Q'):
        if port in c['connections']:
            for b in c['connections'][port]:
                if isinstance(b, int): drv.setdefault(b, (n, port))

state = {}; vals = {}

def getval(v):
    out = 0
    for i, b in enumerate(v):
        if isinstance(b, str): out |= (1 if b == '1' else 0) << i
        else: out |= vals.get(b, 0) << i
    return out

dffs = [(n, c) for n, c in CELLS.items() if c['type'] in ('$dff', '$dffe')]
outbits = {}
for n, c in CELLS.items():
    if c['type'] in ('$dff', '$dffe'): continue
    for b in (c['connections'].get('Y') or []):
        if isinstance(b, int): outbits.setdefault(b, []).append(n)
deps = {}
for n, c in CELLS.items():
    if c['type'] in ('$dff', '$dffe'): continue
    dep = set()
    for port, bits in c['connections'].items():
        if port == 'Y': continue
        for b in bits:
            if isinstance(b, int) and b in outbits: dep.update(outbits[b])
    deps[n] = dep - {n}
done = set(); pending = dict(deps); order = []
while pending:
    ready = [n for n, d in pending.items() if d <= done] or [next(iter(pending))]
    for n in ready:
        order.append(n); done.add(n); del pending[n]

PORTS = TOP['ports']
DIN = [p for p in PORTS if 'X0Y13' in p][0]
CLK = [p for p in PORTS if 'IPAD' in p and 'X0Y13' not in p][0]
OUTP = [p for p in PORTS if 'OPAD' in p][0]

def set_port(p, v):
    for i, b in enumerate(PORTS[p]['bits']):
        if isinstance(b, int): vals[b] = (v >> i) & 1

def comb_eval():
    for n in order:
        c = CELLS[n]; t = c['type']; conn = c['connections']
        if t == '$mux': y = getval(conn['B']) if getval(conn['S']) else getval(conn['A'])
        elif t == '$xor': y = getval(conn['A']) ^ getval(conn['B'])
        elif t == '$and': y = getval(conn['A']) & getval(conn['B'])
        elif t == '$or': y = getval(conn['A']) | getval(conn['B'])
        elif t == '$not': y = getval(conn['A']) ^ ((1 << len(conn['Y'])) - 1)
        elif t == '$shiftx': y = (getval(conn['A']) >> getval(conn['B'])) & ((1 << len(conn['Y'])) - 1)
        elif t == '$_NOT_': y = getval(conn['A']) ^ 1
        elif t == '$_MUX_': y = getval(conn['B']) if getval(conn['S']) else getval(conn['A'])
        else: raise Exception('unknown %s' % t)
        for i, b in enumerate(conn['Y']):
            if isinstance(b, int): vals[b] = (y >> i) & 1

def outport():
    v = 0
    for i, b in enumerate(PORTS[OUTP]['bits']):
        if isinstance(b, int): v |= vals.get(b, 0) << i
    return v

def tick(din):
    vals.clear(); vals.update(state)
    set_port(DIN, din); set_port(CLK, 0)
    comb_eval()
    out = outport()
    set_port(CLK, 1); comb_eval()
    new = {}
    for n, c in dffs:
        en = True
        if c['type'] == '$dffe': en = bool(getval(c['connections']['EN']))
        if en:
            d = getval(c['connections']['D'])
            for i, b in enumerate(c['connections']['Q']):
                if isinstance(b, int): new[b] = (d >> i) & 1
    state.update(new)
    return out

def read_regs(names):
    res = {}
    inv = {}
    for b, q in qmap.items(): inv.setdefault(q, b)
    for q in names:
        b = inv.get(q)
        res[q] = state.get(b, 0) if b is not None else None
    return res

def uart_bits(bytes_, div, idle=1000):
    bits = [1] * idle
    for byt in bytes_:
        bits += [0] * div
        for k in range(8): bits += [(byt >> k) & 1] * div
        bits += [1] * div
    bits += [1] * 3000
    return bits

if __name__ == '__main__':
    R1 = ['Q42C4','Q42B4','Q42A4','Q42A6','Q43C4','Q43A6','Q43B4','Q43A4','Q44C4','Q44B4','Q44A6','Q44A4',
          'Q45C4','Q45A6','Q45B4','Q45A4','Q46A6','Q46C4','Q46B4','Q46A4','Q47C4','Q47A6','Q47B4','Q47A4','Q48A4','Q48B4']
    div = int(sys.argv[1]) if len(sys.argv) > 1 else 868
    msg = sys.argv[2].encode('latin1') if len(sys.argv) > 2 else b'\x01\x23\x45\x67\x89\xab\xcd\xef'
    bits = uart_bits(msg, div)
    tx = []
    prev = None
    for k, b in enumerate(bits):
        o = tick(b)
        tx.append(o)
        if k % 4 == 0 or True:
            pass
    txs = ''.join(map(str, tx))
    # R1 value over time (sampled)
    print('TX edges:', [i for i in range(1, len(txs)) if txs[i] != txs[i-1]][:30])
    # watch R1 counter max value
    R1v = []
    state.clear()
    vals.clear()
    mx = 0; mxk = 0
    samples = []
    for k, b in enumerate(bits):
        tick(b)
        vals.clear(); vals.update(state)
        r1 = 0
        for i, q in enumerate(R1[:24]):
            bb = {q: None}
        # rebuild bit->q inverse
        pass
    # simpler: recompute with inverse map
    inv = {}
    for b, q in qmap.items(): inv[q] = b
    state.clear()
    for k, b in enumerate(bits):
        tick(b)
        v = 0
        for i, q in enumerate(R1):
            bb = inv.get(q)
            if bb is not None: v |= state.get(bb, 0) << i
        if v > mx: mx = v; mxk = k
        if k % 434 == 0: samples.append((k, v))
    print('R1 max:', mx, 'at k=', mxk)
    print('R1 samples (k % 434):', samples[:40])
