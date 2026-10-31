"""Shared repair utilities for the frozen tree dump."""
import math
import numpy as np

N = 128

def node_sizes(n):
    if n == 1: return []
    return [n//2] + node_sizes(n//2) + node_sizes(n//2)

def nleaves(n):
    return 1 if n == 1 else 2*nleaves(n//2)

class Node:
    __slots__ = ("idx", "n", "sz", "off", "left", "right", "lo", "hi")
    def __init__(self, idx, n):
        self.idx = idx; self.n = n; self.sz = n//2
        self.left = None; self.right = None

class Leaf:
    __slots__ = ("slot",)
    def __init__(self, slot): self.slot = slot

def build_tree(data, start, loff, sizes):
    """sizes = flat list of L-sizes in preorder for this subtree"""
    offs = []
    o = 0
    for sz in sizes:
        offs.append(o); o += 2*sz
    class Ctx: pass
    def build(i, n, l):
        if n == 1:
            return Leaf(l), i, l + 1
        nd = Node(i, n); nd.off = loff + offs[i]
        a, nxt, ll = build(i + 1, n//2, l)
        b, nxt, ll = build(nxt, n//2, ll)
        nd.left, nd.right = a, b
        return nd, nxt, ll
    root, nxt, ll = build(0, N, 0)
    assert nxt == len(sizes)
    return root, offs, o

def raw_L(data, nd):
    o = nd.off; sz = nd.sz
    return data[o:o+sz] + 1j*data[o+sz:o+2*sz]

def t_obs(data, nd):
    L = raw_L(data, nd)
    rho = np.exp(1j*np.pi*(2*np.arange(nd.sz)+1)/nd.n)
    out = []
    for comp in (0, 1):
        r = rho.real if comp == 0 else rho.imag
        v = L.real if comp == 0 else L.imag
        w = np.abs(r); safe = w > 1e-12
        e = np.where(safe, v/np.where(safe, r, 1.0), 0.0)
        out.append((e, w, safe))
    return out

def leaves_under(x):
    if isinstance(x, Leaf): return [x.slot]
    return leaves_under(x.left) + leaves_under(x.right)

def nodes_list(root):
    out = []
    def rec(x):
        if isinstance(x, Leaf): return
        out.append(x); rec(x.left); rec(x.right)
    rec(root)
    return out
