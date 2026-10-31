# 强网杯 2026 · hoRRibleRing —— 解题过程与交接文档

> 状态：**未解出**（flag 未恢复）。本仓库是对该题完整分析过程的归档，核心价值是
> **已证明的负面结论**与**可复现的量化难度模型**，避免后续接手者重复劳动。

## 1. 一句话结论

题目（`samples.txt` 实际数据）等价于：对 **336 个互相独立**的 RLWE 样本逐个判断
"`b = a·s + e` 且 `s,e` 都很小"是否成立。单样本判定是 dim = 1024、det = p^512 的 BDD 问题，
**gap ≈ 2253**，需要 **BKZ-β≈150**；而 LLL 的能力上限只到 dim≈390。因此：

- **纯格攻击不可行**（差 10^10 量级，且要跑 336 次）；
- 所有"用环的可约性降维"的路线（CRT/商环投影、理想消元、对偶攻击）**已被证明封死**；
- 唯一的未穷尽线索是题面提示 `Notice that there are 3 'R's in the title too :(`，
  与数据中唯一的非平凡"3"结构（**3 个偶四次自对称因子**）吻合，但其攻击用途未找到。

综合评估解出概率：**10%–15%**。

## 2. 题目机制（已逐行确认）

```python
p = 0x3ac01f87                       # 985669511，素数
PR.<x> = PolynomialRing(GF(p))
f = x^512 + ...                      # 512 次，随机系数
def F0():                            # bit '0' -> LWE
    D = DiscreteGaussianDistributionIntegerSampler(sigma=3.371)
    s = PR([D() for _ in range(512)])   # 每次调用都重新采样！
    e = PR([D() for _ in range(512)])
    a = PR([randbelow(p) for _ in range(512)])
    b = (a*s + e) % f
    return [a.list(), b.list()]
def F1():                            # bit '1' -> 全随机
```

输出 = `bin(bytes_to_long(flag))[2:].zfill(len(flag)*8)` 的每一位对应的样本，共 **336 个**
（⇒ flag 长 42 字节）。索引 `j` ↔ 第 `j` 位 ↔ 第 `j//8` 字节的第 `7-(j%8)` 位。

**关键点：`s, e, a` 每个样本都是全新的，不存在共享密钥**（已用三种独立检验确认，见 `docs/02`）。

## 3. 仓库结构

```
README.md                      本文件
docs/01-交接文档.md             主交接文档（背景/进展/结论/后续）
docs/02-负面结论清单.md          已排除的假设表（查重用，勿重复）
docs/03-格攻击定量分析.md        参数推导、成本模型、实测标定数据
scripts/                       复现用脚本（python-flint + fplll）
data/task.sage                 题面原始代码
data/samples.txt               336 个样本（题面输出）
data/factors.pkl               f 在 GF(p) 上的 261 个不可约因子（预计算）
```

## 4. 快速复现

```powershell
py -3 -m pip install python-flint          # 0.6.0 已测
py -3 scripts/lll1.py 0                     # 对样本 0 做 Kannan 嵌入 + LLL（会很久）
py -3 scripts/proj1.py                      # 复现"CRT 投影无效"的证据
py -3 scripts/cal.py                        # 复现 LLL 阈值标定
```

BKZ 需要 `fplll`（本机已编译于 `.deps/install/bin/fplll.exe`，Windows 下需
`PATH+=C:\msys64\usr\bin;C:\msys64\mingw64\bin`）。

## 5. 环境与网络备注

- Windows + PowerShell，`py -3`（3.9.13），python-flint 0.6.0，无 Sage，无 fpylll。
- 本机 `git config --global` 里配的代理 `http://127.0.0.1:7890` **是失效的**（该端口无监听）；
  实际可用的本地代理是 **`http://127.0.0.1:7897`**（系统代理也是这个）。推送命令：

  ```powershell
  git -c http.proxy=http://127.0.0.1:7897 -c https.proxy=http://127.0.0.1:7897 push origin main
  ```

  若代理关闭且直连 `github.com:443` 不通，可临时绕过代理：
  `git -c http.proxy= -c https.proxy= ...`（`api.github.com:443` 通常仍可达）。
