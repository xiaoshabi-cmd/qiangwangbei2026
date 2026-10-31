import pickle, math
from collections import Counter, defaultdict
from flint import fmpz_mod_poly_ctx

p = 0x3ac01f87
ctx = fmpz_mod_poly_ctx(p)
facs = [ctx(fc) for fc in pickle.load(open("factors.pkl", "rb"))]
cset = {tuple(int(c) for c in g.coeffs()) for g in facs}

byd = defaultdict(list)
for g in facs:
    byd[g.degree()].append(g)

# 1) self-reciprocal factors
print("=== self-reciprocal factors ===")
n = 0
for g in facs:
    cc = [int(c) for c in g.coeffs()]
    d = len(cc) - 1
    if all(cc[i] == cc[d - i] for i in range(d + 1)):
        print(" deg", d, g)
        n += 1
print("count:", n)

# 2) scaling orbits: g2(x) = c^{-d} g1(c x)  -> from x^{d-1} coeff solve c, verify
print("=== scaling pairs g2 = norm(c^-d g1(c x)) ===")
found = []
for d, gs in byd.items():
    for i1 in range(len(gs)):
        for i2 in range(len(gs)):
            if i1 == i2:
                continue
            g1, g2 = gs[i1], gs[i2]
            c1 = [int(v) for v in g1.coeffs()]
            c2 = [int(v) for v in g2.coeffs()]
            if d >= 2:
                # coefficient of x^{d-1}: c^{1-d} * g1_{d-1} = g2_{d-1}
                den = c1[d-1]
                num = c2[d-1]
                if den == 0:
                    continue
                # c^{d-1} = den/num
                t = den * pow(num, p-2, p) % p
                e = d - 1
                if math.gcd(e, p-1) != 1:
                    continue
                c = pow(t, pow(e, -1, p-1), p)
            else:
                continue
            # verify: c^{-d} g1(c x) == g2
            cp = 1
            out = []
            ok = True
            cinv = pow(c, p-2, p)
            cpow = pow(c, p-2, p)  # c^{-1}
            for k in range(d+1):
                # coeff of x^k in g1(c x) is c1[k]*c^k ; scaled by c^{-d}
                val = c1[k] * pow(c, k, p) % p * pow(c, p-1-d, p) % p
                if val != c2[k]:
                    ok = False
                    break
            if ok:
                found.append((d, c, g1, g2))
print("scaling pairs:", len(found))
for f in found[:10]:
    print("  deg", f[0], "c =", f[1])

# 3) translation orbits: g2(x) = g1(x + c)
print("=== translation pairs g2 = g1(x+c) ===")
tfound = []
x = ctx([0, 1])
for d, gs in byd.items():
    if d < 2:
        continue
    for i1 in range(len(gs)):
        for i2 in range(len(gs)):
            if i1 == i2:
                continue
            g1, g2 = gs[i1], gs[i2]
            c1 = [int(v) for v in g1.coeffs()]
            c2 = [int(v) for v in g2.coeffs()]
            # from x^{d-1} coeff: g1_{d-1} + d*c = g2_{d-1}
            c = (c2[d-1] - c1[d-1]) % p * pow(d, p-2, p) % p
            # verify g1(x + c) == g2
            acc = ctx([0])
            for k in range(d, -1, -1):
                acc = acc * (x + ctx([c])) + ctx([c1[k]])
            if tuple(int(v) for v in acc.coeffs()) == tuple(int(v) for v in g2.coeffs()):
                tfound.append((d, c, g1, g2))
print("translation pairs:", len(tfound))
for f in tfound[:10]:
    print("  deg", f[0], "c =", f[1])
