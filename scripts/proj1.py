import pickle, sys
from flint import fmpz_mod_poly_ctx, fmpz_mat

p = 0x3ac01f87
ctx = fmpz_mod_poly_ctx(p)
facs = [ctx(fc) for fc in pickle.load(open("factors.pkl", "rb"))]
samples = pickle.load(open("samples.pkl", "rb"))

# indices guaranteed to be LWE samples: bit index == 0 mod 8 (MSB of each ASCII byte)
I = list(range(0, len(samples), 8))
m = len(I)
print("m =", m, "samples used;", "total samples", len(samples))

def horner(coefs, r):
    v = 0
    for c in reversed(coefs):
        v = (v * r + c) % p
    return v

def cen(v):
    return v - p if v > p // 2 else v

lin = [(-int(g.coeffs()[0])) % p for g in facs if g.degree() == 1]

res = []
for ri, r in enumerate(lin):
    A = [horner(samples[i][0], r) for i in I]
    B = [horner(samples[i][1], r) for i in I]
    # Kannan embedding: rows [A | 0], [p*e_j | 0], [B | 1]
    rows = [list(A) + [0]]
    for j in range(m):
        row = [0] * (m + 1)
        row[j] = p
        rows.append(row)
    rows.append(list(B) + [1])
    M = fmpz_mat(rows)
    R = M.lll()
    best = None
    for k in range(R.nrows()):
        row = [int(R[k, j]) for j in range(m + 1)]
        if abs(row[-1]) != 1:
            continue
        n = sum(x * x for x in row[:-1]) ** 0.5
        if best is None or n < best[0]:
            best = (n, row)
    res.append((best[0] if best else float('inf'), ri, r))

res.sort()
print("smallest found error norms (d=1 projections):")
for n, ri, r in res[:10]:
    print("  root idx %3d  r=%11d  ||e||=%.4g" % (ri, r, n))
print("median:", res[len(res)//2][0], " max:", res[-1][0])
