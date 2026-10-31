#!/usr/bin/env python3
"""
frozen: recover D = f*adj(f) + g*adj(g) from the corrupted LDL-tree dump.

Structure: L_j = t_j*rho_j (t real, anti-palindromic), E = [A(1+t), A(1-t)],
child2 array B = A(1-t^2), t=0 for n=2, G00 = E(root) = FFT(D).

Repair pipeline:
 1. n=4 "quads": hypothesis testing on 4 leaves + 4 |t|^2 observations.
 2. leftovers resolved one level up (parent relation), which is a linear
    equation for the quad's single free parameter v.
 3. D = ifft(E) must be integral -> final check.
"""
import math, json, struct, hashlib, itertools, sys
import numpy as np
from repair_lib import N, node_sizes, nleaves, Node, Leaf, t_obs, leaves_under, nodes_list

SZ = node_sizes(N); NL = nleaves(N)
_k = np.arange(N)
M = np.exp(1j*math.pi*np.outer(_k, 2*_k+1)/N)
TOL_L = 1e-13
TOL_T2 = 1e-13


class Tree:
    def __init__(self, node0_off, leaf_off):
        offs = []; o = node0_off
        for sz in SZ:
            offs.append(o); o += 2*sz
        self.leaf_off = leaf_off
        self.parent = {}
        self.byidx = {}
        def build(i, n, l):
            if n == 1:
                return Leaf(l), i, l+1
            nd = Node(i, n); nd.off = offs[i]
            a, nxt, ll = build(i+1, n//2, l)
            b, nxt, ll = build(nxt, n//2, ll)
            nd.left, nd.right = a, b
            self.parent[id(a)] = nd; self.parent[id(b)] = nd
            self.byidx[i] = nd
            return nd, nxt, ll
        self.root, nxt, ll = build(0, N, 0)
        assert nxt == len(SZ) and ll == NL


def same(x, y, tol=TOL_L):
    return abs(x-y) <= tol*max(abs(x), abs(y), 1e-300)


def raw_t(data, nd):
    e0, e1 = t_obs(data, nd)
    return e0[0], e1[0], e0[1], e1[1]


def signs_of(data, x):
    tr, ti, w0, w1 = raw_t(data, x)
    v = np.sign(tr)*w0 + np.sign(ti)*w1
    vr = np.sign(tr[::-1])*w0[::-1] + np.sign(ti[::-1])*w1[::-1]
    return np.where(v - vr >= 0, 1.0, -1.0)


def quad_hypotheses(a, b, c, d, t2s, tol_rel=1e-13):
    obs = [a, b, c, d] + list(t2s)
    for k in range(0, 5):
        hyps = []
        for drop in itertools.combinations(range(8), k):
            drop = set(drop)
            vc = [obs[i] for i in (0, 1) if i not in drop]
            wc = [obs[i] for i in (2, 3) if i not in drop]
            tc = [obs[i] for i in (4, 5, 6, 7) if i not in drop]
            if vc and not all(same(x, vc[0]) for x in vc): continue
            if wc and not all(same(x, wc[0]) for x in wc): continue
            if tc and not all(abs(x-tc[0]) <= TOL_T2 for x in tc): continue
            v = vc[0] if vc else None
            w = wc[0] if wc else None
            t2 = tc[0] if tc else None
            try:
                if v is None and w is not None and t2 is not None:
                    if not (0 <= t2 < 1): continue
                    v = w/(1-t2)
                if w is None and v is not None and t2 is not None:
                    if not (0 <= t2 < 1): continue
                    w = v*(1-t2)
                if t2 is None and v is not None and w is not None:
                    if not (0 < w < v): continue
                    t2 = 1 - w/v
            except ZeroDivisionError:
                continue
            if v is None or w is None or t2 is None: continue
            if not (v > 0 and w > 0 and 0 <= t2 < 1): continue
            if abs(w - v*(1-t2)) > 1e-13*v: continue
            ok = True
            for i in (0, 1):
                if i not in drop and not same(obs[i], v): ok = False; break
            if ok:
                for i in (2, 3):
                    if i not in drop and not same(obs[i], w): ok = False; break
            if ok:
                for i in range(4, 8):
                    if i not in drop and abs(obs[i]-t2) > TOL_T2: ok = False; break
            if ok:
                hyps.append((v, w))
        if hyps:
            groups = []
            for v, w in hyps:
                for g in groups:
                    if abs(v-g[0]) <= tol_rel*abs(g[0]) and abs(w-g[1]) <= tol_rel*abs(g[1]):
                        break
                else:
                    groups.append((v, w))
            return groups
    return []


def quad_t2(data, nd):
    """the 4 |t|^2 observations of an n=4 node"""
    tr, ti, _, _ = raw_t(data, nd)
    return [float(tr[0])**2, float(ti[0])**2, float(tr[1])**2, float(ti[1])**2]


def t2_vec(data, nd):
    """per-index |t|^2 for a node, NaN when the two raw estimates disagree"""
    tr, ti, _, _ = raw_t(data, nd)
    out = np.full(nd.sz, np.nan)
    for j in range(nd.sz):
        c0, c1 = float(tr[j])**2, float(ti[j])**2
        if 0 <= c0 < 1 and 0 <= c1 < 1 and abs(c0-c1) <= 1e-13:
            out[j] = 0.5*(c0+c1)
    return out


def repair_quads(data, tree, verbose=True):
    rep = data[tree.leaf_off:tree.leaf_off+NL].astype(float).copy()
    quads = [x for x in nodes_list(tree.root) if x.n == 4]
    amb = []
    nfix = 0
    for nd in quads:
        sl = leaves_under(nd)
        a, b, c, d = (float(rep[s]) for s in sl)
        groups = quad_hypotheses(a, b, c, d, quad_t2(data, nd))
        if len(groups) == 1:
            v, w = groups[0]
            rep[sl[0]] = rep[sl[1]] = v
            rep[sl[2]] = rep[sl[3]] = w
            nfix += 1
        else:
            amb.append((nd, sl, groups))
    if verbose:
        print("  quads: fixed %d, ambiguous %d of %d" % (nfix, len(amb), len(quads)))
    return rep, amb


def compute_arrays(data, tree, lv):
    """E array of every node + the root E"""
    cache = {}
    def rec(x):
        if isinstance(x, Leaf):
            return np.array([lv[x.slot]])
        A = rec(x.left); B = rec(x.right)
        if x.n == 2:
            t = np.zeros(x.sz)
        else:
            with np.errstate(divide='ignore', invalid='ignore'):
                t2 = np.where(A != 0, 1 - B/np.where(A != 0, A, 1.0), 0.0)
            t2 = np.nan_to_num(t2, nan=0.0)
            t = np.sqrt(np.clip(t2, 0, None))*signs_of(data, x)
        E = np.concatenate([A*(1+t), A*(1-t)])
        cache[x.idx] = (E, A, B, t)
        return E
    root = rec(tree.root)
    return root, cache


def resolve_by_parent(data, tree, lv, nd, verbose=False):
    """quad node nd: single free parameter v; use the parent relation."""
    P = tree.parent.get(id(nd))
    if P is None:
        return None
    sib = P.right if P.left is nd else P.left
    _, cache = compute_arrays(data, tree, lv)
    Es = cache[sib.idx][0] if sib.idx in cache else None
    if Es is None:
        return None
    if P.n != 8:
        return None
    T2 = t2_vec(data, P)
    # the quad's own |t|^2 (from its own observations, majority)
    t2q = t2_vec(data, nd)
    ok = t2q[np.isfinite(t2q)]
    if len(ok) == 0:
        return None
    tq = math.sqrt(float(ok[0]))
    t = np.array([tq, tq])*signs_of(data, nd)      # size 2 (anti-palindromic)
    fac = np.array([1+t[0], 1+t[1], 1-t[0], 1-t[1]])
    T = np.array([math.sqrt(x) if np.isfinite(x) else np.nan for x in T2], dtype=float)
    # parent t signs are irrelevant here (only t^2 enters)
    est = []
    for j in range(4):
        if not np.isfinite(T[j]):
            continue
        g = 1 - T[j]**2
        if P.left is nd:
            A_j = Es[j]/g if g != 0 else np.nan
            est.append(A_j/fac[j])
        else:
            B_j = Es[j]*g
            est.append(B_j/fac[j])
    est = [e for e in est if np.isfinite(e) and e > 0]
    if not est:
        return None
    est.sort()
    return est[len(est)//2]


def solve(data, tree, verbose=True):
    rep, amb = repair_quads(data, tree, verbose)
    lv = rep.copy()
    if not amb:
        E, _ = compute_arrays(data, tree, lv)
        D = np.real(np.linalg.solve(M.T, E))
        if verbose:
            r = np.abs(D-np.round(D))
            print("  residual max %.3g" % r.max())
        return D, lv, []

    def resid(lvv):
        E, _ = compute_arrays(data, tree, lvv)
        D = np.real(np.linalg.solve(M.T, E))
        return np.abs(D - np.round(D)).max(), D

    # candidate values per ambiguous quad: parent-resolved + hypothesis groups
    opts = []
    for nd, sl, groups in amb:
        cand = []
        vp = resolve_by_parent(data, tree, lv, nd)
        t2q = t2_vec(data, nd)
        okt = t2q[np.isfinite(t2q)]
        t2 = float(okt[0]) if len(okt) else None
        if vp is not None:
            cand.append((vp, vp*(1-t2) if t2 is not None else vp))
        for g in groups:
            cand.append(g)
        # dedupe
        uq = []
        for v, w in cand:
            for o in uq:
                if abs(v-o[0]) <= 1e-13*abs(o[0]) and abs(w-o[1]) <= 1e-13*abs(o[1]):
                    break
            else:
                uq.append((v, w))
        if not uq:
            uq = [(float(rep[sl[0]]), float(rep[sl[2]]))]
        opts.append((sl, uq))
    if verbose:
        print("  candidate sets:", [len(o) for _, o in opts])
    best = (1e18, None)
    total = 0
    for combo in itertools.product(*[o for _, o in opts]):
        total += 1
        if total > 400000:
            break
        trial = rep.copy()
        for (sl, _), (v, w) in zip(opts, combo):
            trial[sl[0]] = trial[sl[1]] = v
            trial[sl[2]] = trial[sl[3]] = w
        r, D = resid(trial)
        if r < best[0]:
            best = (r, D.copy(), trial)
        if r < 1e-9:
            break
    if verbose:
        print("  searched %d combos, best residual %.3g" % (total, best[0]))
    return best[1], best[2], []


def keystream(key, n):
    out = b""; c = 0
    while len(out) < n:
        out += hashlib.sha256(key + c.to_bytes(4, "big")).digest(); c += 1
    return out[:n]


def flag_from(ch, D):
    Dl = np.round(D).astype(np.int64)
    canon = ",".join(str(int(v)) for v in Dl).encode()
    fk = hashlib.sha256(b"frozen:" + canon).digest()
    ct = bytes.fromhex(ch["flag"])
    return bytes(a ^ b for a, b in zip(ct, keystream(fk, len(ct))))


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "real"
    if mode == "synth":
        from test_pipeline import make
        seeds = [int(x) for x in sys.argv[2:]] or [7, 11, 23, 31, 47, 59, 71, 83]
        ok = 0
        for s in seeds:
            data, Dtrue, true = make(cseed=s)
            D, lv, still = solve(data, Tree(0, 2*sum(SZ)), verbose=False)
            err = np.abs(D - Dtrue)
            good = (err.max() < 0.5)
            ok += good
            print("  cseed %2d: err max %.4g  #>0.5 %3d  %s"
                  % (s, err.max(), (err > 0.5).sum(), "OK" if good else "FAIL"))
        print("  solved %d/%d" % (ok, len(seeds)))
    else:
        path = sys.argv[2] if len(sys.argv) > 2 else "challenge2.json"
        ch = json.load(open(path))
        data = np.array(struct.unpack("<%dd" % (len(bytes.fromhex(ch["mem"]))//8),
                                      bytes.fromhex(ch["mem"])))
        print("==", path)
        D, lv, still = solve(data, Tree(256, 2048))
        Dl = np.round(D).astype(np.int64)
        print("  D[0] =", Dl[0])
        print("  FLAG:", flag_from(ch, D))
