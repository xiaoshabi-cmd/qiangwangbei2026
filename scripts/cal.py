import random, time, math
from flint import fmpz_mod_poly_ctx, fmpz_mat

p = 0x3ac01f87
ctx = fmpz_mod_poly_ctx(p)
sigma = 3.371

def gauss():
    # discrete gaussian approx: sum of 3 uniforms - simple, or use rejection
    while True:
        v = int(random.gauss(0, sigma))
        if abs(v) < 8 * sigma:
            return v

def mulmod(ac, bc, fc, N):
    res = [0] * (len(ac) + len(bc) - 1)
    for i, ai in enumerate(ac):
        if ai:
            for j, bj in enumerate(bc):
                res[i + j] = (res[i + j] + ai * bj) % p
    for k in range(len(res) - 1, N - 1, -1):
        c = res[k]
        if c:
            res[k] = 0
            for j in range(N):
                res[k - N + j] = (res[k - N + j] - c * fc[j]) % p
    return res[:N]

def test(n, alpha=1):
    # random monic f of degree n = product of random linear factors (reducible)
    roots = [random.randrange(p) for _ in range(n)]
    poly = ctx([1])
    for r in roots:
        poly = poly * ctx([(-r) % p, 1])
    fc = [int(c) for c in poly.coeffs()]
    s = [gauss() % p for _ in range(n)]
    e = [gauss() % p for _ in range(n)]
    a = [random.randrange(p) for _ in range(n)]
    as_ = mulmod(a, s, fc, n)
    b = [(as_[k] + e[k]) % p for k in range(n)]
    # columns
    cols = []
    t = a[:]
    for j in range(n):
        cols.append(t[:])
        new = [0] * (n + 1)
        for i in range(n):
            new[i + 1] = t[i]
        c = new[n]
        new[n] = 0
        if c:
            for i in range(n):
                new[i] = (new[i] - c * fc[i]) % p
        t = new[:n]
    rows = []
    for j in range(n):
        row = [0] * (2 * n + 1)
        row[j] = 1
        for k in range(n):
            row[n + k] = (-cols[j][k]) % p
        rows.append(row)
    for k in range(n):
        row = [0] * (2 * n + 1)
        row[n + k] = p
        rows.append(row)
    row = [0] * (2 * n + 1)
    for k in range(n):
        row[n + k] = b[k]
    row[2 * n] = alpha
    rows.append(row)
    t0 = time.time()
    R = fmpz_mat(rows).lll()
    dt = time.time() - t0
    best = None
    for r in range(R.nrows()):
        v = [int(R[r, c]) for c in range(2 * n + 1)]
        if abs(v[-1]) != alpha:
            continue
        mx = max(abs(x) for x in v[:-1])
        if best is None or mx < best[0]:
            best = (mx, v)
    tgt = max(max(abs(x) for x in s), max(abs(x) for x in e))
    GH = math.sqrt(2 * n / (2 * math.pi * math.e)) * math.sqrt(p)
    print("n=%3d dim=%4d  LLL %6.1fs  real max|s,e|=%3d  found max=%s  gap=%.0f" %
          (n, 2 * n + 1, dt, tgt, ("%d" % best[0]) if best else "none", GH / (sigma * math.sqrt(2 * n))))

for n in [16, 32, 64, 128]:
    test(n)
