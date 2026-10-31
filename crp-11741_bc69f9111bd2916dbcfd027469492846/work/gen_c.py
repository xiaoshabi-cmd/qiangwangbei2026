#!/usr/bin/env python3
"""Generate a fast C simulator from the fasm2bels netlist."""
import sys
sys.path.insert(0, '/home/xiaoshabi/lessons/ctf/qwb/crp-11741_bc69f9111bd2916dbcfd027469492846/work')
from netlist import parse_verilog, const_val

OUT_PAD = 'LIOB33_X0Y111_IOB_X0Y112_OPAD'
DIN_PAD = 'LIOB33_X0Y13_IOB_X0Y13_IPAD'


class Builder:
    def __init__(self, path):
        self.cells, self.assigns = parse_verilog(path)
        self.net_id = {}
        self.expr = {}
        self.ffs = []
        self.srls = []
        self.carry = []
        self.luts = []
        self.order = []
        self.built = set()
        self.visiting = set()
        self.loops = 0
        for c in self.cells:
            if c.ctype == 'FDRE':
                self.ffs.append(c)
            elif c.ctype in ('SRL16E', 'SRLC16E'):
                self.srls.append(c)
            elif c.ctype == 'CARRY4':
                self.carry.append(c)
            elif c.ctype == 'LUT6_2':
                self.luts.append(c)
        self.ff_idx = {c.conns['Q']: i for i, c in enumerate(self.ffs)}
        self.srl_idx = {}
        for i, c in enumerate(self.srls):
            self.srl_idx[c.conns['Q']] = (i, 'Q')
            if 'Q15' in c.conns:
                self.srl_idx[c.conns['Q15']] = (i, 'Q15')

    def nid(self, name):
        if name not in self.net_id:
            self.net_id[name] = len(self.net_id)
        return self.net_id[name]

    def build_net(self, name):
        name = name.strip()
        cv = const_val(name)
        if cv is not None:
            return str(cv & 1)
        if name in self.built:
            return 'v%d' % self.nid(name)
        if name in self.visiting:
            self.loops += 1
            return 'v%d' % self.nid(name)
        self.visiting.add(name)
        if name in self.assigns:
            e = self.build_net(self.assigns[name])
        else:
            e = self.cell_expr(name)
        self.visiting.discard(name)
        vid = self.nid(name)
        self.expr[name] = e
        self.order.append((vid, e))
        self.built.add(name)
        return 'v%d' % vid

    def cell_expr(self, outname):
        if outname in self.ff_idx:
            return 'f%d' % self.ff_idx[outname]
        if outname in self.srl_idx:
            i, kind = self.srl_idx[outname]
            if kind == 'Q15':
                return '((s%d >> 15) & 1)' % i
            c = self.srls[i]
            terms = []
            for k in range(4):
                terms.append('((%s)<<%d)' % (self.build_net(c.conns.get('A%d' % k, "1'b0")), k))
            return '((s%d >> (%s)) & 1)' % (i, '|'.join(terms))
        for c in self.luts:
            if c.conns.get('O6') == outname:
                return self.lut_expr(c, 6)
            if c.conns.get('O5') == outname:
                return self.lut_expr(c, 5)
        for c in self.carry:
            for k, n in enumerate(self.split4(c.conns['O'])):
                if n == outname:
                    return self.carry_expr(c, 'O', k)
            for k, n in enumerate(self.split4(c.conns['CO'])):
                if n == outname:
                    return self.carry_expr(c, 'CO', k)
        for c in self.cells:
            if c.ctype == 'MUXF7' and c.conns.get('O') == outname:
                return '(%s ? %s : %s)' % (
                    self.build_net(c.conns['S']), self.build_net(c.conns['I1']),
                    self.build_net(c.conns['I0']))
            if c.ctype == 'BUFGCTRL' and c.conns.get('O') == outname:
                return '1'
            if c.ctype == 'IBUF' and c.conns.get('O') == outname:
                return 'din' if c.conns['I'] == DIN_PAD else '0'
            if c.ctype == 'OBUF' and c.conns.get('O') == outname:
                return self.build_net(c.conns['I'])
        return '0'

    def lut_expr(self, c, nbits):
        init = const_val(c.params['INIT'])
        terms = []
        for k in range(nbits):
            t = self.build_net(c.conns.get('I%d' % k, "1'b0"))
            terms.append('((%s)<<%d)' % (t, k))
        idx = '|'.join(terms) if terms else '0'
        return '((0x%xULL >> (%s)) & 1)' % (init, idx)

    @staticmethod
    def split4(s):
        s = s.strip()
        parts = [p.strip() for p in s[1:-1].split(',')]
        assert len(parts) == 4, s
        return parts[::-1]   # Verilog concat {D,C,B,A}: index0 = A (LSB)

    def carry_expr(self, c, which, k):
        S = [self.build_net(x) for x in self.split4(c.conns['S'])]
        DI = [self.build_net(x) for x in self.split4(c.conns['DI'])]
        ci = c.conns.get('CI')
        if ci is not None and const_val(ci) is None:
            cyi = ci          # chained carry from previous CARRY4
        else:
            cyi = c.conns.get('CYINIT', "1'b0")
        cexpr = self.build_net(cyi)
        exprs = []
        for i in range(4):
            oexpr = '(%s ^ %s)' % (S[i], cexpr)
            cnext = '((%s) ? (%s) : (%s))' % (S[i], cexpr, DI[i])
            exprs.append((oexpr, cnext))
            cexpr = cnext
        return exprs[k][0] if which == 'O' else exprs[k][1]

    def gen(self):
        self.build_net(OUT_PAD)
        for c in self.ffs:
            for p in ('D', 'CE', 'R'):
                self.build_net(c.conns[p])
        for c in self.srls:
            for p in ('D', 'CE'):
                self.build_net(c.conns[p])
            for k in range(4):
                self.build_net(c.conns.get('A%d' % k, "1'b0"))


def main():
    b = Builder('/home/xiaoshabi/lessons/ctf/qwb/crp-11741_bc69f9111bd2916dbcfd027469492846/work/crp.v')
    b.gen()
    print('// nets', len(b.net_id), 'ffs', len(b.ffs), 'srls', len(b.srls), 'loops', b.loops, file=sys.stderr)
    decls = ['static uint8_t v%d = 0;' % i for i in range(len(b.net_id))]
    body = ['  v%d = %s;' % (vid, e) for vid, e in b.order]
    out = []
    out.append('#include <stdint.h>')
    out.append('#include <stdio.h>')
    out.append('#include <stdlib.h>')
    out.append('#include <string.h>')
    out.append('static uint8_t din = 0;')
    out.extend(decls)
    if b.ffs:
        out.append('static uint8_t ' + ', '.join('f%d' % i for i in range(len(b.ffs))) + ';')
        out.append('static uint8_t ' + ', '.join('nq%d' % i for i in range(len(b.ffs))) + ';')
    if b.srls:
        out.append('static uint16_t ' + ', '.join('s%d' % i for i in range(len(b.srls))) + ';')
    out.append('static void comb(void) {')
    out.extend(body)
    out.append('}')
    out.append('static void tick(void) {')
    out.append('  comb();')
    for i, c in enumerate(b.ffs):
        out.append('  { uint8_t nr = %s; uint8_t nce = %s; uint8_t nd = %s;'
                   % (b.build_net(c.conns['R']), b.build_net(c.conns['CE']),
                      b.build_net(c.conns['D'])))
        out.append('    nq%d = nr ? 0 : (nce ? nd : f%d); }' % (i, i))
    for i, c in enumerate(b.srls):
        out.append('  { uint8_t nce = %s; uint8_t nd = %s;'
                   % (b.build_net(c.conns['CE']), b.build_net(c.conns['D'])))
        out.append('    if (nce) s%d = (uint16_t)(((s%d << 1) | nd) & 0xffff); }' % (i, i))
    for i in range(len(b.ffs)):
        out.append('  f%d = nq%d;' % (i, i))
    out.append('  comb();')
    out.append('}')
    # din program: argv[2] is a bit string; extended with last value
    out.append(r'''
int main(int argc, char** argv) {
  long n = atol(argv[1]);
  char* prog = NULL;
  long plen = 0;
  if (argc > 2 && argv[2][0]) {
    FILE* f = fopen(argv[2], "rb");
    if (f) {
      fseek(f, 0, SEEK_END); plen = ftell(f); fseek(f, 0, SEEK_SET);
      prog = malloc(plen + 1);
      if (fread(prog, 1, plen, f) != (size_t)plen) plen = 0;
      fclose(f);
    }
  }
  for (long k = 0; k < n; k++) {
    if (plen > 0) din = (k < plen) ? (uint8_t)(prog[k] == '1') : (uint8_t)(prog[plen-1] == '1');
    tick();
    putchar(48 + (''' + 'v%d' % b.nid(OUT_PAD) + r''' & 1));
    if (dump) {
      putchar(' ');
''' + '\n'.join("      putchar(48 + f%d);" % i for i in range(len(b.ffs))) + r'''
      putchar(10);
    }
  }
  putchar(10);
  return 0;
}
''')
    init_code = '\n'.join(
        '    f%d = ini[%d] - 48;' % (i, i) for i in range(len(b.ffs)))
    out[-1] = out[-1].replace(
        '  long n = atol(argv[1]);',
        '  long n = atol(argv[1]);\n  int dump = (argc > 3 && argv[3][0] == \'d\');\n'
        '  if (argc > 4) { const char* ini = argv[4]; if ((long)strlen(ini) >= %d) {\n%s\n  } }'
        % (len(b.ffs), init_code))
    path = '/home/xiaoshabi/lessons/ctf/qwb/crp-11741_bc69f9111bd2916dbcfd027469492846/work/sim.c'
    open(path, 'w').write('\n'.join(out))
    print('wrote', path, len(b.order), 'comb statements', file=sys.stderr)


if __name__ == '__main__':
    main()
