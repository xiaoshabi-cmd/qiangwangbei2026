#!/usr/bin/env python3
"""Parse a 7-series .bit file into frames keyed by FAR (ports prjxray logic)."""
import json
import struct
import sys

WORDS_PER_FRAME = 101


def fa_make(block_type, bottom, row, column, minor):
    return ((block_type & 7) << 23) | ((1 if bottom else 0) << 22) | \
           ((row & 0x1f) << 17) | ((column & 0x3ff) << 7) | (minor & 0x7f)


def fa_block_type(a):
    return (a >> 23) & 7


def fa_bottom(a):
    return bool((a >> 22) & 1)


def fa_row(a):
    return (a >> 17) & 0x1f


def fa_column(a):
    return (a >> 7) & 0x3ff


def fa_minor(a):
    return a & 0x7f


BUS_NAMES = {0: 'CLB_IO_CLK', 1: 'BLOCK_RAM', 2: 'CFG_CLB'}


class Part:
    def __init__(self, path):
        d = json.load(open(path))
        self.idcode = int(d['idcode'], 0) if isinstance(d['idcode'], str) else d['idcode']
        self.regions = {}
        for name, reg in d['global_clock_regions'].items():
            rows = {}
            for rk, rv in reg['rows'].items():
                buses = {}
                for bk, bv in rv['configuration_buses'].items():
                    cols = {}
                    for ck, cv in bv['configuration_columns'].items():
                        cols[int(ck)] = cv['frame_count']
                    buses[bk] = cols
                rows[int(rk)] = buses
            self.regions[name] = rows

    def region(self, bottom):
        return self.regions['bottom' if bottom else 'top']

    def is_valid(self, a):
        rows = self.region(fa_bottom(a))
        r = rows.get(fa_row(a))
        if r is None:
            return False
        cols = r.get(BUS_NAMES.get(fa_block_type(a)))
        if cols is None:
            return False
        fc = cols.get(fa_column(a))
        if fc is None:
            return False
        return fa_minor(a) < fc

    def _region_next(self, a):
        rows = self.region(fa_bottom(a))
        r = rows.get(fa_row(a))
        if r is None:
            return None
        cols = r.get(BUS_NAMES.get(fa_block_type(a)))
        if cols is not None:
            fc = cols.get(fa_column(a))
            if fc is not None:
                if fa_minor(a) + 1 < fc:
                    return a + 1
                # next column
                for c in sorted(cols):
                    if c > fa_column(a) and cols[c] > 0:
                        return fa_make(fa_block_type(a), fa_bottom(a), fa_row(a), c, 0)
        # next row in this region
        for nr in sorted(rows):
            if nr > fa_row(a):
                cand = fa_make(fa_block_type(a), fa_bottom(a), nr, 0, 0)
                if self.is_valid(cand):
                    return cand
        return None

    def next_addr(self, a):
        n = self._region_next(a)
        if n is not None:
            return n
        if not fa_bottom(a):
            cand = fa_make(fa_block_type(a), True, 0, 0, 0)
            if self.is_valid(cand):
                return cand
        if fa_block_type(a) < 1:
            cand = fa_make(1, False, 0, 0, 0)
            if self.is_valid(cand):
                return cand
        if fa_block_type(a) < 2:
            cand = fa_make(2, False, 0, 0, 0)
            if self.is_valid(cand):
                return cand
        return None


def parse_packets(data):
    sync = data.find(bytes.fromhex('aa995566'))
    if sync < 0:
        raise ValueError('no sync word')
    p = sync + 4
    words = list(struct.unpack('>%dI' % ((len(data) - p) // 4), data[p:p + ((len(data) - p) // 4) * 4]))
    i = 0
    packets = []
    while i < len(words):
        w = words[i]
        hdr = w >> 29
        if hdr == 1:
            op = (w >> 27) & 3
            reg = (w >> 13) & 0x3fff
            cnt = w & 0x7ff
            i += 1
            if op == 2:
                if cnt == 0:
                    # count comes from next type2 packet
                    if i < len(words) and (words[i] >> 29) == 2:
                        cnt = words[i] & 0x1fffffff
                        i += 1
                        d = words[i:i + cnt]
                        i += cnt
                        packets.append((op, reg, d))
                    else:
                        packets.append((op, reg, []))
                else:
                    d = words[i:i + cnt]
                    i += cnt
                    packets.append((op, reg, d))
            elif op == 1:
                i += cnt
                packets.append((op, reg, []))
            else:
                packets.append((op, reg, []))
        elif hdr == 2:
            cnt = w & 0x1fffffff
            i += 1
            d = words[i:i + cnt]
            i += cnt
            packets.append((2, None, d))
        else:
            i += 1
            packets.append((0, None, []))
    return packets, words


REG_CRC = 0
REG_FAR = 1
REG_FDRI = 2
REG_CMD = 4
REG_CTL1 = 0x18
REG_IDCODE = 0x0c


def frames_from_bit(path, part):
    data = open(path, 'rb').read()
    packets, words = parse_packets(data)
    cmd = 0
    far = 0
    ctl1 = 0
    start_new_write = False
    frames = {}
    order = []
    for op, reg, d in packets:
        if op != 2:
            continue
        if reg == REG_CMD and d:
            cmd = d[0]
            if cmd == 1:
                start_new_write = True
        elif reg == REG_FAR and d:
            far = d[0]
            if not ((ctl1 >> 21) & 1) and cmd == 1:
                start_new_write = True
        elif reg == REG_CTL1 and d:
            ctl1 = d[0]
        elif reg == REG_IDCODE and d:
            pass
        elif reg == REG_FDRI and d:
            if start_new_write:
                cur = far
                start_new_write = False
            else:
                cur = far
            ii = 0
            n = len(d)
            while ii + WORDS_PER_FRAME <= n:
                frames[cur] = d[ii:ii + WORDS_PER_FRAME]
                order.append(cur)
                ii += WORDS_PER_FRAME
                nxt = part.next_addr(cur)
                if nxt is None:
                    break
                if fa_block_type(nxt) != fa_block_type(cur) or \
                   fa_bottom(nxt) != fa_bottom(cur) or \
                   fa_row(nxt) != fa_row(cur):
                    ii += 2 * WORDS_PER_FRAME
                cur = nxt
    return frames, order


def write_bits(frames, out):
    with open(out, 'w') as f:
        for far, ws in frames.items():
            for widx, w in enumerate(ws):
                if w == 0:
                    continue
                for b in range(32):
                    if (w >> b) & 1:
                        f.write('bit_%08x_%03d_%02d\n' % (far, widx, b))


if __name__ == '__main__':
    partpath = '/tmp/prjxray-db/artix7/xc7a35tcpg236-1/part.json'
    part = Part(partpath)
    bit = sys.argv[1] if len(sys.argv) > 1 else 'Cryptarithm.bit'
    frames, order = frames_from_bit(bit, part)
    print('frames parsed:', len(frames), 'order entries:', len(order))
    print('first 5 fars:', [hex(x) for x in order[:5]])
    print('last 3 fars:', [hex(x) for x in order[-3:]])
    # count valid addresses in part
    cnt = 0
    bt = {}
    for name, rows in part.regions.items():
        for r, buses in rows.items():
            for b, cols in buses.items():
                for c, fc in cols.items():
                    cnt += fc
                    bt[b] = bt.get(b, 0) + fc
    print('expected total frames:', cnt, 'by bus:', bt)
    if len(sys.argv) > 2:
        write_bits(frames, sys.argv[2])
        print('wrote', sys.argv[2])
