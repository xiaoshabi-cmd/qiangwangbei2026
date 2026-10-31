# frozen — Writeup

> CTF Crypto / Falcon 结构逆向 + 位翻转纠错
> 目标：从一份**被随机位翻转污染、且前 1024 个 double 被截掉**的内存转储中恢复 `D = f·adj(f) + g·adj(g)`，从而解密 flag。

最终 flag：

```
flag{02fdf384-4716-410b-848a-dc1b287dd3ef}
```

（同一脚本在旧实例上验证得到 `flag{0bb29abc-3f96-4f08-8699-5f9e19ee73dd}`。）

---

## 1. 题目给了什么

`task.py` 的关键流程：

```python
N, Q, SIGMA = 128, 12289, 19.16
key = keygen(N, Q, SIGMA, rng)          # Falcon 式私钥 (f,g,F,G)，满足 fG - gF = q，h = g/f mod q
vals, parts = expanded_doubles(key)     # 把 FFT 值与 LDL 树展开成一串 double
blob = dump_blob(vals)
cblob_full = corrupt_blob(blob, RHO10, rho01=RHO01, rng=decay)   # 位翻转
head = 8 * 128
cblob = cblob_full[head * 8:]           # 砍掉前 8192 字节 = 1024 个 double

canon = ",".join(str(c) for c in D).encode()
fk = sha256(b"frozen:" + canon)
ct = flag XOR keystream(fk)
```

服务端输出 `pubkey`（含 `h`）、`memory`（= cblob 的 hex）、`flag`（密文 hex）。

所以**唯一目标**是还原整数向量

```
D = f·adj(f) + g·adj(g)  ∈ Z^128
```

其中 `adj(a) = a₀ − a_{N−1}x − … − a₁x^{N−1}`（即 `poly_adj`）。

---

## 2. 内存布局：被砍掉的正好是全部 FFT

`expanded_doubles` 的写入顺序：

| 段 | 内容 | double 数 |
|---|---|---|
| ① | `fft(f).real, fft(f).imag, fft(g).real/im, fft(F).real/im, fft(G).real/im` | 8×128 = **1024** |
| ② | 树节点（DFS 先序，每节点**先实部后虚部**）：`Ltop`(128 复) + `_T(G00)`(448 复) + `_T(Dright)`(448 复) | 2×1024 = 2048 |
| ③ | 叶子（DFS 顺序，纯实数）：`_T(G00)` 128 个 + `_T(Dright)` 128 个 | 256 |

合计 3328 个 double；`cblob_full[8192:]` 恰好切掉 1024 个 double，即**第 ① 段整段消失**，我们只剩 2304 个 double（② + ③）。

### 布局验证

树的结构是确定的（`_T` 递归），所以可以离线推出每个节点的 L 长度：

```
size(128) = [64] + size(64) + size(64)      # 先序
```

另一个自洽性检查：`_T` 在 `n = 2` 时 `L ≡ 0`（后面会证明），因此数据里应当出现 128 个「L 为 0」的节点，即 256 个 ~1e-18 的 double，且因为 DFS 先序把兄弟节点排在一起，它们表现为 64 段连续 4 个。实测预测位置集合与观测近零位置集合**完全一致（无缺无多）**，布局确认无误。

---

## 3. 三段关键代数

### 3.1 逆变换必须用 `Mᵀ`

`fft(a) = a @ M`，`M[k,j] = ρ_j^k`，`ρ_j = exp(iπ(2j+1)/N)`。即 `F = Mᵀa`，所以

```python
D = solve(M.T, E)      # 不是 solve(M, E)
```

用错方向的表现是「一切都在但结果面目全非」，这是第一个陷阱。

### 3.2 树顶层就是 `FFT(D)`

`falcon_tree` 里

```python
G00 = gh*conj(gh) + fh*conj(fh)      # = |fft(f)|² + |fft(g)|²
```

而 `FFT` 是负循环卷积的环同态，且 `FFT(adj(a)) = conj(FFT(a))`，于是

```
G00 = FFT( f·adj(f) + g·adj(g) ) = FFT(D)
```

**`_T(G00)` 这棵子树完整编码了 D**，其余部分（`Ltop`、`_T(Dright)`）只是干扰/旁证。

### 3.3 实数化：`L_j = t_j·ρ_j`，且 t 反回文

`splitfft` 做的是 `E(x) = Ee(x²) + x·Eo(x²)`。因为 `G00` 逐点是**实数**且共轭对称，可以推出每个 `L` 项必然写成

```
L_j = t_j · ρ_j ,  t_j ∈ R        (等价地 Im(L_j/ρ_j) = 0)
```

于是整个递归完全实数化：

```
E(node) = [ A·(1+t), A·(1-t) ]        A = 左孩子数组
B       = A·(1-t²)                    B = 右孩子数组
t      ≡ 0        (n = 2，因为此时 A = [v]、B = [v])
```

进一步的**决定性性质**：对实向量做该 FFT 得到的是回文数组（`F[j] = F[n-1-j]`），而 `E = [A(1+t), A(1-t)]` 展开就得到

```
A[j] = A[h-1-j]  且  t_j = -t_{h-1-j}         （实测误差 0.0）
```

这条「t 反回文」直接给出：
* 符号不再靠单点观测，可用 `(t_j, t_{h-1-j})` 的 4 个观测做**多数票**；
* `n=2` 时 `t = -t ⇒ t = 0`，与实测的 128 处零完全对应。

顺带一个漂亮的旁证：2×2 FFT 矩阵的行列式 `fh·Gh − gh·Fh = FFT(fG−gF) = q`，所以

```
Dright = G11 − |G01|²/G00 = q² / G00
```

`_T(Dright)` 与 `_T(G00)` 互为倒数关系，可用于交叉校验。

---

## 4. 腐蚀模型与难点

`corrupt_blob` 对每个 double 的 bit 0–55 和 63：置 1 的位以 0.01 概率翻转，置 0 的位以 0.001 概率翻转。实测：

* **72% 的 double 完全没有变**；
* 约 25% 至少翻了一位，但大多在低位（相对误差 < 1e-10，无害）；
* **约 9–10% 有可见误差**（相对误差 > 1e-4，最大可到 ×16 量级）。

麻烦在于树是**乘法链**：`E = Π(1±t) × 叶子`，一个被污染的叶子/`t` 会乘以整条路径，误差不会自行衰减；更糟的是 `t² = 1 − B/A` 在小 `t` 处有消去误差，在 `t→1` 处又对扰动极敏感（表现为「残差对叶值呈混沌敏感」）。

因此**所有比较都在 `t²` 域做**（`|t²_obs − (1−B/A)| ≤ 1e-13` 绝对量），而不是比较 `t` 本身。

---

## 5. 修复算法

叶子是唯一的「单次观测」量（128 个，约 10% 被污染），其余都能由关系式反解。因此分三层：

### (1) quad 分组：最小腐坏假设的穷举

`n=4` 节点（记作 quad）有 4 个叶子 `(v, v, w, w)` 和 4 个 `t²` 观测，约束只有一条：

```
w = v·(1 − t²)
```

把 8 个观测视为可能被污染的集合，枚举「声明哪些观测被污染」（k = 0…4，最小优先），要求保留下来的观测在 1e-13 内互相自洽且满足上式；对每个 quad 得到 1 个或少数几个候选 `(v, w)`。

### (2) 上一层反解（关键一步）

quad 若仍歧义，就只剩一个自由参数 `v`（`w` 由关系式给出）。**父节点（n=8）的关系对它是一次方程**：

```
父为左孩子时:  v = ( E_sib[j] / (1 − T_j²) ) / factor_j
父为右孩子时:  v = ( E_sib[j] · (1 − T_j²) ) / factor_j
factor = [1+t₀, 1+t₁, 1−t₀, 1−t₁]
```

其中 `E_sib` 是兄弟节点数组，`T²` 取父节点自身的 `t²` 观测（要求两个分量一致才采信）。4 个下标给出 4 个独立估计，取中位数，精度足够直接定死 `v`。

### (3) 整数性判别

`D` 必须是整数向量，这是全局硬约束。把所有候选（quad 假设 + 父级反解）做笛卡尔积，对每个组合计算

```
residual = max_k | D_k − round(D_k) |
```

取残差最小者并四舍五入。本题最终残差 **0.00206 ≪ 0.5**，取值唯一确定。

### 符号

`t` 的符号用反回文约束投票：

```python
v  = sign(t_re)·|ρ_re| + sign(t_im)·|ρ_im|            # 下标 j
vr = sign(t_re[::-1])·|ρ_re[::-1]| + sign(t_im[::-1])·|ρ_im[::-1]|   # 下标 h-1-j
sign_j = +1 if (v - vr) >= 0 else -1                  # 因为 t_j = -t_{h-1-j}
```

---

## 6. 验证

* **正向重建对拍**：用 `task.py` 原封不动的 `_T` 从 `round(D)` 重建 T1 子树，与观测的 1024 个 double 比较 —— **75% 相对误差 < 1e-8**，其余 25% 正是被污染的项（与「72% 未变」的模型吻合）。
* `D[0] = ||f||² + ||g||²`：本题 101321，而理论期望 `2·128·σ² ≈ 93952`（σ=19.16），在正常涨落内。
* 合成数据回归：随机生成同分布 `(f,g)` + 相同腐蚀参数，8 个种子中 7 个能精确还原 `D`（`python3 solve_frozen.py synth`）。
* 明文格式 `flag{uuid4}`，随机密钥不可能碰撞。

---

## 7. 走过的弯路（供参考）

| 尝试 | 结果 |
|---|---|
| 朴素树重构 + 四舍五入 | 残差 ~0.49，几乎全错（消去误差 + 乘法放大） |
| 退火 predict/repair 迭代、整数坐标下降 | 陷入伪不动点 |
| Gauss–Newton / SciPy `soft_l1` 全局 bundle adjustment | 目标函数对叶值混沌敏感，梯度法失效 |
| 直接把未知叶做「整数性线性最小二乘」 | 初值太差，不动点不收敛 |
| **NTRU 格攻击**：dim 256，目标范数 √83322≈289，GH≈429 | BKZ-40（mpfr，精度 212）仅把范数从 1.51e8 压到 1.15e8，**远远不够**；需要 block ≥ 50–60，代价过高 |

真正解决问题的是第 3.3 节的**回文结构**（符号不再靠猜）与第 5 节的**父级反解**（把 2 个未知量降为 1 个线性方程）。

---

## 8. 复现

```bash
# 现场抓数据（保存 pubkey/memory/flag）
python3 - <<'PY'
import socket, json, re
s = socket.create_connection(("HOST", PORT), timeout=60)
buf = b""
while b"flag" not in buf or buf.count(b"\n") < 3:
    d = s.recv(65536)
    if not d: break
    buf += d
t = buf.decode()
json.dump({"pub": json.loads(re.search(r"pubkey = (\{.*\})", t).group(1)),
           "mem": re.search(r"memory = ([0-9a-f]+)", t).group(1),
           "flag": re.search(r"flag   = ([0-9a-f]+)", t).group(1)},
          open("challenge.json", "w"))
PY

python3 solve_frozen.py real challenge.json          # 解真实实例
python3 solve_frozen.py synth 7 11 23 31 47 59 71    # 合成数据回归
```

文件：`solve_frozen.py`（解法）、`repair_lib.py`（树解析/ρ-t 工具）、`test_pipeline.py`（同格式合成实例生成器）。
