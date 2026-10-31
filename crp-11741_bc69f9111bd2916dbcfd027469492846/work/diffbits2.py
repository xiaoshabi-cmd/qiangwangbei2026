#!/usr/bin/env python3
"""Precise classification of lost bits: assign to INT (c<26) or CLB (c>=26) per DB coverage."""
import struct, json, collections, glob, os, re

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
genidx = {}
for line in open('/home/xiaoshabi/lessons/ctf/qwb/crp-11741_bc69f9111bd2916dbcfd027469492846/work/frames.txt'):
    parts = line.split()
    if len(parts) < 2: continue
    gen.append((int(parts[0], 16), [int(x, 16) for x in parts[1].split(',') if x.strip()]))

tg = json.load(open('/tmp/prjxray-db/artix7/xc7a50t/tilegrid.json'))
tiles = {}
for tn, tv in tg.items():
    bv = tv['bits'].get('CLB_IO_CLK')
    if bv: tiles[tn] = (tv['type'], int(bv['baseaddr'], 16), bv['offset'], bv['frames'])

# DB coverage: (tiletype, c, w) -> set of features (names)
dbfeat = collections.defaultdict(list)
for f2 in glob.glob('/tmp/prjxray-db/artix7/segbits_*.db'):
    base = os.path.basename(f2)[len('segbits_'):-3]
    for line in open(f2):
        parts = line.split()
        if len(parts) < 2: continue
        for spec in parts[1:]:
            if '_' not in spec: continue
            c, w = spec.lstrip('!').split('_')[:2]
            try: dbfeat[base + '.%d.%d' % (int(c), int(w))].append(parts[0] + ('!' if spec.startswith('!') else ''))
            except ValueError: pass

used = set(open('/home/xiaoshabi/lessons/ctf/qwb/crp-11741_bc69f9111bd2916dbcfd027469492846/work/used_tiles.txt').read().split())
usedB = {}
for tn in used:
    if tn in tiles: usedB[tiles[tn][1]] = tn

# map FA -> used tiles with (row via offset)
fa_rows = collections.defaultdict(list)
for tn in used:
    if tn not in tiles: continue
    tt, B, o, f = tiles[tn]
    for c in range(f):
        fa_rows[B + c].append((tn, tt, o, c))

def tile_of(fa, j):
    """find the tile whose (offset,offset+1) contains word j"""
    for tn, tt, o, c in fa_rows.get(fa, []):
        if j in (o, o + 1):
            return tn, tt, o, (j - o) * 32
    return None

summary = collections.Counter()
details = collections.defaultdict(list)
for k, (fa, ws) in enumerate(gen):
    od = orig[101 * k:101 * k + 101]
    if len(od) < 101: break
    for j in range(101):
        m = od[j] ^ ws[j]
        if not m: continue
        t = tile_of(fa, j)
        if not t: 
            summary['<no-tile>'] += bin(m).count('1')
            continue
        tn, tt, o, wbase = t
        for b in range(32):
            if not (m >> b & 1): continue
            w = wbase + b
            c = fa - tiles[tn][1]
            feats = dbfeat.get('%s.%d.%d' % (tt.lower(), c, w))
            if feats:
                summary[tt + '.decoded-region'] += 1
                details[tt + '.decoded-region'].append((tn, c, w, feats))
            else:
                summary[tt + '.NO-DB'] += 1
                details[tt + '.NO-DB'].append((tn, c, w))
print(dict(summary))
print()
# focus: IMUX-region lost bits (c 24,25 of INT tiles)
for key in list(details):
    if 'NO-DB' in key:
        xs = details[key]
        print(key, len(xs))
        for x in xs[:12]: print('   ', x)
