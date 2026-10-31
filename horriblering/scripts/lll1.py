import pickle, re, sys, time
from flint import fmpz_mod_poly_ctx, fmpz_mat

p = 0x3ac01f87
N = 512
ctx = fmpz_mod_poly_ctx(p)
samples = pickle.load(open("samples.pkl", "rb"))

src = open("task.sage").read()
line = [l for l in src.splitlines() if l.startswith("f = x^512")][0]
expr = line.split("=", 1)[1].strip()
coeffs = [0] * 513
for term in expr.split("+"):
    term = term.strip()
    if not term:
        continue
    m = re.fullmatch(r"(?:(\d+)\s*\*\s*)?x(?:\^(\d+))?", term)
    if m:
        c = int(m.group(1)) if m.group(1) else 1
        d = int(m.group(2)) if m.group(2) else 1
        coeffs[d] += c
    else:
        coeffs[0] += int(term)
f = ctx(coeffs)
fc = [int(c) for c in f.coeffs()]

def cen(v):
    v = int(v)
    return v - p if v > p // 2 else v

def mulmod(ac, bc):
    """multiply two polys (lists, low->high) mod f, over GF(p)"""
    res = [0] * (len(ac) + len(bc) - 1)
    for i, ai in enumerate(ac):
        if ai:
            for j, bj in enumerate(bc):
                res[i + j] = (res[i + j] + ai * bj) % p
    # reduce
    for k in range(len(res) - 1, N - 1, -1):
        c = res[k]
        if c:
            res[k] = 0
            for j in range(N):
                res[k - N + j] = (res[k - N + j] - c * fc[j]) % p
    return res[:N]

def build(idx):
    a = [int(v) % p for v in samples[idx][0]]
    b = [int(v) % p for v in samples[idx][1]]
    # columns of M_a : a * x^j mod f
    cols = []
    t = a[:]
    for j in range(N):
        cols.append(t[:])
        # t = t * x mod f
        new = [0] * (N + 1)
        for i in range(N):
            new[i + 1] = t[i]
        c = new[N]
        new[N] = 0
        if c:
            for i in range(N):
                new[i] = (new[i] - c * fc[i]) % p
        t = new[:N]
    return cols, b, a

def solve(idx, alpha=1):
    cols, b, a = build(idx)
    rows = []
    for j in range(N):
        row = [0] * (2 * N + 1)
        row[j] = 1
        for k in range(N):
            row[N + k] = (-cols[j][k]) % p
        rows.append(row)
    for k in range(N):
        row = [0] * (2 * N + 1)
        row[N + k] = p
        rows.append(row)
    row = [0] * (2 * N + 1)
    for k in range(N):
        row[N + k] = b[k]
    row[2 * N] = alpha
    rows.append(row)
    t0 = time.time()
    R = fmpz_mat(rows).lll()
    dt = time.time() - t0
    best = None
    for r in range(R.nrows()):
        v = [int(R[r, c]) for c in range(2 * N + 1)]
        if abs(v[-1]) != alpha:
            continue
        n = max(abs(x) for x in v[:-1])
        if best is None or n < best[0]:
            best = (n, v)
    return best, dt, a, b, cols

if __name__ == "__main__":
    for idx in [int(x) for x in sys.argv[1:]] or [0]:
        best, dt, a, b, cols = solve(idx)
        print("sample %d: LLL %.1fs" % (idx, dt))
        if best is None:
            print("  no vector with last coord = alpha")
        else:
            n, v = best
            print("  best: max|coef| = %d" % n)
            s = v[:N]
            e = v[N:2 * N]
            print("  max|s| = %d, max|e| = %d" % (max(abs(x) for x in s), max(abs(x) for x in e)))
            if max(abs(x) for x in s) < 10 ** 6:
                chk = [(x % p) for x in s]
                lhs = mulmod([x % p for x in a], chk)
                ok = all((lhs[k] + e[k]) % p == b[k] % p for k in range(N))
                print("  verify a*s+e==b :", ok)
