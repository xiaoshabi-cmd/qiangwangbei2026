#!/usr/bin/env python3
"""Correctly map diff bits (orig bitstream vs fasm2frames output) to tile segbit coords."""
import struct, json, collections, glob, os

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
        i += cnt; pending=False
    else: i += 1

gen = []
for line in open('/home/xiaoshabi/lessons/ctf/qwb/crp-11741_bc69f9111bd2916dbcfd027469492846/work/frames.txt'):
    parts = line.split()
    if len(parts) < 2: continue
    gen.append((int(parts[0], 16), [int(x, 16) for x in parts[1].split(',') if x.strip()]))

tg = json.load(open('/tmp/prjxray-db/artix7/xc7a50t/tilegrid.json'))
# tile -> (baseaddr, offset, frames) for CLB_IO_CLK
tiles = {}
for tn, tv in tg.items():
    bv = tv['bits'].get('CLB_IO_CLK')
    if bv:
        tiles[tn] = (tv['type'], int(bv['baseaddr'], 16), bv['offset'], bv['frames'])
base2tiles = collections.defaultdict(list)
for tn, (tt, B, o, f) in tiles.items():
    base2tiles[B].append((tn, tt, o, f))

# DB: tile type -> set of (c, w) that appear (set or !)
dbwb = collections.defaultdict(set)
for f2 in glob.glob('/tmp/prjxray-db/artix7/segbits_*.db'):
    base = os.path.basename(f2)[len('segbits_'):-3]
    for line in open(f2):
        parts = line.split()
        if len(parts) < 2: continue
        for spec in parts[1:]:
            if '_' not in spec: continue
            c, w = spec.lstrip('!').split('_')[:2]
            try: dbwb[base].add((int(c), int(w)))
            except ValueError: pass

diffc = collections.defaultdict(set)   # tile type -> (tile, c, w)
unassigned = 0
for k, (fa, ws) in enumerate(gen):
    od = orig[101 * k:101 * k + 101]
    if len(od) < 101: break
    for j in range(101):
        m = od[j] ^ ws[j]
        if not m: continue
        for b in range(32):
            if not (m >> b & 1): continue
            # candidate tiles: those whose baseaddr <= fa < baseaddr+frames and word j in {o, o+1}
            hit = False
            for tn, tt, o, f in base2tiles.get(fa & ~0x3ff, []):
                pass
            # baseaddr includes minor=0; column part = fa & ~0x3ff only if fa minor < frames... fa minor from B+c
            # instead: find tiles where fa-B in [0,f)
            for B, tl in base2tiles.items():
                pass
            # direct scan (slow but ok once): precompute fa->tiles
            break
        break
# precompute fa -> list of (tile, type, offset)
fa2t = collections.defaultdict(list)
for tn, (tt, B, o, f) in tiles.items():
    for c in range(f):
        fa2t[B + c].append((tn, tt, o, c))
for k, (fa, ws) in enumerate(gen):
    od = orig[101 * k:101 * k + 101]
    if len(od) < 101: break
    for j in range(101):
        m = od[j] ^ ws[j]
        if not m: continue
        for b in range(32):
            if not (m >> b & 1): continue
            got = False
            for tn, tt, o, c in fa2t.get(fa, []):
                w = (j - o) * 32 + b
                if 0 <= w <= 49:
                    diffc[tt].add((tn, c, w))
                    got = True
            if not got:
                unassigned += 1
print('unassigned diff bits:', unassigned)
tot_nodb = 0
for tt, cells in sorted(diffc.items()):
    db = dbwb.get(tt.lower(), set())
    nodb = [x for x in cells if (x[1], x[2]) not in db]
    tot_nodb += len(nodb)
    ntiles = len(set(x[0] for x in cells))
    print('%-16s cells %5d noDB %5d ntiles %4d' % (tt, len(cells), len(nodb), ntiles))
    for x in nodb[:3]: print('     miss:', x)
print('TOTAL noDB:', tot_nodb)
