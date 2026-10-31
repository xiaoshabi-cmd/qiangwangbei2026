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

def norm(P):
    return max(abs(cen(c)) for c in P.coeffs())

def P(lst):
    return ctx([int(v) % p for v in lst])

# known LWE indices from flag prefix "flag{"
known = [0,3,4,7,8,11,13,14,16,19,20,21,22,23,24,27,28,29,30,31,32,36,38,39]
print("known LWE indices:", known)

a = {i: P(samples[i][0]) for i in known}
b = {i: P(samples[i][1]) for i in known}
one = ctx([1])

print("\n--- test 1: e == 0 ?   b_i*a_j - b_j*a_i == 0")
for (i,j) in [(0,3),(0,4),(3,4),(7,8)]:
    v = (b[i]*a[j] - b[j]*a[i]) % f
    print("  (%d,%d) zero=%s maxcoef=%d" % (i,j, v.is_zero(), norm(v)))

print("\n--- test 2: s == e ?   b_i*(a_j+1) - b_j*(a_i+1) == 0")
for (i,j) in [(0,3),(0,4),(3,4),(7,8)]:
    v = (b[i]*(a[j]+one) - b[j]*(a[i]+one)) % f
    print("  (%d,%d) zero=%s maxcoef=%d" % (i,j, v.is_zero(), norm(v)))

print("\n--- test 3: uniform-difference sanity (should be big): b_i*a_j - b_j*a_i for UNIFORM samples")
ui = [1,2,5,6]   # 'f'=0x66 -> bits 1,2,5,6 are 1 -> F1 uniform
au = {i: P(samples[i][0]) for i in ui}
bu = {i: P(samples[i][1]) for i in ui}
for (i,j) in [(1,2),(1,5)]:
    v = (bu[i]*au[j] - bu[j]*au[i]) % f
    print("  (%d,%d) maxcoef=%d" % (i,j, norm(v)))
