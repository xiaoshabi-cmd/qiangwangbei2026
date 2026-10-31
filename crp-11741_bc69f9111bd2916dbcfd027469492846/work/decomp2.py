#!/usr/bin/env python3
"""Decompile gates.json into readable per-register update equations."""
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

drv = {}   # bit -> (cellname, port)
for n, c in CELLS.items():
    for port in ('Y', 'Q'):
        if port in c['connections']:
            for b in c['connections'][port]:
                if isinstance(b, int):
                    drv.setdefault(b, (n, port))

def short(b):
    if isinstance(b, str):
        return b
    ns = bitnames.get(b)
    if not ns:
        return 'b%d' % b
    n = ns[0]
    m = re.search(r'SLICE_X\d+Y(\d+)_(\w)(\d?)$', n)
    if m:
        return 'r%s%s%s' % (m.group(1), m.group(2), m.group(3))
    m = re.search(r'SLICE_X\d+Y(\d+)_(\w)(\d?)_\d$', n)
    if m:
        return 'r%s%s%s' % (m.group(1), m.group(2), m.group(3))
    if 'IPAD' in n:
        if 'X0Y13' in n:
            return 'RX'
        return 'CLK'
    if 'OPAD' in n:
        return 'TX'
    return n[-30:]

dffout = {}  # bit -> reg name
for n, c in CELLS.items():
    if c['type'] in ('$dff', '$dffe'):
        for b in c['connections']['Q']:
            if isinstance(b, int):
                dffout[b] = short(b)

memo = {}
depth_lim = 80

def expr(b, depth=0, seen=frozenset()):
    if isinstance(b, str):
        return b if b in ('0', '1') else "x'" + b
    if depth > depth_lim:
        return '<deep>'
    if b in seen:
        return '<loop>' + short(b)
    if b in memo:
        return memo[b]
    d = drv.get(b)
    if d is None:
        r = short(b)
    else:
        n, port = d
        c = CELLS[n]
        t = c['type']
        conn = c['connections']
        seen2 = seen | {b}
        if t in ('$dff', '$dffe'):
            r = short(b)
        elif t == '$mux':
            s = expr(conn['S'][0], depth + 1, seen2)
            a = expr(conn['A'][0], depth + 1, seen2)
            bb = expr(conn['B'][0], depth + 1, seen2)
            if a == bb:
                r = a
            else:
                r = '(%s ? %s : %s)' % (s, bb, a)
        elif t == '$xor':
            a = expr(conn['A'][0], depth + 1, seen2)
            bb = expr(conn['B'][0], depth + 1, seen2)
            if a == '0': r = bb
            elif bb == '0': r = a
            elif a == '1': r = '(~' + bb + ')'
            elif bb == '1': r = '(~' + a + ')'
            else: r = '(%s ^ %s)' % (a, bb)
        elif t == '$and':
            a = expr(conn['A'][0], depth + 1, seen2)
            bb = expr(conn['B'][0], depth + 1, seen2)
            if a == '0' or bb == '0': r = '0'
            elif a == '1': r = bb
            elif bb == '1': r = a
            else: r = '(%s & %s)' % (a, bb)
        elif t == '$or':
            a = expr(conn['A'][0], depth + 1, seen2)
            bb = expr(conn['B'][0], depth + 1, seen2)
            if a == '1' or bb == '1': r = '1'
            elif a == '0': r = bb
            elif bb == '0': r = a
            else: r = '(%s | %s)' % (a, bb)
        elif t == '$not':
            a = expr(conn['A'][0], depth + 1, seen2)
            r = '~' + a if not a.startswith('~') else a[1:]
        elif t == '$_NOT_':
            r = '~' + expr(conn['A'][0], depth + 1, seen2)
        elif t.startswith('$_'):
            r = '%s(%s)' % (t, ','.join(expr(v[0], depth + 1, seen2) for k, v in conn.items() if k not in ('Y',)))
        else:
            r = '?%s' % t
    if depth < 12 and len(r) < 120:
        memo[b] = r
    return r

# order dffs by reg name
regs = []
for n, c in CELLS.items():
    if c['type'] in ('$dff', '$dffe'):
        q = c['connections']['Q'][0]
        regs.append((short(q), n, c))
regs.sort()

out = open('/home/xiaoshabi/lessons/ctf/qwb/crp-11741_bc69f9111bd2916dbcfd027469492846/work/equations.txt', 'w')
for name, n, c in regs:
    t = c['type']
    d = expr(c['connections']['D'][0])
    if t == '$dffe':
        ce = expr(c['connections']['EN'][0])
        line = '%-8s <= %s   [CE: %s]' % (name, d, ce)
    else:
        line = '%-8s <= %s   [always]' % (name, d)
    print(line, file=out)
out.close()
print('wrote equations.txt')
import subprocess
print(subprocess.run(['wc', '-l', '/home/xiaoshabi/lessons/ctf/qwb/crp-11741_bc69f9111bd2916dbcfd027469492846/work/equations.txt'], capture_output=True, text=True).stdout)
