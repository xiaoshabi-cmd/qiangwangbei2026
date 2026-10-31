#!/usr/bin/env python3
"""Verify LUT INIT bits: orig bitstream vs fasm2frames regeneration at INIT positions."""
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
fa2k = {}
for k, line in enumerate(open('/home/xiaoshabi/lessons/ctf/qwb/crp-11741_bc69f9111bd2916dbcfd027469492846/work/frames.txt')):
    parts = line.split()
    if len(parts) < 2: continue
    fa = int(parts[0], 16)
    ws = [int(x, 16) for x in parts[1].split(',') if x.strip()]
    gen.append((fa, ws))
    fa2k[fa] = len(gen) - 1

db = collections.defaultdict(dict)
for f2 in glob.glob('/tmp/prjxray-db/artix7/segbits_*.db'):
    base = os.path.basename(f2)[len('segbits_'):-3]
    for line in open(f2):
        parts = line.split()
        if len(parts) < 2: continue
        db[base][parts[0]] = parts[1:]

tg = json.load(open('/tmp/prjxray-db/artix7/xc7a50t/tilegrid.json'))
used = set(open('/home/xiaoshabi/lessons/ctf/qwb/crp-11741_bc69f9111bd2916dbcfd027469492846/work/used_tiles.txt').read().split())

mis = 0; tot = 0
per = collections.Counter()
for tn in sorted(used):
    if tn not in tg: continue
    tt = tg[tn]['type']; bv = tg[tn]['bits']['CLB_IO_CLK']
    B = int(bv['baseaddr'], 16); o = bv['offset']
    sdb = db.get(tt.lower())
    if not sdb: continue
    for feat, specs in sdb.items():
        if not re.search(r'(ALUT|BLUT|CLUT|DLUT)\.INIT', feat): continue
        for s in specs:
            if s.startswith('!') or '_' not in s: continue
            c, w = s.split('_')[:2]
            fa = B + int(c); wb = int(w)
            kk = fa2k.get(fa)
            if kk is None: continue
            j = o + wb // 32; b = wb % 32
            if j >= 101: continue
            ob = (orig[101 * kk + j] >> b) & 1
            gb = (gen[kk][1][j] >> b) & 1
            tot += 1
            if ob != gb:
                mis += 1
                per[(tn, feat, s)] += 1
print('INIT positions checked:', tot, 'mismatches:', mis)
for k2, v in list(per.items())[:20]: print(k2, v)
