#!/usr/bin/env python3
"""Full readable dump of the design: FFs grouped, CARRY4 chains, SRLs, output path.
Uses gates.json (yosys-folded, faithful)."""
import json
import re
import collections

D = json.load(open('/home/xiaoshabi/lessons/ctf/qwb/crp-11741_bc69f9111bd2916dbcfd027469492846/work/gates.json'))
TOP = D['modules']['top']
CELLS = {n: c for n, c in TOP['cells'].items() if c['type'] != '$scopeinfo'}

bitnames = {}
for nn, nd in TOP['netnames'].items():
    for i, b in enumerate(nd['bits']):
        if isinstance(b, int):
            bitnames.setdefault(b, []).append(nn if len(nd['bits']) == 1 else '%s[%d]' % (nn, i))

drv = {}
for n, c in CELLS.items():
    for port in ('Y', 'Q'):
        if port in c['connections']:
            for b in c['connections'][port]:
                if isinstance(b, int):
                    drv.setdefault(b, (n, port))

PORTS = TOP['ports']
def portname(bit):
    for p, nd in PORTS.items():
        if bit in nd['bits']:
            if 'X0Y13' in p: return 'RX'
            if 'IPAD' in p: return 'CLK'
            return 'TX'
    return None

def nname(b):
    """clean unique name for a net"""
    if isinstance(b, str): return b
    pn = portname(b)
    if pn: return pn
    ns = bitnames.get(b)
    if not ns: return 'b%d' % b
    n = ns[0]
    # slice register output
    m = re.match(r'(CLBL[LM]_[LR])_X(\d+)Y(\d+)_SLICE_X(\d+)Y(\d+)_(\w)(5?)Q$', n)
    if m:
        return 'r%s%s%s%s%s' % (m.group(2), m.group(3), m.group(4), m.group(6), m.group(5))
    # SRL internal bit
    m = re.match(r'(CLBL[LM]_[LR])_X(\d+)Y(\d+)_SLICE_X(\d+)Y(\d+)_(\w)(\d?)SRL\.r\[(\d+)\]$', n)
    if m:
        return 's%s%s%s%s%s[%s]' % (m.group(2), m.group(3), m.group(4), m.group(6), m.group(5), m.group(7))
    # carry nets
    m = re.match(r'.*_CARRY4_X(\d+)Y(\d+)_(CO|O|COUT|CYINIT|CI)(\d?)$', n)
    if m:
        return 'cy%s_%s%s_Y%s' % (m.group(2), m.group(1), m.group(3), m.group(2))
    # slice X muxes / outputs
    m = re.match(r'(CLBL[LM]_[LR])_X(\d+)Y(\d+)_SLICE_X(\d+)Y(\d+)_(\w+?)(\d?)$', n)
    if m:
        return 'w%s%s%s%s%s_%s' % (m.group(2), m.group(3), m.group(4), m.group(5), m.group(6), m.group(7))
    return n[-38:]

# dff/srl recognition: $dffe with WIDTH 16 whose D = shift of Q = SRL
srls = {}
for n, c in CELLS.items():
    if c['type'] == '$dffe' and int(c['parameters']['WIDTH']) == 16:
        # check D = {Q[14:0], x}
        qb = c['connections']['Q']; db = c['connections']['D']
        if db[1:] == qb[:-1]:
            srls[n] = c

def is_srl_out(b):
    for n, c in srls.items():
        if b in c['connections']['Q']: return n
    return None

memo = {}
def expr(b, depth=0, seen=frozenset()):
    if isinstance(b, str): return b
    if depth > 90: return '<deep:%s>' % nname(b)
    if b in seen: return '<fb:%s>' % nname(b)
    if b in memo: return memo[b]
    sn = is_srl_out(b)
    if sn:
        r = 'SRL(%s)' % nname(b)
        memo[b] = r
        return r
    d = drv.get(b)
    if d is None:
        r = nname(b)
        memo[b] = r
        return r
    n, port = d
    c = CELLS[n]
    t = c['type']; conn = c['connections']
    seen2 = seen | {b}
    if t in ('$dff', '$dffe'):
        r = nname(b)
    elif t == '$mux':
        s = expr(conn['S'][0], depth + 1, seen2)
        a = expr(conn['A'][0], depth + 1, seen2)
        bb = expr(conn['B'][0], depth + 1, seen2)
        r = a if a == bb else ('%s ? %s : %s' % (s, bb, a))
    elif t == '$xor':
        a = expr(conn['A'][0], depth + 1, seen2)
        bb = expr(conn['B'][0], depth + 1, seen2)
        r = a if a == '0' else (bb if bb == '0' else '(%s^%s)' % (a, bb))
    else:
        r = '?%s' % t
    if depth < 8 and len(r) < 160: memo[b] = r
    return r

out = open('/home/xiaoshabi/lessons/ctf/qwb/crp-11741_bc69f9111bd2916dbcfd027469492846/work/design_dump.txt', 'w')
P = print
# 1. SRL list
P('=== SRLs (16-bit shift regs) ===')
for n, c in sorted(srls.items()):
    d0 = nname(c['connections']['D'][0])
    en = expr(c['connections']['EN'][0])
    # address: find shiftx reading this srl
    P('%-40s D=%-30s CE=%s' % (nname(c['connections']['Q'][0])[:40], d0, en))
P()
# 2. FF equations
P('=== FFs ===')
ffs = []
for n, c in CELLS.items():
    if c['type'] in ('$dff', '$dffe') and n not in srls:
        ffs.append((nname(c['connections']['Q'][0]), n, c))
ffs.sort()
for name, n, c in ffs:
    d = expr(c['connections']['D'][0])
    if c['type'] == '$dffe':
        ce = expr(c['connections']['EN'][0])
        P('%-24s <= %s\n%-24s    [CE: %s]' % (name, d, '', ce))
    else:
        P('%-24s <= %s  [always]' % (name, d))
P()
# 3. CARRY4 info: find in flat.json? use gates.json cells named CARRY4? They were flattened.
# Instead: scan crp.v directly in separate script.
out.close()
print('wrote design_dump.txt')
