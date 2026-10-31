#!/usr/bin/env python3
"""Readable decompilation of gates.json with unique names, mux-tree collapse."""
import json
import re
import sys

D = json.load(open('/home/xiaoshabi/lessons/ctf/qwb/crp-11741_bc69f9111bd2916dbcfd027469492846/work/gates.json'))
TOP = D['modules']['top']
CELLS = {n: c for n, c in TOP['cells'].items() if c['type'] != '$scopeinfo'}

bitnames = {}
for nn, nd in TOP['netnames'].items():
    for i, b in enumerate(nd['bits']):
        if isinstance(b, int):
            bitnames.setdefault(b, []).append(nn if len(nd['bits']) == 1 else '%s[%d]' % (nn, i))

def regname(bit):
    ns = bitnames.get(bit, ['b%d' % bit])
    n = ns[0]
    # e.g. CLBLM_R_X3Y51_SLICE_X2Y51_AQ  or ..._A5Q
    m = re.search(r'(CLBL[LM]_[LR])_X(\d+)Y(\d+)_SLICE_X(\d+)Y(\d+)_(\w)(5?)Q$', n)
    if m:
        return '%s.%dY%d.s%s%s%s' % (m.group(1), int(m.group(2)), int(m.group(3)), m.group(6), m.group(4), m.group(5))
    m = re.search(r'(CLBL[LM]_[LR])_X(\d+)Y(\d+)_SLICE_X(\d+)Y(\d+)_(\w)(\d?)SRL\.r\[(\d+)\]$', n)
    if m:
        return '%s.%dY%d.s%s%s%s.SRL[%s]' % (m.group(1), int(m.group(2)), int(m.group(3)), m.group(6), m.group(4), m.group(5), m.group(7))
    return n[-45:]

drv = {}
for n, c in CELLS.items():
    for port in ('Y', 'Q'):
        if port in c['connections']:
            for b in c['connections'][port]:
                if isinstance(b, int):
                    drv.setdefault(b, (n, port))

memo = {}

def expr(b, depth=0, seen=frozenset()):
    if isinstance(b, str):
        return b
    if depth > 100:
        return '<deep:%s>' % regname(b)
    if b in seen:
        return '<fb:%s>' % regname(b)
    if b in memo:
        return memo[b]
    d = drv.get(b)
    if d is None:
        r = regname(b)
        memo[b] = r
        return r
    n, port = d
    c = CELLS[n]
    t = c['type']
    conn = c['connections']
    seen2 = seen | {b}
    if t in ('$dff', '$dffe'):
        r = regname(b)
    elif t == '$mux':
        s = expr(conn['S'][0], depth + 1, seen2)
        a = expr(conn['A'][0], depth + 1, seen2)
        bb = expr(conn['B'][0], depth + 1, seen2)
        r = a if a == bb else ('(%s ? %s : %s)' % (s, bb, a))
    elif t == '$xor':
        a = expr(conn['A'][0], depth + 1, seen2)
        bb = expr(conn['B'][0], depth + 1, seen2)
        r = a if a == '0' else (bb if bb == '0' else '(%s^%s)' % (a, bb))
    else:
        r = '?%s' % t
    if depth < 6 and len(r) < 150:
        memo[b] = r
    return r

regs = []
for n, c in CELLS.items():
    if c['type'] in ('$dff', '$dffe'):
        regs.append((regname(c['connections']['Q'][0]), n, c))
regs.sort()

out = open('/home/xiaoshabi/lessons/ctf/qwb/crp-11741_bc69f9111bd2916dbcfd027469492846/work/equations2.txt', 'w')
for name, n, c in regs:
    d = expr(c['connections']['D'][0])
    if c['type'] == '$dffe':
        ce = expr(c['connections']['EN'][0])
        print('%-34s <= %s\n%-34s    [CE: %s]' % (name, d, '', ce), file=out)
    else:
        print('%-34s <= %s   [always]' % (name, d), file=out)
out.close()
print('done')
