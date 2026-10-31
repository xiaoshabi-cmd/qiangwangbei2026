# 脚本说明

所有脚本在 **仓库根目录** 运行（它们以相对路径读取 `samples.pkl` / `task.sage`）。

```powershell
py -3 -m pip install python-flint
py -3 scripts/prepare.py     # 生成 ./samples.pkl（必需的第一步）
```

| 脚本 | 作用 | 备注 |
|---|---|---|
| `prepare.py` | 解析 `data/task.sage` 与 `data/samples.txt`，生成 `samples.pkl`，并校验 `factors.pkl` | 新增，替代原先散落的解析代码 |
| `lll1.py` | **主攻击**：对单个样本构造 Kannan 嵌入（dim 1025），LLL 后寻找最后一个坐标为 ±1 的短向量，并用 `a*s+e ≡ b` 校验 | dim 1025 时 FLINT LLL 会跑很久 |
| `bkz_attack.py` | 同上格的 fplll 版本：先 FLINT LLL，再调 `fplll -a bkz -b <block>` | 依赖 `.deps/install/bin/fplll.exe`（未随仓库提交）；Windows 需把 `C:\msys64\usr\bin;C:\msys64\mingw64\bin` 加入 PATH |
| `cal.py` | **阈值标定**：同 p/σ 的随机可约 f，植入已知 (s,e)，测 LLL 在 n=16..128 的成功率与耗时 | 复现 docs/03 的表 |
| `proj1.py` | **否定证据**：把 42 个已知 F0 样本投影到 140 个根，逐个做小维 LLL | 全部无解 ⇒ CRT 投影攻击无效 |
| `pow.py` | 扫描 `x^k mod f`（k ≤ 3000）的系数范数 | 无短结构 |
| `hyp.py` | 检验 `e=0` / `s=e` / 共享密钥等代数关系 | 全部为负 |
| `inv.py` | 检验 `(a+c)^{-1}b` 是否小 | 全部为负 |
| `x16.py` | 因子集的缩放/平移轨道与自互反检验 | 全部为负 |

## fplll 的用法

```powershell
$env:PATH="C:\msys64\usr\bin;C:\msys64\mingw64\bin;"+$env:PATH
.deps\install\bin\fplll.exe -a bkz -b 30 lattice.lat > lattice.reduced.lat
```

格文件格式：`[[row0][row1]...]`，行 = 基向量。`-nolll` 表示跳过前置 LLL。
