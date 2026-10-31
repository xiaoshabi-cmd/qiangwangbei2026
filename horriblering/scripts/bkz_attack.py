import os
import random
import subprocess
import sys
import time
from pathlib import Path
from flint import fmpz_mat
from lll1 import N, p, samples, build, mulmod

ROOT = Path(__file__).resolve().parent
FPLLL = ROOT / ".deps" / "install" / "bin" / "fplll.exe"


def write_matrix(path, rows):
    with open(path, "w") as fh:
        fh.write("[")
        for i, row in enumerate(rows):
            fh.write((" " if i else "") + "[" + " ".join(map(str, row)) + "]\n")
        fh.write("]\n")


def read_matrix(path):
    rows = []
    for line in open(path):
        line = line.strip()
        if not line or line in "[]":
            continue
        line = line.replace("[", "").replace("]", "")
        if line.strip():
            rows.append(list(map(int, line.split())))
    return rows


def make_lattice(a, b):
    cols = []
    from lll1 import fc
    t = a[:]
    for _ in range(N):
        cols.append(t[:])
        new = [0] * (N + 1)
        for i in range(N):
            new[i + 1] = t[i]
        c = new[N]
        if c:
            for i in range(N):
                new[i] = (new[i] - c * fc[i]) % p
        t = new[:N]
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
    row[N:2 * N] = b
    row[-1] = 1
    rows.append(row)
    return rows


def toy(seed=7):
    random.seed(seed)
    def gauss():
        return [int(random.gauss(0, 3.371)) for _ in range(N)]
    s, e = gauss(), gauss()
    a = [random.randrange(p) for _ in range(N)]
    product = mulmod(a, [x % p for x in s])
    b = [(x + y) % p for x, y in zip(product, e)]
    return a, b, s, e


def run_bkz(a, b, block, tag):
    source = ROOT / (tag + ".lat")
    target = ROOT / (tag + ".reduced.lat")
    started = time.time()
    reduced = fmpz_mat(make_lattice(a, b)).lll()
    rows = [[int(reduced[i, j]) for j in range(2 * N + 1)] for i in range(2 * N + 1)]
    print("FLINT LLL time:", time.time() - started, flush=True)
    write_matrix(source, rows)
    env = os.environ.copy()
    env["PATH"] = r"C:\msys64\usr\bin;C:\msys64\mingw64\bin;" + env["PATH"]
    started = time.time()
    with open(target, "w") as out:
        proc = subprocess.run([str(FPLLL), "-a", "bkz", "-b", str(block), "-nolll", str(source)],
                              stdout=out, env=env)
    print("BKZ", block, "return", proc.returncode, "time", time.time() - started, flush=True)
    if proc.returncode:
        return None
    best = None
    for row in read_matrix(target):
        if len(row) == 2 * N + 1 and abs(row[-1]) == 1:
            score = max(map(abs, row[:-1]))
            if best is None or score < best[0]:
                best = (score, row)
    if best:
        print("best max coefficient:", best[0], flush=True)
        if best[0] <= 40:
            sign = best[1][-1]
            s = [x * sign for x in best[1][:N]]
            e = [x * sign for x in best[1][N:2 * N]]
            product = mulmod(a, [x % p for x in s])
            ok = all((product[i] + e[i] - b[i]) % p == 0 for i in range(N))
            print("RLWE verification:", ok, flush=True)
            if ok:
                return s, e
    return None


if __name__ == "__main__":
    import threading
    pulse_started = time.time()
    def pulse():
        while True:
            time.sleep(2)
            print("working, elapsed %.0fs" % (time.time() - pulse_started), flush=True)
    threading.Thread(target=pulse, daemon=True).start()
    print("starting lattice attack", flush=True)
    block = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    is_toy = len(sys.argv) > 2 and sys.argv[2] == "toy"
    if is_toy:
        a, b, true_s, true_e = toy()
        result = run_bkz(a, b, block, "toy_bkz")
        print("toy exact:", result is not None and result[0] == true_s and result[1] == true_e)
    else:
        indices = [int(sys.argv[2])] if len(sys.argv) > 2 else range(len(samples))
        for i in indices:
            print("sample", i, flush=True)
            a, b = samples[i]
            a = list(map(int, a)) + [0] * (N - len(a))
            b = list(map(int, b)) + [0] * (N - len(b))
            result = run_bkz(a, b, block, "sample_%d_bkz" % i)
            if result:
                print("RECOVERED SAMPLE", i, flush=True)
                break
