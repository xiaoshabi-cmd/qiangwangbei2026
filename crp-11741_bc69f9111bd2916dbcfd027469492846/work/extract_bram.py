#!/usr/bin/env python3
"""Extract BRAM INIT bits from parsed frames using prjxray-db segbits."""
import json
import sys
sys.path.insert(0, '/home/xiaoshabi/lessons/ctf/qwb/crp-11741_bc69f9111bd2916dbcfd027469492846/work')
from bitparse import Part, frames_from_bit

DB = '/tmp/prjxray-db/artix7'


def load_tilegrid():
    return json.load(open(DB + '/xc7a50t/tilegrid.json'))


def load_segbits(fn):
    seg = {}
    for line in open(fn):
        line = line.strip()
        if not line:
            continue
        parts = line.split(' ')
        feat = parts[0]
        bits = []
        for v in parts[1:]:
            if not v:
                continue
            w, b = v.split('_')
            bits.append((int(w), int(b)))
        seg[feat] = bits
    return seg


def main():
    part = Part(DB + '/xc7a35tcpg236-1/part.json')
    frames, order = frames_from_bit('Cryptarithm.bit', part)
    grid = load_tilegrid()
    res = {}
    for tilename, info in sorted(grid.items()):
        t = info['type']
        if t not in ('BRAM_L', 'BRAM_R'):
            continue
        br = info['bits'].get('BLOCK_RAM')
        if not br:
            continue
        base = int(br['baseaddr'], 16)
        nframes = br['frames']
        words = br['words']
        seg = load_segbits(DB + '/segbits_%s.block_ram.db' % t.lower())
        vals = {}
        for feat, bits in seg.items():
            # BRAM_X.RAMB18_Y0.INIT_00[000]
            fname, bitidx = feat.split('[')
            bitidx = int(bitidx[:-1])
            site = fname.split('.')[1]
            initname = fname.split('.')[2]
            key = (site, initname)
            if key not in vals:
                vals[key] = 0
            for (w, b) in bits:
                far = base + w
                ws = frames.get(far)
                if ws is None:
                    continue
                word = ws[b // 32]
                if (word >> (b % 32)) & 1:
                    vals[key] |= (1 << bitidx)
        nz = {k: v for k, v in vals.items() if v}
        if nz:
            res[tilename] = nz
            print('tile', tilename, 'type', t, 'nonzero inits:', len(nz))
            tot = sum(v.bit_length() for v in nz.values())
            print('   sites/inits:', sorted(set(k[0] for k in nz)), 'count', len(nz))
    # dump compactly
    with open('bram_dump.json', 'w') as f:
        json.dump({t: {'%s.%s' % k: '%x' % v for k, v in d.items()} for t, d in res.items()}, f, indent=0)
    print('tiles with nonzero init:', len(res))


if __name__ == '__main__':
    main()
