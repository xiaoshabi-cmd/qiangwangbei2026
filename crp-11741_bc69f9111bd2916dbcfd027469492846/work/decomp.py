#!/usr/bin/env python3
"""Decompile the netlist into readable pseudo-RTL expressions."""
import re
import sys
sys.path.insert(0, '/home/xiaoshabi/lessons/ctf/qwb/crp-11741_bc69f9111bd2916dbcfd027469492846/work')
from netlist import parse_verilog, const_val

cells, assigns = parse_verilog('crp.v')

# net -> driver cell
drv = {}
for c in cells:
    for port in ('O', 'O5', 'O6', 'Q', 'Q15', 'CO', 'O2'):
        if port in c.conns and c.conns[port] and not c.conns[port].startswith("1'"):
            drv.setdefault(c.conns[port], []).append((port, c))

CLKS = {'RIOB33_X43Y25_IOB_X0Y26_I', 'RIOB33_X43Y25_IOB_X1Y26_I'}

def short(n):
    if n is None:
        return '?'
    n = n.strip()
    if n.startswith("1'"):
        return n
    m = re.search(r'CLBL[LM]_[LR]_X\d+Y\d+_SLICE_X\d+Y(\d+)_(\w)', n)
    if m:
        return 'r%s%s' % (m.group(1), m.group(2))
    m = re.search(r'_CARRY4_X\d+Y\d+_CO(\d)', n)
    if m:
        return 'co' + m.group(1)
    m = re.search(r'_CARRY4_X\d+Y\d+_O(\d)', n)
    if m:
        return 'cyo' + m.group(1)
    m = re.search(r'_CARRY4_X\d+Y\d+_CI$', n)
    if m:
        return 'ci?'
    m = re.search(r'CARRY4_X\d+Y\d+_O$', n)
    if m:
        return 'CY?'
    m = re.search(r'_MUXF7_X\d+Y\d+_O', n)
    if m:
        return 'mux7_' + n[-6:]
    if 'IOB' in n:
        if n in ('LIOB33_X0Y13_IOB_X0Y13_I',):
            return 'RX'
        if n.startswith('RIOB33'):
            return 'CLK'
        return 'PAD?' + n[-8:]
    return n

cache = {}

def expr(net, depth=0, seen=None):
    """Return readable boolean expr for net, or None."""
    if seen is None:
        seen = set()
    net = net.strip()
    if net.startswith("1'"):
        return net
    if net in seen:
        return '<loop:' + short(net) + '>'
    if depth > 60:
        return '<deep:' + short(net) + '>'
    key = (net, depth)
    if key in cache:
        return cache[key]
    seen = seen | {net}
    if net in assigns:
        r = expr(assigns[net], depth, seen)
        cache[key] = r
        return r
    ds = drv.get(net, [])
    if not ds:
        r = 'GND' if net.endswith('_GND') or 'GND' in net else ('VCC' if 'VCC' in net else short(net))
        cache[key] = r
        return r
    port, c = ds[0]
    t = c.ctype
    if t == 'IBUF' or t == 'BUFGCTRL':
        r = expr(c.conns['I'], depth + 1, seen) if t == 'IBUF' else expr(c.conns['I0'], depth + 1, seen)
        cache[key] = r
        return r
    if t == 'FDRE':
        r = short(net)  # state variable
        cache[key] = r
        return r
    if t in ('SRL16E', 'SRLC16E'):
        if port == 'Q15':
            r = 's%d[15]' % id(c)
        else:
            a = 0
            for k in range(4):
                e = expr(c.conns.get('A%d' % k, "1'b0"), depth + 1, seen)
                try:
                    a |= int(e) << k
                except Exception:
                    r = 'SRL?'
                    cache[key] = r
                    return r
            r = 'SRL%d[%d]' % (id(c) % 100, a)
        cache[key] = r
        return r
    if t == 'MUXF7':
        s = expr(c.conns['S'], depth + 1, seen)
        i0 = expr(c.conns['I0'], depth + 1, seen)
        i1 = expr(c.conns['I1'], depth + 1, seen)
        r = '(%s ? %s : %s)' % (s, i1, i0)
        cache[key] = r
        return r
    if t == 'CARRY4':
        if port == 'CO':
            idx = int(port[-1])
            # CO[i] = O[i] for chain; need DI/S of this carry
            di = c.conns.get('DI%d' % idx)
            s = c.conns.get('S%d' % idx)
            cie = expr(c.conns.get('CI', "1'b0"), depth + 1, seen)
            die = expr(di, depth + 1, seen) if di else None
            se = expr(s, depth + 1, seen) if s else None
            if die and se and die == se:
                r = '(~(%s) & %s)' % (die, cie)  # propagate: P&CI
            elif se:
                r = '(%s ^ %s ^ %s)' % (se, die or "1'b0", cie)
            else:
                r = 'co?'
        else:  # O port
            idx = int(port[1])
            s = c.conns.get('S%d' % idx)
            se = expr(s, depth + 1, seen) if s else None
            r = se if se else 'o?'
        cache[key] = r
        return r
    if t == 'LUT6_2':
        if port == 'O5':
            init = const_val(c.params.get('INIT_L', c.params.get('INIT', '0')))
            bits = [(init >> (i * 2)) & 1 for i in range(32)] + [(init >> (32 + i)) & 1 for i in range(32)]
            ins = [c.conns.get('I%d' % k, "1'b0") for k in range(5)]
        else:
            init = const_val(c.params.get('INIT', '0'))
            ins = [c.conns.get('I%d' % k, "1'b0") for k in range(6)]
            bits = [(init >> i) & 1 for i in range(64)]
        es = [expr(x, depth + 1, seen) for x in ins]
        # try to simplify
        terms_on = [i for i, b in enumerate(bits) if b]
        if len(terms_on) == 0:
            r = "1'b0"
        elif len(terms_on) == 64:
            r = "1'b1"
        else:
            # pattern: XOR of inputs (parity) => 32 on-bits with even parity structure
            def parity(x, n):
                return bin(x).count('1') & 1
            if all(bits[i] == parity(i, len(ins)) for i in range(len(bits))) and len(ins) >= 2:
                r = '(' + ' ^ '.join(e for e in es if e != "1'b0") + ')'
            else:
                # small function: try AND/ANDNOT of subset via brute force on inputs appearing
                var_idx = [k for k, e in enumerate(es) if e not in ("1'b0", "1'b1")]
                nv = len(var_idx)
                if nv <= 4:
                    # find minimal DNF
                    best = None
                    for mask in range(1 << (1 << nv)):
                        nb = bin(mask).count('1')
                        ok = True
                        for v in range(1 << nv):
                            # input line value: var k of v
                            line = 0
                            for kk, gi in enumerate(var_idx):
                                line |= ((v >> kk) & 1) << gi
                            if bool(mask & (1 << v)) != bool(bits[line]):
                                ok = False
                                break
                        if ok and (best is None or nb < best[0]):
                            best = (nb, mask)
                    if best:
                        nb, mask = best
                        if nb == 1:
                            v = mask.bit_length() - 1
                            line = 0
                            for kk, gi in enumerate(var_idx):
                                line |= ((v >> kk) & 1) << gi
                            # find exact assignment
                            want = [0] * 6
                            for gi in range(6):
                                want[gi] = (line >> gi) & 1
                            # express as and of literals
                            lits = []
                            for kk, gi in enumerate(var_idx):
                                lits.append(es[gi] if want[gi] else '~' + es[gi])
                            r = '&'.join(lits) if lits else "1'b1"
                        else:
                            r = 'LUT(%s)' % ','.join(e for e in es if e not in ("1'b0", "1'b1"))
                    else:
                        r = 'LUT(%s)' % ','.join(e for e in es if e not in ("1'b0", "1'b1"))
                else:
                    r = 'LUT(%s)' % ','.join(e for e in es if e not in ("1'b0", "1'b1"))
        cache[key] = r
        return r
    r = '%s?%s' % (t, short(net))
    cache[key] = r
    return r

def ffsr(c):
    m = re.search(r'SLICE_X\d+Y(\d+)_(\w)', c.conns['Q'])
    return 'r%s%s' % (m.group(1), m.group(2))

print('=== FDRE list (sorted by slice) ===')
ffs = sorted((c for c in cells if c.ctype == 'FDRE'), key=ffsr)
for c in ffs:
    ce = expr(c.conns['CE'])
    d = expr(c.conns['D'])
    r = expr(c.conns['R'])
    print('%-8s R=%-6s CE=%-40s D=%s' % (ffsr(c), short(r), ce[:46], d[:110]))

print()
print('=== CARRY4 chains ===')
for c in sorted((c for c in cells if c.ctype == 'CARRY4'), key=lambda c: c.name):
    s = [expr(c.conns.get('S%d' % k, "1'b0"))[:18] for k in range(4)]
    di = [expr(c.conns.get('DI%d' % k, "1'b0"))[:18] for k in range(4)]
    print('%-40s S=%s DI=%s' % (short(c.name), s, di))
