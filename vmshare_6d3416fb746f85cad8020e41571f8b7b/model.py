M32 = 0xFFFFFFFF
M16 = 0xFFFF

# constants
C = [0x1357,0x2468,0x369c,0x48ad,0x5be1,0x6cf2,0x7d03,0x8e14,
     0x9f25,0xa036,0xb147,0xc258,0xd369,0xe47a,0xf58b,0x069c]
IV = bytes(b"SIMD_TINY_BLOCK_IS_A_NIGHTMARE!!")
S0 = [IV[2*j] | (IV[2*j+1] << 8) for j in range(16)]


def prng(val, seed):
    """function @0x1c60 : (val & 0xffffff) ^ seed -> 8 uint16 words"""
    s = ((val & 0xFFFFFF) ^ seed) & M32
    s ^= s >> 13
    s = (s * 0x45d9f3b) & M32
    s ^= s >> 16
    out = []
    acc = 0
    for _ in range(8):
        s = (s + acc + 0x9E3779B9) & M32   # lea eax,[rax+rsi-0x61c88647]
        acc = (acc + 0x7f4a7c15) & M32
        t = s ^ (s >> 13)
        t = (t * 0x85ebca6b) & M32
        t = t ^ (t >> 16)
        u = t ^ (t >> 16)
        out.append(u & M16)
        s = t
    return out


def rotl16(x, k):
    return ((x << k) | (x >> (16 - k))) & M16


def rotr16(x, k):
    return ((x >> k) | (x << (16 - k))) & M16


def rnd(y, w, c):
    y ^= y >> 5
    y = (w + c + rotl16(y, 3)) & M16
    y ^= y >> 7
    return rotl16(y, 9)


def inv_xor_shr(y, k):
    """invert y = x ^ (x >> k)  for 16-bit"""
    x = y
    for _ in range(3):
        x = y ^ (x >> k)
    return x & M16


def rnd_inv(y, w, c):
    y = rotr16(y, 9)
    y = inv_xor_shr(y, 7)
    y = rotr16((y - w - c) & M16, 3)
    return inv_xor_shr(y, 5)


def simd_block(state, words):
    """function @0x1cc0 : 16 lanes, 8 rounds"""
    s = list(state)
    for i in range(8):
        w = words[i]
        s = [rnd(s[j], w, C[j]) for j in range(16)]
    return s


def simd_block_inv(state, words):
    s = list(state)
    for i in range(7, -1, -1):
        w = words[i]
        s = [rnd_inv(s[j], w, C[j]) for j in range(16)]
    return s


def encrypt(X, Y):
    b1 = prng(X, 0x31415926)
    b2 = prng(Y, 0x27182818)
    st = simd_block(S0, b1)
    st = simd_block(st, b2)
    out = bytearray(32)
    for j in range(16):
        out[2*j] = st[j] & 0xFF
        out[2*j+1] = (st[j] >> 8) & 0xFF
    return bytes(out)


if __name__ == "__main__":
    import sys
    if len(sys.argv) == 3:
        print(encrypt(int(sys.argv[1], 16), int(sys.argv[2], 16)).hex())
    else:
        # self test of round trip
        import random
        random.seed(1)
        for _ in range(200):
            st = [random.randrange(65536) for _ in range(16)]
            ws = [random.randrange(65536) for _ in range(8)]
            assert simd_block_inv(simd_block(st, ws), ws) == st
        for k in (5, 7):
            for _ in range(1000):
                x = random.randrange(65536)
                y = x ^ (x >> k)
                assert inv_xor_shr(y, k) == x
        print("self-test ok")
