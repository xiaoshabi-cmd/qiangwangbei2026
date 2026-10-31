#!/usr/bin/env python3
"""Final readable decompilation of crp.v primitives into RTL-like equations."""
import re
import sys
import collections
sys.path.insert(0, '/home/xiaoshabi/lessons/ctf/qwb/crp-11741_bc69f9111bd2916dbcfd027469492846/work')
from netlist import parse_verilog, const_val

cells, assigns = parse_verilog('/home/xiaoshabi/lessons/ctf/qwb/crp-11741_bc69f9111bd2916dbcfd027469492846/work/crp.v')

# expand CARRY4 buses into per-bit ports
for c in cells:
    if c.ctype == 'CARRY4':
        for bus in ('S', 'DI', 'O', 'CO'):
            v = c.conns.get(bus)
            if v:
                parts = v.strip().strip('{}').split(',')
                for k, part in enumerate(parts):
                    c.conns['%s%d' % (bus, k)] = part.strip()

# ---- naming ----
def reg_of(net):
    """map slice nets to readable unique names"""
    net = net.strip()
    m = re.match(r'(CLBL[LM]_[LR])_X(\d+)Y(\d+)_SLICE_X(\d+)Y(\d+)_(\w)(5?)Q$', net)
    if m:
        # register: tile Y, site letter, site x
        return 'Q%s%s%s' % (m.group(3), m.group(6), m.group(4))
    return None

def srl_bits(net):
    m = re.match(r'(CLBL[LM]_[LR])_X(\d+)Y(\d+)_SLICE_X(\d+)Y(\d+)_(\w)(\d?)SRL\.r\[(\d+)\]$', net)
    if m:
        return 'S%s%s%s%s[%s]' % (m.group(3), m.group(6), m.group(5), m.group(2), m.group(8))
    return None

def cname(net):
    net = net.strip()
    r = reg_of(net)
    if r: return r
    s = srl_bits(net)
    if s: return s
    if 'IOB_X0Y13_I' in net: return 'RX'
    if net.startswith('RIOB33'): return 'CLK'
    if 'OPAD' in net: return 'TX'
    m = re.match(r'.*_CARRY4_X(\d+)Y(\d+)_COUT$', net)
    if m: return 'COUT.%dY%s' % (m.group(1), m.group(2))
    m = re.match(r'(CLBL[LM]_[LR])_X(\d+)Y(\d+)_SLICE_X(\d+)Y(\d+)_(\w+?)(\d?)$', net)
    if m:
        return 'W%s%s%s%s_%s' % (m.group(3), m.group(6), m.group(4), m.group(7), m.group(2))
    return net[-34:]

# driver map: net -> (cell, outport)
drv = {}
for c in cells:
    for port in ('O5', 'O6', 'O', 'Q', 'Q15', 'CO', 'CO0', 'CO1', 'CO2', 'CO3', 'O0', 'O1', 'O2', 'O3'):
        v = c.conns.get(port)
        if v and not v.startswith("1'"):
            # CO/O are 4-bit concat {D,C,B,A}; register bit names
            if port in ('CO', 'O'):
                for k, part in enumerate(v.strip('{}').split(',')):
                    pn = '%s%d' % (port, k)
                    if not part.strip().startswith("1'"):
                        drv[part.strip()] = (c, pn)
            else:
                drv[v] = (c, port)

CONST = {}
def const_of(net):
    net = net.strip()
    if net.startswith("1'"):
        try:
            return const_val(net)
        except Exception:
            return None
    return None

memo = {}
def E(net, depth=0, seen=frozenset()):
    net = (net or "1'b0").strip()
    cv = const_of(net)
    if cv is not None:
        return str(cv)
    if depth > 70:
        return '<deep:%s>' % cname(net)
    if net in seen:
        return '<fb:%s>' % cname(net)
    if net in memo:
        return memo[net]
    r = _drv_expr(net, depth, seen)
    if depth < 10 and len(r) < 140:
        memo[net] = r
    return r

def _drv_expr(net, depth, seen):
    d = drv.get(net)
    if d is None:
        n = assigns.get(net)
        if n is not None:
            return E(n, depth, seen)
        return cname(net)
    c, port = d
    t = c.ctype
    seen2 = seen | {net}
    if t == 'FDRE':
        return cname(c.conns['Q'])
    if t in ('SRL16E', 'SRLC16E'):
        if port == 'Q15':
            a = int(E(c.conns.get('A0', "1'b0"), depth + 1, seen2)) if c.conns.get('A0', "1'b0").startswith("1'") else None
            return '%s.shift[15]' % cname(c.conns['Q'])
        return '%s[%s]' % (cname(c.conns['Q']), addr_expr(c, depth + 1, seen2))
    if t == 'MUXF7':
        s = E(c.conns['S'], depth + 1, seen2)
        i0 = E(c.conns['I0'], depth + 1, seen2)
        i1 = E(c.conns['I1'], depth + 1, seen2)
        return '(%s ? %s : %s)' % (s, i1, i0)
    if t == 'CARRY4':
        k = int(port[2:]) if port.startswith('CO') else int(port[1:])
        s = E(c.conns['S%d' % k], depth + 1, seen2)
        if port.startswith('O'):
            ci = E('CO3_OF_%s' % id(c), depth, seen2) if False else carry_in(c, k, depth + 1, seen2)
            return '(%s ^ %s)' % (s, ci) if ci != '0' else s
        else:  # CO
            di = E(c.conns['DI%d' % k], depth + 1, seen2)
            ci = carry_in(c, k, depth + 1, seen2)
            if s == '1': return ci
            if s == '0': return di
            if di == s: return di
            return '(%s ? %s : %s)' % (s, ci, di)
    if t == 'LUT6_2':
        return lut_expr(c, port, depth, seen2)
    return '%s(%s)' % (t, cname(net))

def addr_expr(c, depth, seen):
    a = 0
    for k in range(4):
        v = c.conns.get('A%d' % k, "1'b0").strip()
        if v.startswith("1'"):
            a |= const_val(v) << k
        else:
            return E(v, depth, seen)
    return str(a)

def carry_in(c, k, depth, seen):
    if k > 0:
        return E('CO%d' % (k - 1) + '', depth, seen) if False else E(c.conns.get('DI%d' % (k - 1), "1'b0"), depth, seen) if False else _co_of(c, k - 1, depth, seen)
    # k == 0: CI or CYINIT
    ci = c.conns.get('CI', "1'b0").strip()
    cy = c.conns.get('CYINIT')
    if cy is not None and not cy.startswith("1'"):
        return E(cy, depth, seen)
    return E(ci, depth, seen)

def _co_of(c, k, depth, seen):
    net = c.conns['CO'].strip('{}').split(',')[k].strip()
    return E(net, depth, seen)

def lut_expr(c, port, depth, seen):
    init = const_val(c.params['INIT'])
    ins = [c.conns.get('I%d' % k, "1'b1") for k in range(6)]
    if port == 'O5':
        # O5 = INIT[I4..I0] (low 32)
        vals = [(init >> i) & 1 for i in range(32)]
        n = 5
    else:
        vals = [(init >> i) & 1 for i in range(64)]
        n = 6
    es = [E(x, depth + 1, seen) for x in ins[:n]]
    # constant-fold
    const_idx = [k for k, e in enumerate(es) if e in ('0', '1')]
    if const_idx:
        # evaluate all valuations consistent with consts
        fixed = {k: int(es[k]) for k in const_idx}
        var_idx = [k for k in range(n) if k not in const_idx]
        out_vals = {}
        for v in range(1 << len(var_idx)):
            idx = 0
            for kk, gi in enumerate(var_idx):
                idx |= ((v >> kk) & 1) << gi
            for gi, val in fixed.items():
                idx |= val << gi
            out_vals[v] = vals[idx] if port == 'O6' else vals[idx]
        vs = sorted(set(out_vals.values()))
        if len(vs) == 1:
            return str(vs[0])
        # rebuild es for vars only
        sub_es = [es[k] for k in var_idx]
        sub_vals = [vals]  # placeholder
        # build reduced truth table over var_idx (densely re-keyed)
        tt = {}
        for v, ov in out_vals.items():
            idx = 0
            for kk in range(len(var_idx)):
                idx |= ((v >> kk) & 1) << kk
            tt[idx] = ov
        return tt_to_expr(tt, var_idx, sub_es)
    tt = {i: vals[i] for i in range(len(vals))}
    var_idx = list(range(n))
    return tt_to_expr(tt, var_idx, es)

def tt_to_expr(tt, var_idx, es):
    nv = len(var_idx)
    if nv == 0:
        return '1' if tt.get(0) else '0'
    ones = [i for i in range(1 << nv) if tt[i]]
    if len(ones) == 0: return '0'
    if len(ones) == (1 << nv): return '1'
    # parity?
    def par(x): return bin(x).count('1') & 1
    if all(tt[i] == par(i) for i in range(1 << nv)) and nv >= 2:
        return '(' + ' ^ '.join(e for e in es) + ')'
    if all(tt[i] == (1 - par(i)) for i in range(1 << nv)) and nv >= 2:
        return '~(' + ' ^ '.join(e for e in es) + ')'
    # minimal DNF up to 4 vars: try single literal, AND of literals, XOR-with-const, mux forms
    if len(ones) == (1 << (nv - 1)):
        # depends on exactly? find the var: check if tt[i] = bit k of i
        for k in range(nv):
            if all(tt[i] == ((i >> k) & 1) for i in range(1 << nv)):
                return es[k]
            if all(tt[i] == 1 - ((i >> k) & 1) for i in range(1 << nv)):
                return '~' + es[k]
        # mux: tt[i] = i[m] ? f(i) : g(i) - check dependence on highest var as mux of lower vars
        m = nv - 1
        lo = {i: tt[i] for i in range(1 << nv)}
        f = {}; g = {}
        okf = okg = True
        for i in range(1 << nv):
            base = i & ~(1 << m)
            if (i >> m) & 1:
                if f.setdefault(base, tt[i]) != tt[i]: okf = False
            else:
                if g.setdefault(base, tt[i]) != tt[i]: okg = False
        if okf and okg:
            fe = tt_to_expr({i: f[i] for i in range(1 << (nv - 1))}, var_idx[:m], es[:m]) if nv > 1 else ('1' if f[0] else '0')
            ge = tt_to_expr({i: g[i] for i in range(1 << (nv - 1))}, var_idx[:m], es[:m]) if nv > 1 else ('1' if g[0] else '0')
            if fe == ge: return fe
            if fe == '1' and ge == '0': return es[m]
            if fe == '0' and ge == '1': return '~' + es[m]
            if fe == '1': return '(%s | %s)' % (es[m], ge)
            if fe == '0': return '(~%s & %s)' % (es[m], ge)
            if ge == '0': return '(%s & %s)' % (es[m], fe)
            if ge == '1': return '(~%s | %s)' % (es[m], fe)
            return '(%s ? %s : %s)' % (es[m], fe, ge)
    # general small DNF
    terms = []
    for o in ones:
        lits = []
        for k in range(nv):
            lits.append(es[k] if (o >> k) & 1 else '~' + es[k])
        terms.append('&'.join(lits) if lits else '1')
    if len(terms) <= 4:
        return '(' + ' | '.join(terms) + ')'
    return 'LUT%d(%s)' % (nv, ','.join(es))

# ---- output ----
out = open('/home/xiaoshabi/lessons/ctf/qwb/crp-11741_bc69f9111bd2916dbcfd027469492846/work/rtl.txt', 'w')
P = lambda *a: print(*a, file=out)

P('=== registers (FDRE) ===')
ffs = [c for c in cells if c.ctype == 'FDRE']
def ffname(c):
    return cname(c.conns['Q'])
ffs.sort(key=ffname)
for c in ffs:
    q = ffname(c)
    d = E(c.conns['D'])
    ce = E(c.conns.get('CE', "1'b1"))
    r = E(c.conns.get('R', "1'b0"))
    tag = '' if r == '0' else '  [R=%s]' % r
    P('%-14s <= %s' % (q, d))
    P('%-14s    CE: %s%s' % ('', ce, tag))
P()
P('=== SRLs ===')
for c in cells:
    if c.ctype in ('SRL16E', 'SRLC16E'):
        P('%-14s D=%s CE=%s  A=%s %s' % (cname(c.conns['Q']),
            E(c.conns['D']), E(c.conns['CE']), addr_expr(c, 0, frozenset()),
            'Q15=%s' % cname(c.conns['Q15']) if 'Q15' in c.conns else ''))
P()
P('=== CARRY4 chains ===')
for c in cells:
    if c.ctype == 'CARRY4':
        S = [E(c.conns['S%d' % k]) for k in range(4)]
        DI = [E(c.conns['DI%d' % k]) for k in range(4)]
        ci = c.conns.get('CI', "1'b0").strip()
        cy = c.conns.get('CYINIT', "1'b0").strip()
        P('%-40s CI=%s CYINIT=%s' % (c.name[-44:], ci[:12], cy[:20]))
        P('    S =%s' % S)
        P('    DI=%s' % DI)
P()
P('=== MUXF7 ===')
for c in cells:
    if c.ctype == 'MUXF7':
        P('%-14s = %s' % (cname(c.conns['O']), _drv_expr(c.conns['O'], 0, frozenset())))
P()
P('=== output net TX cone ===')
for c in cells:
    if c.ctype == 'OBUF':
        P('TX = %s' % E(c.conns['I']))
P('=== RX fanout (direct) ===')
RX = 'LIOB33_X0Y13_IOB_X0Y13_I'
for c in cells:
    for k in range(6):
        if (c.conns.get('I%d' % k) or '').strip() == RX and c.ctype == 'LUT6_2':
            ins = [(k, 'RX')] + [(kk, E(c.conns['I%d' % kk])) for kk in range(6) if kk != k]
            P('%s O6=%s O5=%s ins=%s' % (c.name[-40:], E(c.conns['O6'])[:60], E(c.conns['O5'])[:40], ins))
out.close()
print('wrote rtl.txt')
import subprocess
print(subprocess.run(['wc', '-l', '/home/xiaoshabi/lessons/ctf/qwb/crp-11741_bc69f9111bd2916dbcfd027469492846/work/rtl.txt'], capture_output=True, text=True).stdout)
