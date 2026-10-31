#!/usr/bin/env python3
"""Test battery of cipher constructions against the two (KEY,FRAME)->KS vectors."""
import struct, itertools, hashlib, sys

V1 = (int('0123456789abcdef', 16), 0, bytes.fromhex('3836c93c175ec224a6db1f8bd6a3b681'))
V2 = (int('deadbeefcafebabe', 16), 2796202, bytes.fromhex('b1993d4779346b929ceb31822fabaadd'))
VEC = [V1, V2]

hits = []

def check(name, gen):
    """gen(key_int, frame) -> bytes; call generator lazily only if v1 matches"""
    try:
        ks = gen(V1[0], V1[1])
    except Exception as e:
        return
    if ks and ks[:16] == V1[2]:
        ks2 = gen(V2[0], V2[1])
        ok = ks2[:16] == V2[2]
        print('*** MATCH v1', name, 'v2:', ok, ks2[:16].hex() if ks2 else '')
        hits.append((name, ok))
    # partial: check 1-byte coincidence is too common; also check 4-byte on v1 only for triage
    elif ks and ks[:4] == V1[2][:4]:
        print('  partial v1[:4]', name, ks[:8].hex())

# ---------- ARX primitives ----------
M32 = 0xffffffff
def rotl(x, r): return ((x << r) | (x >> (32 - r))) & M32
def rotr(x, r): return ((x >> r) | (x << (32 - r))) & M32

def tea_enc(v0, v1, k, rounds=32, delta=0x9E3779B9):
    s = 0
    for _ in range(rounds):
        s = (s + delta) & M32
        v0 = (v0 + (((v1 << 4) + k[0]) ^ (v1 + s) ^ ((v1 >> 5) + k[1]))) & M32
        v1 = (v1 + (((v0 << 4) + k[2]) ^ (v0 + s) ^ ((v0 >> 5) + k[3]))) & M32
    return v0, v1

def xtea_enc(v0, v1, k, rounds=32, delta=0x9E3779B9):
    s = 0
    for _ in range(rounds):
        v0 = (v0 + ((((v1 << 4) ^ (v1 >> 5)) + v1) ^ (s + k[s & 3]))) & M32
        s = (s + delta) & M32
        v1 = (v1 + ((((v0 << 4) ^ (v0 >> 5)) + v0) ^ (s + k[(s >> 11) & 3]))) & M32
    return v0, v1

def xtea_dec(v0, v1, k, rounds=32, delta=0x9E3779B9):
    s = (delta * rounds) & M32
    for _ in range(rounds):
        v1 = (v1 - ((((v0 << 4) ^ (v0 >> 5)) + v0) ^ (s + k[(s >> 11) & 3]))) & M32
        s = (s - delta) & M32
        v0 = (v0 - ((((v1 << 4) ^ (v1 >> 5)) + v1) ^ (s + k[s & 3]))) & M32
    return v0, v1

def tea_dec(v0, v1, k, rounds=32, delta=0x9E3779B9):
    s = (delta * rounds) & M32
    for _ in range(rounds):
        v1 = (v1 - (((v0 << 4) + k[2]) ^ (v0 + s) ^ ((v0 >> 5) + k[3]))) & M32
        v0 = (v0 - (((v1 << 4) + k[0]) ^ (v1 + s) ^ ((v1 >> 5) + k[1]))) & M32
        s = (s - delta) & M32
    return v0, v1

def key_words(ki, order='be'):
    kb = ki.to_bytes(8, order)
    return list(struct.unpack('>4I', kb)), list(struct.unpack('<4I', kb))

def blocks_from_frame(frame, nblocks, layout):
    """yield 64-bit block values"""
    for i in range(nblocks):
        if layout == 'hi':      # frame in high word, counter low
            yield (frame << 32) | i
        elif layout == 'lo':
            yield (i << 32) | frame
        elif layout == 'sum':
            yield (frame + i) & M32
        elif layout == 'only':
            yield frame & M32
        elif layout == 'rep':
            yield (frame << 32) | frame

def arx_battery():
    for fname, f in (('tea', tea_enc), ('tea_dec', tea_dec), ('xtea', xtea_enc), ('xtea_dec', xtea_dec)):
        for kw in ('be', 'le'):
            for layout in ('hi', 'lo', 'sum', 'only', 'rep'):
                for rounds in (32, 16, 64):
                    def gen(ki, fr, f=f, kw=kw, layout=layout, rounds=rounds):
                        ks = ks4, kl4 = key_words(ki, kw)[0 if kw == 'be' else 1]
                        out = b''
                        for blk in blocks_from_frame(fr, 2, layout):
                            v0, v1 = (blk >> 32) & M32, blk & M32
                            a, b = f(v0, v1, ks4, rounds)
                            out += struct.pack('>II', a, b)
                        return out
                    check('%s/%s/%s/r%d' % (fname, kw, layout, rounds), gen)
                    # swapped word order output
                    def gen2(ki, fr, f=f, kw=kw, layout=layout, rounds=rounds):
                        ks4 = key_words(ki, kw)[0 if kw == 'be' else 1]
                        out = b''
                        for blk in blocks_from_frame(fr, 2, layout):
                            a, b = f((blk >> 32) & M32, blk & M32, ks4, rounds)
                            out += struct.pack('<II', a, b)
                        return out
                    check('%s/%s/%s/r%d/swapout' % (fname, kw, layout, rounds), gen2)

# ---------- Speck / Simon ----------
def speck64_round(x, y, k):
    x = (rotr(x, 8) + y) & M32
    x ^= k
    y = rotl(y, 3) ^ x
    return x, y

def speck64_expand(key_words3, rounds=27):
    rk = [key_words3[0]]
    k = list(key_words3)
    for i in range(rounds - 1):
        k[1], k[2] = speck64_round(k[1], k[2], rk[i])
        rk.append(k[0] if False else rk[i])  # placeholder
    # proper: lfsr feed
    return None

def speck64_128(key4, rounds=27):
    """Speck64/128, key = 4 words; returns list of round keys."""
    rk = [key4[0]]
    k = list(key4[1:])
    for i in range(rounds - 1):
        k[0], k[1] = speck64_round(k[0], k[1], rk[-1])
        k[2] = (rotr(k[2], 8) + k[1]) & M32  # wrong generic; use standard below
    return rk

# implement standard Speck64/128 key schedule properly
def speck_expand(l, k0, rounds):
    rk = [k0]
    for i in range(rounds - 1):
        l[0], _ = speck64_round(l[0], l[1] if len(l) > 1 else l[0], rk[-1])
        # generic for 3-word key schedule (m=4): standard is
        rk.append(rk[-1])
    return rk

# Simpler: use known-good generic Speck implementation
def speck_enc(pt_words, key_words, word_bits=32, rounds=27, alpha=8, beta=3):
    n = word_bits
    M = (1 << n) - 1
    def R(x, y, k):
        x = (((x >> alpha) | (x << (n - alpha))) & M) 
        x = (x + y) & M
        x ^= k
        y = (((y << beta) | (y >> (n - beta))) & M) ^ x
        return x, y
    # key schedule m words
    m = len(key_words)
    rk = [key_words[0]]
    lk = list(key_words[1:])
    for i in range(rounds - 1):
        # round key schedule
        for j in range(len(lk) - 1):
            lk[j], _ = R(lk[j], lk[j + 1], rk[i]) if False else (lk[j], lk[j + 1])
        # standard: lk[-1] = R(lk[-1], rk[i]) ... depends on m; handle m=4 (128-bit key)
        if m == 4:
            lk[2], _ = R(lk[2], rk[i], i)
            lk[0], lk[1] = R(lk[0], lk[1], rk[i])
            lk[1], lk[2] = lk[1], lk[2]
        rk.append(rk[i])
    # WRONG generic; bail out
    return None

def speck64_128_proper(key_int, order='be'):
    kb = key_int.to_bytes(16, order) if False else key_int.to_bytes(8, order) * 2
    K = list(struct.unpack('>4I' if order == 'be' else '<4I', kb))
    l = [K[3], K[2], K[1]]  # note standard ordering: k[0]=K0 lowest
    k0 = K[0]
    rk = [k0]
    for i in range(26):
        # l[-1] = R(l[-1], rk[i]) then rotate list, k_new = ...
        # standard Speck64/128:
        #   l[i-1+m-2] = (l[i-1] >> 8) + k[i]... ; use array approach
        x = (rotr(l[-1], 8) + rk[i]) & M32
        x ^= i
        nl = (rotl(l[0], 3) ^ x) if len(l) == 3 else None
        # for m=4: l = [l2,l1,l0]; new round key = l0; l2 = R(l2, k_prev); then l1 = R(l1, l2); l0 = R(l0, l1)
        break
    return None

# do Speck via a clean correct implementation
def speck_correct(key_bytes, wordn=32, rounds=27, alpha=8, beta=3):
    """key_bytes: raw bytes, len = m*wordn/8, m in {2,3,4}. Returns round keys and enc func."""
    m = len(key_bytes) * 8 // wordn
    M = (1 << wordn) - 1
    words = [int.from_bytes(key_bytes[i * wordn // 8:(i + 1) * wordn // 8], 'little') for i in range(m)]
    # Speck standard: key = k0, l0, l1, ..., l[m-2] where bytes are LE per word
    k0 = words[0]
    l = words[1:]  # l[m-2] ... ordering: l list with l[0] = first after k0
    # schedule (from spec): for i in 0..rounds-2: l[i mod (m-2)]... simpler circular buffer
    if m == 2:
        lk = [l[0]]
    else:
        lk = list(reversed(l))  # lk[-1] is l_{m-2}? We'll use: B=lk[-1], A=others
    rk = [k0]
    b = lk[-1]
    a = lk[:-1]
    for i in range(rounds - 1):
        # B = R(B, k); A[j] = R(A[j], B) chain
        b = (((rotr(b, alpha) + rk[i]) & M) ^ i)
        na = rotl(a[0], beta) ^ b if a else b
        for j in range(len(a) - 1):
            a[j] = (((rotr(a[j], alpha) + (a[j + 1] if j + 1 < len(a) else b)) & M))
        if a:
            a[-1] = (((rotr(a[-1], alpha) + b) & M))
        a = [na] + a[:-1] if a else a
        rk.append(b)
    def enc(x, y):
        for i in range(rounds):
            x = (rotr(x, alpha) + y) & M
            x ^= rk[i]
            y = rotl(y, beta) ^ x
        return x, y
    return enc

def speck_battery():
    for kb_len, wordn, rounds in ((16, 32, 27), (12, 32, 26), (8, 32, 25), (8, 24, 23), (6, 24, 23), (4, 16, 22)):
        for order in ('be', 'le'):
            for layout in ('hi', 'lo'):
                def gen(ki, fr, kb_len=kb_len, wordn=wordn, rounds=rounds, order=order, layout=layout):
                    kb = ki.to_bytes(8, 'big')
                    if kb_len == 16: kb = kb * 2
                    elif kb_len == 12: kb = kb + b'\0' * 4
                    elif kb_len == 8 and wordn == 24: kb = kb  # 8 bytes for 24-bit words? m=int(64/24) invalid
                    elif kb_len == 6: kb = kb[:6]
                    elif kb_len == 4: kb = kb[:4]
                    if len(kb) * 8 % wordn: return None
                    try:
                        enc = speck_correct(kb, wordn, rounds)
                    except Exception:
                        return None
                    n = wordn
                    out = b''
                    for i in range(2):
                        if layout == 'hi':
                            x, y = fr & (M32 >> (32 - n)) if n <= 32 else fr, i
                        else:
                            x, y = i, fr & ((1 << n) - 1)
                        x, y = enc(x & ((1 << n) - 1), y & ((1 << n) - 1))
                        out += (x.to_bytes(n // 8, 'little') + y.to_bytes(n // 8, 'little'))
                    return out
                check('speck k%d w%d r%d %s %s' % (kb_len * 8, wordn, rounds, order, layout), gen)

# ---------- RC5 ----------
def rc5(key_int, frame, r=12, wordn=32, rounds_out=2):
    M = (1 << wordn) - 1
    w = wordn // 8
    keyb = key_int.to_bytes(8, 'big')
    c = 2
    L = [int.from_bytes(keyb[0:4], 'big'), int.from_bytes(keyb[4:8], 'big')]
    t = 2 * (r + 1)
    S = [0x9e3779b9]
    for i in range(1, t):
        S.append((S[-1] + 0x9e3779b9) & M32)
    A = B = i = j = 0
    v = 3 * max(c, t)
    LL = L[:]
    for _ in range(v):
        A = S[i] = rotl((S[i] + A + B) & M32, 3)
        B = LL[j] = rotl((LL[j] + A + B) & M32, (A + B) & 31)
        i = (i + 1) % t
        j = (j + 1) % c
    def E(x, y):
        A = (x + S[0]) & M32
        B = (y + S[1]) & M32
        for i in range(1, r + 1):
            A = (rotl(A ^ B, B & 31) + S[2 * i]) & M32
            B = (rotl(B ^ A, A & 31) + S[2 * i + 1]) & M32
        return A, B
    out = b''
    for i in range(2):
        a, b = E(frame & M32, i)
        out += struct.pack('>II', a, b)
    return out

# ---------- AES / DES / etc via pycryptodome ----------
def lib_battery():
    try:
        from Crypto.Cipher import AES, DES, DES3, Blowfish, ARC2, ARC4, ChaCha20, Salsa20
    except ImportError:
        print('no pycryptodome'); return
    kb8a = bytes.fromhex('0123456789abcdef')

    def keybytes(ki): return ki.to_bytes(8, 'big')

    def try_desc(name, f):
        def gen(ki, fr):
            try:
                return f(keybytes(ki), fr)
            except Exception:
                return None
        check(name, gen)

    # DES-ECB of counters
    for ivmod in ('frame_iv', 'frame_ctr', 'zero_ctr'):
        def d_ofb(kb, fr, ivmod=ivmod):
            c = DES.new(kb, DES.MODE_ECB)
            iv = fr.to_bytes(8, 'big')
            if ivmod == 'frame_iv':
                return c.encrypt(bytes(16))  # ECB of zeros first
            if ivmod == 'frame_ctr':
                out = b''
                x = fr
                for i in range(2):
                    out += c.encrypt(x.to_bytes(8, 'big')); x += 1
                return out
            out = b''
            for i in range(2):
                out += c.encrypt(i.to_bytes(8, 'big'))
            return out
        try_desc('DES/%s' % ivmod, d_ofb)

    # DES-OFB/CFB with IV=frame
    def des_ofb(kb, fr):
        return DES.new(kb, DES.MODE_OFB, iv=fr.to_bytes(8, 'big')).encrypt(bytes(16))
    try_desc('DES/OFB/iv=frame', des_ofb)
    def des_cfb(kb, fr):
        return DES.new(kb, DES.MODE_CFB, iv=fr.to_bytes(8, 'big'), segment_size=64).encrypt(bytes(16))
    try_desc('DES/CFB64/iv=frame', des_cfb)
    def des_ctr(kb, fr):
        from Crypto.Util import Counter
        ctr = Counter.new(64, initial_value=fr)
        return DES.new(kb, DES.MODE_CTR, counter=ctr).encrypt(bytes(16))
    try_desc('DES/CTR/iv=frame', des_ctr)

    # AES with various key derivations
    kdfs = {
        'rep16': lambda kb, fr: kb * 2,
        'pad16': lambda kb, fr: kb + bytes(8),
        'padpre': lambda kb, fr: bytes(8) + kb,
        'kb+fr': lambda kb, fr: kb + fr.to_bytes(8, 'big'),
        'fr+kb': lambda kb, fr: fr.to_bytes(8, 'big') + kb,
        'md5kb': lambda kb, fr: hashlib.md5(kb).digest(),
        'md5kbfr': lambda kb, fr: hashlib.md5(kb + fr.to_bytes(8, 'big')).digest(),
        'sha256kb': lambda kb, fr: hashlib.sha256(kb).digest(),
        'sha256kbfr': lambda kb, fr: hashlib.sha256(kb + fr.to_bytes(8, 'big')).digest(),
    }
    for kname, kd in kdfs.items():
        def aes_ecb(kb, fr, kd=kd):
            K = kd(kb, fr)
            c = AES.new(K[:16] if len(K) >= 16 else K.ljust(16, b'\0'), AES.MODE_ECB)
            out = b''
            x = fr
            for i in range(2):
                blk = (x).to_bytes(16, 'big')
                out += c.encrypt(blk); x += 1
            return out
        def aes_ecb_zero(kb, fr, kd=kd):
            K = kd(kb, fr)
            c = AES.new(K[:16] if len(K) >= 16 else K.ljust(16, b'\0'), AES.MODE_ECB)
            return c.encrypt(bytes(16)) + c.encrypt((1).to_bytes(16, 'big'))
        def aes_ctr(kb, fr, kd=kd):
            K = kd(kb, fr)
            from Crypto.Util import Counter
            ctr = Counter.new(128 - 22, prefix=b'', initial_value=0) if False else None
            c = AES.new(K[:16], AES.MODE_CTR, nonce=fr.to_bytes(8, 'big'))
            return c.encrypt(bytes(16))
        try_desc('AES/%s/ctr_frame8' % kname, aes_ctr)
        try_desc('AES/%s/ecb_ctr' % kname, aes_ecb)
        try_desc('AES/%s/ecb_zero' % kname, aes_ecb_zero)

    # RC4 keys
    rc4keys = {
        'kb': lambda kb, fr: kb,
        'kb+fr': lambda kb, fr: kb + fr.to_bytes(8, 'big'),
        'fr+kb': lambda kb, fr: fr.to_bytes(8, 'big') + kb,
        'md5': lambda kb, fr: hashlib.md5(kb + fr.to_bytes(8, 'big')).digest(),
        'sha256': lambda kb, fr: hashlib.sha256(kb + fr.to_bytes(8, 'big')).digest(),
        'kborfr': lambda kb, fr: bytes(a ^ b for a, b in zip(kb, fr.to_bytes(8, 'big'))),
    }
    for rname, rk in rc4keys.items():
        def rc4gen(kb, fr, rk=rk):
            key = rk(kb, fr)
            S = list(range(256)); j = 0
            for i in range(256):
                j = (j + S[i] + key[i % len(key)]) % 256
                S[i], S[j] = S[j], S[i]
            i = j = 0; out = bytearray()
            for _ in range(16):
                i = (i + 1) % 256; j = (j + S[i]) % 256
                S[i], S[j] = S[j], S[i]
                out.append(S[(S[i] + S[j]) % 256])
            return bytes(out)
        try_desc('RC4/%s' % rname, rc4gen)

    # ChaCha20 / Salsa20 with 16-byte key
    def chacha(kb, fr):
        return ChaCha20.new(key=kb * 2, nonce=fr.to_bytes(8, 'big')).encrypt(bytes(16))
    def chacha12(kb, fr):
        return ChaCha20.new(key=kb * 2, nonce=fr.to_bytes(12, 'big')).encrypt(bytes(16))
    def salsa(kb, fr):
        return Salsa20.new(key=kb * 2, nonce=fr.to_bytes(8, 'big')).encrypt(bytes(16))
    try_desc('ChaCha20/k16/n8', chacha)
    try_desc('ChaCha20/k16/n12', chacha12)
    try_desc('Salsa20/k16/n8', salsa)

    # Blowfish ECB counter
    def bf(kb, fr):
        c = Blowfish.new(kb, Blowfish.MODE_ECB)
        out = b''
        x = fr
        for i in range(4):
            out += c.encrypt(x.to_bytes(8, 'big')); x += 1
        return out
    try_desc('Blowfish/ECB/ctr', bf)

if __name__ == '__main__':
    print('battery start')
    arx_battery()
    speck_battery()
    def rc5gen(ki, fr):
        return rc5(ki, fr)
    check('RC5/32/12/16', rc5gen)
    lib_battery()
    print('done. hits:', hits)
