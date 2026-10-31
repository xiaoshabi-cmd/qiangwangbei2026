import pickle, re
from flint import fmpz_mod_poly_ctx

p = 0x3ac01f87
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

def cen(v):
    v = int(v)
    return v - p if v > p // 2 else v

def mx(P):
    return max(abs(cen(c)) for c in P.coeffs())

def P(lst):
    return ctx([int(v) % p for v in lst])

known = [0,3,4,7,8,11,13,14,16,19,20,21,22,23,24,27,28,29,30,31,32,36,38,39]
one = ctx([1])

print("candidate test: is (a + c)^-1 * b small ?  (small => b = s*(a+c))")
for c in [0,1,-1,2,-2,3]:
    cc = ctx([int(c) % p])
    for i in known[:5]:
        a = P(samples[i][0]); b = P(samples[i][1])
        t = (a + cc) % f
        if t.is_zero():
            continue
        try:
            inv = t.inverse_mod(f)
        except Exception:
            print("  c=%d i=%d not invertible" % (c,i)); continue
        r = (inv * b) % f
        print("  c=%+d i=%2d maxcoef=%d" % (c, i, mx(r)))
    print()
