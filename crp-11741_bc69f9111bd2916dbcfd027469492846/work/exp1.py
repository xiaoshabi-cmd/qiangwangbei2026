#!/usr/bin/env python3
"""Experiment: feed UART bytes to the FIXED netlist, observe TX."""
import sys
sys.path.insert(0, '/home/xiaoshabi/lessons/ctf/qwb/crp-11741_bc69f9111bd2916dbcfd027469492846/work')
import json

D = json.load(open('/home/xiaoshabi/lessons/ctf/qwb/crp-11741_bc69f9111bd2916dbcfd027469492846/work/gates_fixed.json'))
TOP = D['modules']['top']
CELLS = {n: c for n, c in TOP['cells'].items() if c['type'] != '$scopeinfo'}

drv = {}
for n, c in CELLS.items():
    for port in ('Y', 'Q'):
        if port in c['connections']:
            for b in c['connections'][port]:
                if isinstance(b, int):
                    drv.setdefault(b, (n, port))

state = {}
vals = {}
GLOBAL_STATE = state
GLOBAL_VALS = vals

def getval(v):
    out = 0
    for i, b in enumerate(v):
        if isinstance(b, str):
            out |= (1 if b == '1' else 0) << i
        else:
            out |= vals.get(b, 0) << i
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
        if t == '$mux':
            y = getval(conn['B']) if getval(conn['S']) else getval(conn['A'])
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

def uart_bits(bytes_, div, idle=40):
    """return list of (cycle, rxbit) or a generator function"""
    bits = [1] * (idle * div)
    for byt in bytes_:
        bits += [0] * div
        for k in range(8):
            bits += [(byt >> k) & 1] * div
        bits += [1] * div
    bits += [1] * (idle * div)
    return bits

if __name__ == '__main__':
    div = int(sys.argv[1]) if len(sys.argv) > 1 else 868
    msg = sys.argv[2].encode() if len(sys.argv) > 2 else b'U'
    bits = uart_bits(msg, div)
    outs = []
    for k, b in enumerate(bits):
        outs.append(tick(b))
    tx = ''.join(str(o) for o in outs)
    # find changes in TX vs input echo: compare TX with RX delayed
    print('cycles', len(outs), 'tx zeros', tx.count('0'))
    # print tx as timeline chunks
    # locate start bits in tx after idle
    print(tx[:400])
