import pickle, re
p = 0x3ac01f87
N = 512

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
fc = coeffs[:N]      # f = x^N + sum fc[i] x^i

def cen(v):
    return v - p if v > p // 2 else v

def mulx(t):
    new = [0] * (N + 1)
    for i in range(N):
        new[i + 1] = t[i]
    c = new[N]
    new[N] = 0
    if c:
        for i in range(N):
            new[i] = (new[i] - c * fc[i]) % p
    return new[:N]

t = [0] * N
t[1] = 1   # x
best = []
for k in range(1, 3001):
    if k > 1:
        t = mulx(t)
    mx = max(abs(cen(v)) for v in t)
    nz = sum(1 for v in t if v)
    best.append((mx, k, nz))
    if k <= 3 or k % 500 == 0:
        print("k=%4d maxcoef=%d nonzero=%d" % (k, mx, nz))

best.sort()
print("\nsmallest max|coef| of x^k mod f:")
for mx, k, nz in best[:12]:
    print("  k=%4d maxcoef=%d nonzero=%d" % (k, mx, nz))
