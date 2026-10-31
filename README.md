# 强网杯 2026 解题工作区

第十届"强网杯"全国网络安全挑战赛（线上赛）Crypto 方向的解题过程归档。
本仓库为多题 monorepo，每题独立目录，含完整复现材料与交接文档。

## 题目总览

| 题目 | 目录 | 类型 | 状态 | 入口文档 |
|---|---|---|---|---|
| **crp-11741**（Cryptarithm） | `crp-11741_bc69f9111bd2916dbcfd027469492846/` | FPGA bitstream 逆向 + 流密码 | ⏳ 进行中（电路已识别为 A5/1 型，变体参数未对齐） | [HANDOVER.md](crp-11741_bc69f9111bd2916dbcfd027469492846/HANDOVER.md) |
| **frozen** | `frozen_02136a685ccd425e537aa0735795019f/` | Falcon 结构逆向 + 位翻转纠错 | ✅ 已解出 | [writeup.md](frozen_02136a685ccd425e537aa0735795019f/writeup.md) |
| **vmshare**（SIMD_TINY_BLOCK_IS_A_NIGHTMARE） | `vmshare_6d3416fb746f85cad8020e41571f8b7b/` | AVX2 SIMD 逆向 | ✅ 已解出 | [writeup.md](vmshare_6d3416fb746f85cad8020e41571f8b7b/writeup.md) |
| **hoRRibleRing** | `horriblering/` | RLWE 样本判定 / 格攻击 | ❌ 未解出（负面结论归档，解出概率评估 10%–15%） | [README.md](horriblering/README.md) |

## 各题一句话

- **crp-11741**：给定 Xilinx 7 系列 bitstream，逆向出 UART 接口的 A5/1 型流密码电路；已完成 bit→FASM→网表→模拟器全流水线，两个已知答案向量已标定，当前阻塞点是电路与教科书 A5/1 的变体差异（需从网表精确提取 taps）。
- **frozen**：从被随机位翻转污染、且截去头部 1024 个 double 的内存转储中恢复 Falcon 私钥矩阵 `D = f·adj(f) + g·adj(g)`，解密得 flag。
- **vmshare**：逆向使用 AVX2 的 x86-64 ELF 加密器，恢复 SIMD 变换，对 32 字节密文求逆，flag 形如 `flag{XXXXXXX_YYYYYYY}`（两组 7 位十六进制）。
- **hoRRibleRing**：336 个互相独立的 RLWE 样本逐位编码 flag；单样本为 dim=1024 的 BDD（gap≈2253），纯格攻击不可行，环可约性降维路线已全部证伪，详见负面结论清单。

## 目录结构

```
README.md                     本文件（总索引）
.gitignore
horriblering/                 hoRRibleRing 题目归档
  ├─ README.md                题目主交接文档
  ├─ docs/                    01-交接文档 / 02-负面结论清单 / 03-格攻击定量分析
  ├─ scripts/                 复现脚本（python-flint + fplll）
  └─ data/                    task.sage、samples.txt、factors.pkl
crp-11741_bc69f9111bd2916dbcfd027469492846/
  ├─ Cryptarithm.bit          题目原始 bitstream
  ├─ HANDOVER.md              交接文档（含文献索引与下一步建议）
  └─ work/                    逆向流水线：bit→fasm→网表→模拟器→A5/1 分析
frozen_02136a685ccd425e537aa0735795019f/
  └─ writeup.md、task.py、solve_frozen.py 等
vmshare_6d3416fb746f85cad8020e41571f8b7b/
  └─ writeup.md、encryptor、cipher.bin、solve.c 等
```

## 复现环境备注

- crp-11741：Python 3.14 + `fasm`/prjxray 数据库 + yosys；详见其 `HANDOVER.md` §7。
- hoRRibleRing：Windows + `py -3`（3.9.13）+ python-flint 0.6.0；BKZ 需自编译 fplll。
- GitHub 推送走本地代理 `http://127.0.0.1:7897`：
  `git -c http.proxy=http://127.0.0.1:7897 push origin main`
- crp-11741 的 `work/paths.txt`（1.7 GB）与 `work/states.txt`（110 MB）超出 GitHub 限制，不入库。
