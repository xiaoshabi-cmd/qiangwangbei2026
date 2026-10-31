#!/usr/bin/env python3
"""Simulate a yosys JSON (flat or gates) with stimulus from argv; print output bitstream."""
import json
import sys

path = sys.argv[1] if len(sys.argv) > 1 else 'flat.json'
D = json.load(open(path))
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

def getval(v):
    out = 0
    for i, b in enumerate(v):
        if isinstance(b, str):
            out |= (1 if b == '1' else 0) << i
        else:
            out |= vals.get(b, 0) << i
    return out

dffs = [(n, c) for n, c in CELLS.items() if c['type'] in ('$dff', '$dffe')]
comb = [n for n, c in CELLS.items() if c['type'] not in ('$dff', '$dffe')]

# topo order
outbits = {}
for n, c in CELLS.items():
    if c['type'] in ('$dff', '$dffe'):
        continue
    for b in (c['connections'].get('Y') or []):
        if isinstance(b, int):
            outbits.setdefault(b, []).append(n)
deps = {}
for n, c in CELLS.items():
    if c['type'] in ('$dff', '$dffe'):
        continue
    dep = set()
    for port, bits in c['connections'].items():
        if port == 'Y':
            continue
        for b in bits:
            if isinstance(b, int) and b in outbits:
                dep.update(outbits[b])
    deps[n] = dep - {n}
done = set()
pending = dict(deps)
order = []
while pending:
    ready = [n for n, d in pending.items() if d <= done] or [next(iter(pending))]
    for n in ready:
        order.append(n)
        done.add(n)
        del pending[n]

def ports():
    return TOP['ports']

PORTS = ports()
DIN = [p for p in PORTS if 'X0Y13' in p][0]
CLK = [p for p in PORTS if 'IPAD' in p and 'X0Y13' not in p][0]
OUTP = [p for p in PORTS if 'OPAD' in p][0]

def set_port(p, v):
    for i, b in enumerate(PORTS[p]['bits']):
        if isinstance(b, int):
            vals[b] = (v >> i) & 1

def comb_eval():
    for n in order:
        c = CELLS[n]
        t = c['type']
        conn = c['connections']
        if t == '$mux':
            y = getval(conn['B']) if getval(conn['S']) else getval(conn['A'])
        elif t == '$xor':
            y = getval(conn['A']) ^ getval(conn['B'])
        elif t == '$and':
            y = getval(conn['A']) & getval(conn['B'])
        elif t == '$or':
            y = getval(conn['A']) | getval(conn['B'])
        elif t == '$not':
            y = getval(conn['A']) ^ ((1 << len(conn['Y'])) - 1)
        elif t == '$shiftx':
            y = (getval(conn['A']) >> getval(conn['B'])) & ((1 << len(conn['Y'])) - 1)
        elif t == '$_NOT_':
            y = getval(conn['A']) ^ 1
        elif t == '$_MUX_':
            y = getval(conn['B']) if getval(conn['S']) else getval(conn['A'])
        else:
            raise Exception('unknown %s %s' % (t, n))
        for i, b in enumerate(conn['Y']):
            if isinstance(b, int):
                vals[b] = (y >> i) & 1

def outport():
    v = 0
    for i, b in enumerate(PORTS[OUTP]['bits']):
        if isinstance(b, int):
            v |= vals.get(b, 0) << i
    return v

def tick(din):
    vals.clear()
    vals.update(state)
    set_port(DIN, din)
    set_port(CLK, 0)
    comb_eval()
    out = outport()
    # rising edge
    set_port(CLK, 1)
    comb_eval()
    new = {}
    for n, c in dffs:
        en = True
        if c['type'] == '$dffe':
            en = bool(getval(c['connections']['EN']))
        if en:
            d = getval(c['connections']['D'])
            for i, b in enumerate(c['connections']['Q']):
                if isinstance(b, int):
                    new[b] = (d >> i) & 1
    state.update(new)
    return out

if __name__ == '__main__':
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 3000
    mode = sys.argv[3] if len(sys.argv) > 3 else 'press'
    outs = []
    for k in range(n):
        din = 1 if k >= 1000 else 0
        outs.append(tick(din))
    z = [i for i, b in enumerate(outs) if b == 0]
    print(path, 'zeros', len(z), 'first', z[:25])
    print(''.join(map(str, outs[1850:2100])))
