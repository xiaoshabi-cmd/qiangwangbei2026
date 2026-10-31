#!/usr/bin/env python3
"""A5/1 implementation, tested against hint vectors."""

class A51:
    def __init__(self):
        self.R1 = 0  # 19 bits
        self.R2 = 0  # 22 bits
        self.R3 = 0  # 23 bits

    def clock(self, fb, majority=True):
        if majority:
            c1 = (self.R1 >> 8) & 1
            c2 = (self.R2 >> 10) & 1
            c3 = (self.R3 >> 10) & 1
            maj = (c1 & c2) | (c2 & c3) | (c1 & c3)
            if c1 == maj:
                fb1 = ((self.R1 >> 13) ^ (self.R1 >> 16) ^ (self.R1 >> 17) ^ (self.R1 >> 18)) & 1
                self.R1 = ((self.R1 << 1) | fb1) & 0x7FFFF
            if c2 == maj:
                fb2 = ((self.R2 >> 20) ^ (self.R2 >> 21)) & 1
                self.R2 = ((self.R2 << 1) | fb2) & 0x3FFFFF
            if c3 == maj:
                fb3 = ((self.R3 >> 21) ^ (self.R3 >> 22)) & 1
                self.R3 = ((self.R3 << 1) | fb3) & 0x7FFFFF
        else:
            fb1 = ((self.R1 >> 13) ^ (self.R1 >> 16) ^ (self.R1 >> 17) ^ (self.R1 >> 18)) & 1
            fb2 = ((self.R2 >> 20) ^ (self.R2 >> 21)) & 1
            fb3 = ((self.R3 >> 21) ^ (self.R3 >> 22)) & 1
            self.R1 = ((self.R1 << 1) | fb1) & 0x7FFFF
            self.R2 = ((self.R2 << 1) | fb2) & 0x3FFFFF
            self.R3 = ((self.R3 << 1) | fb3) & 0x7FFFFF
        _ = fb

    def bit(self):
        self.clock(0, majority=True)
        return ((self.R1 >> 18) ^ (self.R2 >> 21) ^ (self.R3 >> 22)) & 1

def keystream(key, frame, nbytes, warmup=100, msb_key=True, msb_frame=True, majority_load=False):
    a = A51()
    kb = [(key >> (63 - i)) & 1 for i in range(64)] if msb_key else [(key >> i) & 1 for i in range(64)]
    fb = [(frame >> (21 - i)) & 1 for i in range(22)] if msb_frame else [(frame >> i) & 1 for i in range(22)]
    for i in range(64):
        a.clock(kb[i], majority=majority_load)
    for i in range(22):
        a.clock(fb[i], majority=majority_load)
    for _ in range(warmup):
        a.clock(0, majority=True)
    out = bytearray()
    for _ in range(nbytes):
        byt = 0
        for k in range(8):
            byt |= a.bit() << k  # lsb-first
        out.append(byt)
    return bytes(out)

def keystream_msb(key, frame, nbytes, **kw):
    a = A51()
    kb = [(key >> (63 - i)) & 1 for i in range(64)] if kw.get('msb_key', True) else [(key >> i) & 1 for i in range(64)]
    fb = [(frame >> (21 - i)) & 1 for i in range(22)] if kw.get('msb_frame', True) else [(frame >> i) & 1 for i in range(22)]
    for i in range(64): a.clock(kb[i], majority=kw.get('majority_load', False))
    for i in range(22): a.clock(fb[i], majority=kw.get('majority_load', False))
    for _ in range(kw.get('warmup', 100)): a.clock(0, majority=True)
    out = bytearray()
    for _ in range(nbytes):
        byt = 0
        for k in range(8):
            byt = (byt << 1) | a.bit()
        out.append(byt)
    return bytes(out)

HINT1 = (0x0123456789abcdef, 0, bytes.fromhex('3836c93c175ec224a6db1f8bd6a3b681'))
HINT2 = (0xdeadbeefcafebabe, 2796202, bytes.fromhex('b1993d4779346b929ceb31822fabaadd'))

for mk in (True, False):
    for mf in (True, False):
        for ml in (False, True):
            for wu in (100,):
                for name, fn in (('lsb', keystream), ('msb', keystream_msb)):
                    k1 = fn(HINT1[0], HINT1[1], 16, msb_key=mk, msb_frame=mf, majority_load=ml, warmup=wu)
                    if k1 == HINT1[2]:
                        print('MATCH!', name, 'msb_key', mk, 'msb_frame', mf, 'majority_load', ml, 'warmup', wu)
                        k2 = fn(HINT2[0], HINT2[1], 16, msb_key=mk, msb_frame=mf, majority_load=ml, warmup=wu)
                        print('  hint2 check:', k2.hex(), 'expected', HINT2[2].hex(), k2 == HINT2[2])
print('done')
# show a few candidates for eyeballing
print('cand1', keystream(HINT1[0], HINT1[1], 16).hex())
print('cand2', keystream_msb(HINT1[0], HINT1[1], 16).hex())
print('want1', HINT1[2].hex())
