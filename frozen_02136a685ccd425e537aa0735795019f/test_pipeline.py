#!/usr/bin/env python3
"""Test the repair pipeline on synthetic data (true D known)."""
import math, random, struct, sys
import numpy as np
from repair_lib import N, node_sizes, nleaves

def fft(a):
    n = len(a); k = np.arange(n)
    M = np.exp(1j*math.pi*np.outer(k, 2*np.arange(n)+1)/n)
    return np.asarray(a, dtype=complex) @ M
def splitfft(F):
    n = len(F); h = n//2
    rho = np.exp(1j*math.pi*(2*np.arange(n)+1)/n)
    return 0.5*(F[:h]+F[h:]), (F[:h]-F[h:])/(2*rho[:h])
def _T(E):
    n = len(E)
    if n == 1: return [float(np.real(E[0]))]
    Ee, Eo = splitfft(E)
    L = np.conj(Eo)/Ee
    return [L, _T(Ee), _T(Ee - L*np.conj(L)*Ee)]
def flatten(t):
    nodes, leaves = [], []
    def rec(x):
        if isinstance(x[0], float): leaves.extend(x); return
        nodes.append(x[0]); rec(x[1]); rec(x[2])
    rec(t); return nodes, leaves
def pmul(a, b):
    r = [0]*N
    for i, ai in enumerate(a):
        if ai:
            for j, bj in enumerate(b):
                if bj:
                    k = i+j
                    if k >= N: r[k-N] -= ai*bj
                    else: r[k] += ai*bj
    return r
def padj(a): return [a[0]] + [-a[N-i] for i in range(1, N)]
def corrupt(blob, rho10=0.01, rho01=0.001, seed=7):
    rng = random.Random(seed)
    flipbits = list(range(56)) + [63]
    out = bytearray(blob)
    for di in range(len(blob)//8):
        x = int.from_bytes(out[8*di:8*di+8], "little")
        for bit in flipbits:
            if (x >> bit) & 1:
                if rng.random() < rho10: x ^= 1 << bit
            elif rng.random() < rho01:
                x ^= 1 << bit
        out[8*di:8*di+8] = x.to_bytes(8, "little")
    return bytes(out)

def make(seed=1, rho10=0.01, cseed=7):
    rng = random.Random(seed)
    f = [int(round(rng.gauss(0, 19.16))) for _ in range(N)]
    g = [int(round(rng.gauss(0, 19.16))) for _ in range(N)]
    D = [a+b for a, b in zip(pmul(f, padj(f)), pmul(g, padj(g)))]
    G00 = fft(f)*np.conj(fft(f)) + fft(g)*np.conj(fft(g))
    nodes, leaves = flatten(_T(G00))
    vals = []
    for nd in nodes:
        vals += [float(v.real) for v in nd] + [float(v.imag) for v in nd]
    vals += [float(v) for v in leaves]
    blob = struct.pack("<%dd" % len(vals), *vals)
    cb = corrupt(blob, rho10=rho10, seed=cseed)
    data = np.array(struct.unpack("<%dd" % (len(cb)//8), cb))
    true = np.array(vals)
    return data, np.array(D), true

if __name__ == "__main__":
    for cseed in (7, 11, 23):
        data, Dtrue, true = make(cseed=cseed)
        print("=== corruption seed", cseed, " clean doubles %.1f%%"
              % (100*(data == true).mean()))
        tree = Tree(data, 0, 2*sum(SZ))
        rep, mag = quad_repair(tree, data, verbose=True)
        bad = int((rep != true[2*sum(SZ):2*sum(SZ)+NL]).sum())
        print("  leaves wrong:", bad, "/", NL)
        E = compute(tree, data, rep, mag)
        x, im = tree_to_D(E)
        err = np.abs(x - Dtrue)
        print("  D err max %.4g  #>0.5 %d  exact-int %d  |Im D| %.3g"
              % (err.max(), (err > 0.5).sum(), int((np.abs(x-np.round(x)) < 1e-6).sum()), im))
