#!/usr/bin/env python3
"""Massive A5/1-variant sweep: hint keys x conventions vs known-plaintext KS."""
import itertools
import json

TARGET = json.load(open('/home/xiaoshabi/lessons/ctf/qwb/crp-11741_bc69f9111bd2916dbcfd027469492846/work/target_ks.json'))
FR = TARGET['frame']
KS = bytes.fromhex(TARGET['ks16'])
KEYS = [0x0123456789abcdef, 0xdeadbeefcafebabe]

class A51:
    __slots__ = ('R1', 'R2', 'R3')

    def __init__(self):
        self.R1 = 0; self.R2 = 0; self.R3 = 0

    def step(self, inject, use_maj, maj_mask=0):
        fb1 = ((self.R1 >> 13) ^ (self.R1 >> 16) ^ (self.R1 >> 17) ^ (self.R1 >> 18)) & 1
        fb2 = ((self.R2 >> 20) ^ (self.R2 >> 21)) & 1
        fb3 = ((self.R3 >> 21) ^ (self.R3 >> 22)) & 1
        i1 = fb1 ^ inject; i2 = fb2 ^ inject; i3 = fb3 ^ inject
        if use_maj:
            c1 = (self.R1 >> 8) & 1; c2 = (self.R2 >> 10) & 1; c3 = (self.R3 >> 10) & 1
            maj = (c1 & c2) | (c2 & c3) | (c1 & c3)
            if c1 == maj: self.R1 = ((self.R1 << 1) | i1) & 0x7FFFF
            if c2 == maj: self.R2 = ((self.R2 << 1) | i2) & 0x3FFFFF
            if c3 == maj: self.R3 = ((self.R3 << 1) | i3) & 0x7FFFFF
        else:
            self.R1 = ((self.R1 << 1) | i1) & 0x7FFFF
            self.R2 = ((self.R2 << 1) | i2) & 0x3FFFFF
            self.R3 = ((self.R3 << 1) | i3) & 0x7FFFFF

    def out(self):
        return ((self.R1 >> 18) ^ (self.R2 >> 21) ^ (self.R3 >> 22)) & 1

def bits_val(v, n, byte_major, bit_msb):
    byts = [(v >> (8 * i)) & 0xff for i in range((n + 7) // 8)]
    if byte_major: byts = byts[::-1]
    bits = []
    for b in byts:
        bits += [(b >> (7 - k)) & 1 for k in range(8)] if bit_msb else [(b >> k) & 1 for k in range(8)]
    return bits[:n]

def ks(key, frame, n, kw):
    a = A51()
    kb = bits_val(key, 64, kw['kbyte'], kw['kbit'])
    fb = bits_val(frame, 22, kw['fbyte'], kw['fbit'])
    ml = kw['majload']
    for b in kb: a.step(b, ml)
    for b in fb: a.step(b, ml)
    wu = kw['warmup']; wi = kw['winject']; wm = kw['wmaj']
    for _ in range(wu): a.step(wi, wm)
    out = bytearray()
    for _ in range(n):
        byt = 0
        for k in range(8):
            if kw['outfirst']:
                o = a.out(); a.step(0, True)
            else:
                a.step(0, True); o = a.out()
            if kw['bytmsb']: byt = (byt << 1) | o
            else: byt |= o << k
        out.append(byt)
    return bytes(out)

hits = []
grid = list(itertools.product(
    (True, False),                      # kbyte
    (True, False),                      # kbit
    (True, False),                      # fbyte
    (True, False),                      # fbit
    (False, True),                      # majload
    (0, 100, 101, 99),                  # warmup
    (0, 1),                             # winject
    (True, False),                      # wmaj
    (False, True),                      # outfirst
    (True, False),                      # bytmsb
))
print('variants:', len(grid))
for kwv in grid:
    kw = dict(zip(['kbyte','kbit','fbyte','fbit','majload','warmup','winject','wmaj','outfirst','bytmsb'], kwv))
    for key in KEYS:
        k = ks(key, FR, 16, kw)
        if k == KS:
            hits.append((key, kw.copy()))
            print('HIT!', hex(key), kw)
if not hits:
    print('no hit in', len(grid) * 2, 'variants')
