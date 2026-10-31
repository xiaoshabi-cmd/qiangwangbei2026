#!/usr/bin/env python3
"""Directly extract multi-bit features (LUT INIT etc.) from the raw bitstream,
compare with crp.v, and emit a patched crp.v."""
import struct, json, collections, glob, os, re, sys

data = open('/home/xiaoshabi/lessons/ctf/qwb/crp-11741_bc69f9111bd2916dbcfd027469492846/Cryptarithm.bit', 'rb').read()
sync = data.find(bytes.fromhex('aa995566'))
p = sync + 4
words = list(struct.unpack('>%dI' % ((len(data) - p) // 4), data[p:p + ((len(data) - p) // 4) * 4]))
i = 0; orig = []; pending = False
while i < len(words):
    w = words[i]; hdr = w >> 29
    if hdr == 1:
        op = (w >> 27) & 3; reg = (w >> 13) & 0x3fff; cnt = w & 0x7ff; i += 1
        if op == 2:
            if cnt: i += cnt
            else: pending = (reg == 2)
        elif op == 1: i += cnt
    elif hdr == 2:
        cnt = w & 0x7fffffff; i += 1
        if pending: orig += words[i:i + cnt]
        i += cnt; pending = False
    else: i += 1

gen = []
fa2k = {}
for line in open('/home/xiaoshabi/lessons/ctf/qwb/crp-11741_bc69f9111bd2916dbcfd027469492846/work/frames.txt'):
    parts = line.split()
    if len(parts) < 2: continue
    fa = int(parts[0], 16)
    ws = [int(x, 16) for x in parts[1].split(',') if x.strip()]
    fa2k[fa] = len(gen)
    gen.append((fa, ws))

def bit(fa, c, wb, o):
    """orig bit value at frame B+c... caller passes absolute fa"""
    kk = fa2k.get(fa)
    if kk is None: return None
    j = o + wb // 32
    b = wb % 32
    if j >= 101: return None
    return (orig[101 * kk + j] >> b) & 1

tg = json.load(open('/tmp/prjxray-db/artix7/xc7a50t/tilegrid.json'))
db = collections.defaultdict(dict)
for f2 in glob.glob('/tmp/prjxray-db/artix7/segbits_*.db'):
    base = os.path.basename(f2)[len('segbits_'):-3]
    for line in open(f2):
        parts = line.split()
        if len(parts) < 2: continue
        db[base][parts[0]] = parts[1:]

# ---- per-tile extraction of LUT INITs ----
def tile_lut_inits(tn):
    tv = tg[tn]; tt = tv['type']
    bv = tv['bits']['CLB_IO_CLK']
    B = int(bv['baseaddr'], 16); o = bv['offset']
    sdb = db.get(tt.lower())
    if not sdb: return {}
    inits = {}
    for L in 'ABCD':
        bits = {}
        for nn in range(64):
            feat = '%s.SLICEL_X0.%sLUT.INIT[%02d]' % (tt, L, nn)
            specs = sdb.get(feat)
            if not specs: continue
            s = specs[0]
            c, w = s.split('_')[:2]
            v = bit(B + int(c), int(c), int(w), o)
            if v is None: bits[nn] = None
            else: bits[nn] = v
        if len(bits) == 64 and all(v is not None for v in bits.values()):
            val = 0
            for nn, v in bits.items(): val |= v << nn
            inits['X0' + L] = val
    # X1 slice
    for L in 'ABCD':
        bits = {}
        ok = True
        for nn in range(64):
            feat = '%s.SLICEL_X1.%sLUT.INIT[%02d]' % (tt, L, nn)
            specs = sdb.get(feat)
            if not specs: ok = False; break
            s = specs[0]
            c, w = s.split('_')[:2]
            v = bit(B + int(c), int(c), int(w), o)
            if v is None: ok = False; break
            bits[nn] = v
        if ok:
            val = 0
            for nn, v in bits.items(): val |= v << nn
            inits['X1' + L] = val
    return inits

# map crp.v LUT names -> tile/slice/letter
import re as re2
cells, assigns = None, None
sys.path.insert(0, '/home/xiaoshabi/lessons/ctf/qwb/crp-11741_bc69f9111bd2916dbcfd027469492846/work')
from netlist import parse_verilog, const_val
cells, assigns = parse_verilog('/home/xiaoshabi/lessons/ctf/qwb/crp-11741_bc69f9111bd2916dbcfd027469492846/work/crp.v')

lutpat = re2.compile(r'(CLBL[LM]_[LR]_X\d+Y\d+)_SLICE_X(\d+)Y(\d+)_(\w)LUT$')
diffs = []
newinit = {}
for c in cells:
    if c.ctype != 'LUT6_2': continue
    m = lutpat.match(c.name)
    if not m: continue
    tile, sx, sy, L = m.group(1), int(m.group(2)), int(m.group(3)), m.group(4)
    # slice X parity: SLICEL_X0 = even site X? site X in name = sx; slice index X0/X1:
    # tile CLBLx_XaYb has sites SLICE_XsYb with s in {a, a+1}; SLICEL_X0 = first (X0)
    # determine from tilegrid sites order
    key = None
    # get site list
    sites = tg[tile].get('sites', {})
    # sites: 'SLICE_X%dY%d' -> ?
    sl = 'SLICE_X%dY%d' % (sx, sy)
    if sl in sites:
        xidx = sites[sl].get('x_index') if isinstance(sites[sl], dict) else None
    else:
        xidx = None
    if xidx is None:
        # fallback: SLICEL_X0/X1 by relative position within tile
        xs = sorted(int(re2.match(r'SLICE_X(\d+)Y(\d+)', s).group(1))
                    for s in sites if re2.match(r'SLICE_X(\d+)Y(\d+)', s))
        xidx = xs.index(sx) if sx in xs else 0
    key = 'X%d%s' % (xidx, L)
    inits = tile_lut_inits(tile)
    if key not in inits:
        diffs.append((c.name, 'NO-EXTRACT', hex(const_val(c.params['INIT']))))
        continue
    v = inits[key]
    old = const_val(c.params['INIT'])
    newinit[c.name] = v
    if v != old:
        diffs.append((c.name, 'old=%016x' % old, 'new=%016x' % v))
print('LUTs compared:', len(newinit), 'differences:', len(diffs))
for d in diffs[:40]: print('  ', d)
json.dump({k: v for k, v in newinit.items()}, open('/home/xiaoshabi/lessons/ctf/qwb/crp-11741_bc69f9111bd2916dbcfd027469492846/work/lut_init_orig.json', 'w'))
