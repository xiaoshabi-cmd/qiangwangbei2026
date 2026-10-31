#!/usr/bin/env python3
"""Parse fasm2bels techmapped Verilog into a simulatable netlist."""
import re


class Cell:
    def __init__(self, ctype, name, params, conns):
        self.ctype = ctype
        self.name = name
        self.params = params
        self.conns = conns

    def __repr__(self):
        return '<%s %s>' % (self.ctype, self.name)


def parse_verilog(path):
    src = open(path).read()
    # strip comments
    src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
    src = re.sub(r'//[^\n]*', '', src)
    assigns = {}
    cells = []
    i = 0
    lines = src.split('\n')
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        # skip blanks/attributes/assigns/wire decls/module header
        if not line or line.startswith('(*') or line.startswith('assign') \
                or line.startswith('wire') or line.startswith('module') \
                or line.startswith('input') or line.startswith('output') \
                or line.startswith('endmodule') or line.startswith(')') \
                or line.startswith(';'):
            i += 1
            continue
        m = re.match(r'([A-Z][A-Za-z0-9_]*)\s*(#\s*\(.*)?$', line)
        if not m:
            i += 1
            continue
        ctype = m.group(1)
        # gather statement until line == ');' or contains ');'
        stmt = []
        j = i
        while j < len(lines):
            stmt.append(lines[j])
            if lines[j].strip().startswith(');') or lines[j].strip().endswith(');'):
                break
            j += 1
        text = '\n'.join(stmt)
        # split params and conns: params are before the instance name paren
        pmatch = re.search(r'\)\s*([A-Za-z_][A-Za-z0-9_$]*)\s*\(', text)
        if pmatch:
            name = pmatch.group(1)
            ptext = text[:pmatch.start()]
            ctext = text[pmatch.start():]
        else:
            # no params, e.g. "IBUF name ( ... );"
            m2 = re.match(r'[A-Z][A-Za-z0-9_]*\s+([A-Za-z_][A-Za-z0-9_$]*)\s*\(', text)
            if not m2:
                i = j + 1
                continue
            name = m2.group(1)
            ptext = ''
            ctext = text
        params = {}
        for pm in re.finditer(r'\.([A-Za-z0-9_]+)\s*\(\s*([^)]*?)\s*\)', ptext):
            params[pm.group(1)] = pm.group(2).strip()
        conns = {}
        for cm in re.finditer(r'\.([A-Za-z0-9_]+)\s*\(\s*([^)]*?)\s*\)', ctext):
            conns[cm.group(1)] = cm.group(2).strip()
        cells.append(Cell(ctype, name, params, conns))
        i = j + 1
    for m in re.finditer(r'assign\s+([A-Za-z_][A-Za-z0-9_$]*)\s*=\s*([^;]+);', src):
        assigns[m.group(1)] = m.group(2).strip()
    return cells, assigns


def const_val(s):
    s = s.strip()
    if s in ('1\'b1', '1\'b0', '1\'h1', '1\'h0'):
        return int(s[-1], 16) if s[-1] in '01' else int(s[-1], 16)
    m = re.fullmatch(r"(\d+)'([bdh])([0-9a-fA-FxXzZ_]+)", s)
    if m:
        w = int(m.group(1))
        base = {'b': 2, 'd': 10, 'h': 16}[m.group(2)]
        v = m.group(3).replace('_', '')
        try:
            return int(v, base)
        except ValueError:
            return 0
    if re.fullmatch(r'\d+', s):
        return int(s)
    return None


if __name__ == '__main__':
    import sys
    cells, assigns = parse_verilog(sys.argv[1])
    from collections import Counter
    print(Counter(c.ctype for c in cells))
    print('assigns', len(assigns))
    # fanout of the input pin net
    tgt = 'LIOB33_X0Y13_IOB_X0Y13_I'
    users = []
    for c in cells:
        for p, v in c.conns.items():
            if v == tgt:
                users.append((c.name, c.ctype, p))
    print('users of data input:', users)
    for a, r in assigns.items():
        if r == tgt:
            print('assign', a)
