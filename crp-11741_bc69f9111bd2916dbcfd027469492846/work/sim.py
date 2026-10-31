#!/usr/bin/env python3
"""Simulate the fasm2bels netlist (techmapped 7-series primitives)."""
import re
import sys
sys.path.insert(0, '/home/xiaoshabi/lessons/ctf/qwb/crp-11741_bc69f9111bd2916dbcfd027469492846/work')
from netlist import parse_verilog, const_val

CLK_NET = 'CLK_BUFG_BOT_R_X60Y48_BUFGCTRL_X0Y0_O'
DIN_PAD = 'LIOB33_X0Y13_IOB_X0Y13_IPAD'
CLK_PAD = 'RIOB33_X43Y25_IOB_X1Y26_IPAD'
OUT_PAD = 'LIOB33_X0Y111_IOB_X0Y112_OPAD'


class Sim:
    def __init__(self, path):
        self.cells, self.assigns = parse_verilog(path)
        self.by_out = {}
        self.ffs = []
        self.srls = []
        self.carry = []
        for c in self.cells:
            if c.ctype == 'FDRE':
                self.ffs.append(c)
                self.by_out[c.conns['Q']] = c
            elif c.ctype in ('SRL16E', 'SRLC16E'):
                self.srls.append(c)
                self.by_out[c.conns['Q']] = c
                if 'Q15' in c.conns:
                    self.by_out[c.conns['Q15']] = c
            elif c.ctype == 'CARRY4':
                self.carry.append(c)
                for name in self.split4(c.conns['O']):
                    self.by_out[name] = c
                for name in self.split4(c.conns['CO']):
                    self.by_out[name] = c
            elif c.ctype in ('LUT6_2',):
                o6 = c.conns.get('O6')
                o5 = c.conns.get('O5')
                if o6:
                    self.by_out[o6] = c
                if o5:
                    self.by_out[o5] = c
            elif c.ctype == 'MUXF7':
                self.by_out[c.conns['O']] = c
            elif c.ctype in ('IBUF', 'OBUF'):
                self.by_out[c.conns['O']] = c
            elif c.ctype == 'BUFGCTRL':
                self.by_out[c.conns['O']] = c
        # state
        self.q = {}
        for c in self.ffs:
            init = c.params.get('INIT', "1'b0")
            v = const_val(init)
            self.q[c.conns['Q']] = v if v is not None else 0
        # srl state: 16 bit shift register, index 0 = most recently shifted in
        self.srl_state = {}
        for c in self.srls:
            v = const_val(c.params.get('INIT', "16'h0000")) or 0
            self.srl_state[c.name] = [(v >> k) & 1 for k in range(16)]
        # cache per cycle
        self.cache = {}
        # external inputs
        self.din = 0
        self.clk = 0

    @staticmethod
    def split4(s):
        s = s.strip()
        assert s.startswith('{') and s.endswith('}')
        parts = [p.strip() for p in s[1:-1].split(',')]
        return parts[::-1]   # {D,C,B,A}: index0 = A (LSB)

    def lut_init(self, c):
        s = c.params['INIT']
        m = re.fullmatch(r"(\d+)'h([0-9a-fA-F]+)", s)
        return int(m.group(2), 16)

    def eval_net(self, net):
        net = net.strip()
        if net in self.cache:
            return self.cache[net]
        cv = const_val(net)
        if cv is not None:
            self.cache[net] = cv
            return cv
        if net in self.assigns:
            v = self.eval_net(self.assigns[net])
            self.cache[net] = v
            return v
        cell = self.by_out.get(net)
        if cell is None:
            # unknown / unconnected
            self.cache[net] = 0
            return 0
        v = self.eval_cell(cell, net)
        self.cache[net] = v
        return v

    def eval_cell(self, c, which):
        t = c.ctype
        if t == 'LUT6_2':
            init = self.lut_init(c)
            i = 0
            for k in range(6):
                i |= (self.eval_net(c.conns.get('I%d' % k, "1'b0")) & 1) << k
            if which == c.conns.get('O6'):
                return (init >> i) & 1
            else:
                return (init >> (i & 31)) & 1
        if t == 'FDRE':
            return self.q[c.conns['Q']]
        if t in ('SRL16E', 'SRLC16E'):
            st = self.srl_state[c.name]
            if which == c.conns.get('Q'):
                a = 0
                for k in range(4):
                    a |= (self.eval_net(c.conns.get('A%d' % k, "1'b0")) & 1) << k
                return st[a]
            else:
                return st[15]
        if t == 'CARRY4':
            S = [self.eval_net(x) for x in self.split4(c.conns['S'])]
            DI = [self.eval_net(x) for x in self.split4(c.conns['DI'])]
            O = self.split4(c.conns['O'])
            CO = self.split4(c.conns['CO'])
            cyi = c.conns.get('CI')
            if cyi is not None and const_val(cyi) is None:
                pass
            else:
                cyi = c.conns.get('CYINIT', "1'b0")
            cin = self.eval_net(cyi)
            for k in range(4):
                o = S[k] ^ cin
                cout = cin if S[k] else DI[k]
                if which == O[k]:
                    return o
                if which == CO[k]:
                    return cout
                cin = cout
            return 0
        if t == 'MUXF7':
            s = self.eval_net(c.conns['S'])
            return self.eval_net(c.conns['I1'] if s else c.conns['I0'])
        if t == 'IBUF':
            if c.conns['I'] == DIN_PAD:
                return self.din
            if c.conns['I'] == CLK_PAD:
                return self.clk
            return 0
        if t == 'BUFGCTRL':
            return self.eval_net(c.conns['I0'])
        if t == 'OBUF':
            return self.eval_net(c.conns['I'])
        if t == 'IBUF_O':
            return self.eval_net(c.conns['I'])
        return 0

    def tick(self, din=None):
        if din is not None:
            self.din = din
        # rising edge: evaluate D/CE, update FFs and SRLs
        self.cache = {}
        newq = {}
        for c in self.ffs:
            ce = self.eval_net(c.conns['CE'])
            r = self.eval_net(c.conns['R'])
            d = self.eval_net(c.conns['D'])
            q = c.conns['Q']
            if r:
                newq[q] = 0
            elif ce:
                newq[q] = d
            else:
                newq[q] = self.q[q]
        # SRL update
        newsrl = {}
        for c in self.srls:
            st = self.srl_state[c.name]
            ce = self.eval_net(c.conns['CE'])
            d = self.eval_net(c.conns['D'])
            if ce:
                st = [d] + st[:15]
            newsrl[c.name] = st
        self.q = newq
        self.srl_state = newsrl
        self.cache = {}

    def read_out(self):
        self.cache = {}
        return self.eval_net(OUT_PAD)


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    din = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    s = Sim('/home/xiaoshabi/lessons/ctf/qwb/crp-11741_bc69f9111bd2916dbcfd027469492846/work/crp.v')
    bits = []
    for k in range(n):
        s.tick(din)
        bits.append(s.read_out())
    txt = ''.join(str(b) for b in bits)
    print('first 200 bits:', txt[:200])
    print('ones:', sum(bits), '/', n)


if __name__ == '__main__':
    main()
