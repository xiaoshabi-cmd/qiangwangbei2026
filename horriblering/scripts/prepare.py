"""从 data/ 生成各脚本需要的 samples.pkl（在仓库根目录运行）。

用法（仓库根目录）：
    py -3 scripts/prepare.py

产出：./samples.pkl   （其它脚本按相对路径读取它）
同时校验 data/factors.pkl 与 f 的一致性。
"""
import ast
import pickle
import re
from pathlib import Path

from flint import fmpz_mod_poly_ctx

ROOT = Path(__file__).resolve().parent.parent
P = 0x3AC01F87
N = 512


def load_f():
    src = (ROOT / "data" / "task.sage").read_text(errors="ignore")
    line = [l for l in src.splitlines() if l.startswith("f = x^512")][0]
    expr = line.split("=", 1)[1].strip()
    coeffs = [0] * (N + 1)
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
    ctx = fmpz_mod_poly_ctx(P)
    return ctx, ctx(coeffs)


def load_samples():
    txt = (ROOT / "data" / "samples.txt").read_text(errors="ignore")
    payload = txt.split("=", 1)[1].strip()
    return ast.literal_eval(payload)


if __name__ == "__main__":
    ctx, f = load_f()
    assert f.degree() == N, f.degree()
    samples = load_samples()
    assert len(samples) == 336, len(samples)
    assert all(len(a) == N and len(b) == N for a, b in samples)

    facs = pickle.load(open(ROOT / "data" / "factors.pkl", "rb"))
    prod = ctx([1])
    for fc in facs:
        prod = prod * ctx(fc)
    assert prod == f, "factors.pkl 与 f 不一致"

    with open(ROOT / "samples.pkl", "wb") as fh:
        pickle.dump(samples, fh)

    from collections import Counter
    print("samples:", len(samples), " factors:", len(facs),
          " degrees:", dict(sorted(Counter(ctx(fc).degree() for fc in facs).items())))
    print("wrote", ROOT / "samples.pkl")
