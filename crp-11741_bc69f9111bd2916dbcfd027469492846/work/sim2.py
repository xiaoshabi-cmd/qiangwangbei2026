#!/usr/bin/env python3
"""Generic cycle simulator driven by yosys flat.json."""
import json
import sys

D = json.load(open('/home/xiaoshabi/lessons/ctf/qwb/crp-11741_bc69f9111bd2916dbcfd027469492846/work/flat.json'))
TOP = D['modules']['top']
CELLS = {n: c for n, c in TOP['cells'].items() if c['type'] != '$scopeinfo'}

# bit id -> list of human names
bitnames = {}
for nn, nd in TOP['netnames'].items():
    for i, b in enumerate(nd['bits']):
        if isinstance(b, str):
            continue
        bitnames.setdefault(b, []).append(nn if len(nd['bits']) == 1 else '%s[%d]' % (nn, i))

def bname(b):
    if isinstance(b, str):
        return b
    ns = bitnames.get(b, [])
    return ns[0] if ns else 'bit%d' % b

def shorten(n):
    import re
    m = re.search(r'SLICE_X\d+Y(\d+)_(\w+?)(\d?)(?:_\d)?$', n)
    if m:
        return 'r%s%s%s' % (m.group(1), m.group(2), m.group(3))
    if 'IPAD' in n:
        return 'IN(%s)' % n[:12]
    if 'OPAD' in n or 'OPAD' in str(n):
        return 'OUT'
    return n[:40]

def getval(v, state):
    """evaluate a connection bit-vector (list) -> int (LSB first)"""
    out = 0
    for i, b in enumerate(v):
        if isinstance(b, str):
            bit = 1 if b == "1" else 0
        else:
            bit = state.get(b, 0)
        out |= bit << i
    return out

class Sim:
    def __init__(self):
        self.state = {}          # bitid -> 0/1 (dff outputs)
        self.vals = {}           # bitid -> value for current comb evaluation
        self.dffs = []           # (cellname, cell)
        self.comb = []           # topo-ordered cells
        self._build()

    def _build(self):
        # collect dffs and comb cells; determine clock nets
        clk_count = {}
        for n, c in CELLS.items():
            if c['type'] == '$dff':
                self.dffs.append((n, c))
                clk = c['connections']['CLK']
                for b in clk:
                    if isinstance(b, int):
                        clk_count[b] = clk_count.get(b, 0) + 1
        print('dff count', len(self.dffs), 'clock nets:', [(bname(k), v) for k, v in clk_count.items()])
        self.clk_bit = max(clk_count, key=clk_count.get) if clk_count else None
        # topo sort comb cells by dependency on other comb cells' outputs
        outbits = {}
        for n, c in CELLS.items():
            if c['type'] == '$dff':
                continue
            y = c['connections'].get('Y') or c['connections'].get('Q')
            for b in (y or []):
                if isinstance(b, int):
                    outbits.setdefault(b, []).append(n)
        # Kahn
        deps = {}
        for n, c in CELLS.items():
            if c['type'] == '$dff':
                continue
            dep = set()
            for port, bits in c['connections'].items():
                if port == 'Y':
                    continue
                for b in bits:
                    if isinstance(b, int) and b in outbits:
                        for dn in outbits[b]:
                            if dn != n:
                                dep.add(dn)
            deps[n] = dep
        done = set()
        pending = dict(deps)
        order = []
        while pending:
            ready = [n for n, d in pending.items() if d <= done]
            if not ready:
                # cycle: break arbitrarily
                ready = [next(iter(pending))]
            for n in ready:
                order.append(n)
                done.add(n)
                del pending[n]
        self.comb = order

    def inputs(self, names):
        """set input port values: names dict port->0/1"""
        for p, v in names.items():
            nd = TOP['ports'][p]
            for i, b in enumerate(nd['bits']):
                if isinstance(b, int):
                    self.vals[b] = (v >> i) & 1

    def comb_eval(self):
        # propagate input ports each cycle
        for n, c in CELLS.items():
            if c['type'] == '$dff':
                continue
        for n in self.comb:
            c = CELLS[n]
            t = c['type']
            conn = c['connections']
            p = c.get('parameters', {})
            if t == '$mux':
                s = getval(conn['S'], self.vals)
                y = getval(conn['B'], self.vals) if s else getval(conn['A'], self.vals)
            elif t in ('$and', '$or', '$xor', '$xnor'):
                a = getval(conn['A'], self.vals)
                b = getval(conn['B'], self.vals)
                if t == '$and': y = a & b
                elif t == '$or': y = a | b
                elif t == '$xor': y = a ^ b
                else: y = (a ^ b) ^ ((1 << len(conn['Y'])) - 1)
            elif t == '$not':
                y = getval(conn['A'], self.vals) ^ ((1 << len(conn['Y'])) - 1)
            elif t == '$shiftx':
                a = getval(conn['A'], self.vals)
                b = getval(conn['B'], self.vals)
                y = (a >> b) & ((1 << len(conn['Y'])) - 1)
            elif t == '$shift':
                a = getval(conn['A'], self.vals)
                b = getval(conn['B'], self.vals)
                y = a >> b
            elif t in ('$_AND_', '$_OR_', '$_XOR_', '$_NOT_', '$_MUX_'):
                if t == '$_AND_': y = getval(conn['A'], self.vals) & getval(conn['B'], self.vals)
                elif t == '$_OR_': y = getval(conn['A'], self.vals) | getval(conn['B'], self.vals)
                elif t == '$_XOR_': y = getval(conn['A'], self.vals) ^ getval(conn['B'], self.vals)
                elif t == '$_NOT_': y = getval(conn['A'], self.vals) ^ 1
                else: y = getval(conn['B'], self.vals) if getval(conn['S'], self.vals) else getval(conn['A'], self.vals)
            else:
                raise Exception('unknown cell %s %s' % (t, n))
            for i, b in enumerate(conn['Y']):
                if isinstance(b, int):
                    self.vals[b] = (y >> i) & 1

    def port_out(self, port):
        nd = TOP['ports'][port]
        v = 0
        for i, b in enumerate(nd['bits']):
            if isinstance(b, int):
                v |= self.vals.get(b, 0) << i
            else:
                v |= (1 if b == '1' else 0) << i
        return v

    def read_state(self, bit):
        return self.state.get(bit, 0)

    def clock_edge(self):
        new = {}
        for n, c in self.dffs:
            conn = c['connections']
            d = getval(conn['D'], self.vals)
            for i, b in enumerate(conn['Q']):
                if isinstance(b, int):
                    new[b] = (d >> i) & 1
        self.state.update(new)

    def tick(self, inputs=None):
        self.vals = dict(self.state)
        if inputs:
            self.inputs(inputs)
        self.comb_eval()
        self.clock_edge()

    def out(self):
        for p in TOP['ports']:
            if 'OPAD' in p:
                return self.port_out(p)
        return 0

if __name__ == '__main__':
    s = Sim()
    # find data input (non-clock)
    din = [p for p in TOP['ports'] if 'IPAD' in p and p != 'RIOB33_X43Y25_IOB_X1Y26_IPAD'][0]
    print('din port', din)
    # idle run
    outs = []
    for k in range(200):
        s.tick({din: 1})
        outs.append(s.out())
    print('idle out', ''.join(map(str, outs[:60])))
    # button press behavior
    s2 = Sim()
    outs = []
    for k in range(3000):
        s2.tick({din: 0 if k < 1000 else 1})
        outs.append(s2.out())
    print('press out zeros at', [i for i, b in enumerate(outs) if b == 0][:30], 'total zeros', outs.count(0))
