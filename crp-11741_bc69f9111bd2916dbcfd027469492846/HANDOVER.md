# crp-11741（Cryptarithm）解题交接文档

> 日期：2026-11-01
> 状态：**电路已识别为 A5/1 型流密码；参考 A5/1 实现与电路实测输出尚未对齐（当前阻塞点）**

---

## 1. 题目概述

- **附件**：`Cryptarithm.bit`（Xilinx 7 系列 FPGA bitstream）+ 原始压缩包。
- **目标**：逆向 bitstream 中实现的电路，通过 UART 接口完成密码学挑战。
- **电路接口**（3 个 IOB，见 `crp_fixed.v` 端口）：
  - `LIOB33_X0Y13` → **RX**（串口输入）
  - `RIOB33_X43Y25` → **CLK**（时钟）
  - `LIOB33_X0Y111` → **TX**（串口输出）
- **交互协议**：UART 发送 8 字节（64 bit，疑似 key）+ 22 bit frame；电路返回 16 字节密钥流（`ks16`）。仿真时波特率分频 `div=868`（见 `exp1.py` 默认参数）。
- **电路核心**：三条移位寄存器 + 多数表决时钟控制 = **A5/1（GSM 流密码）硬件实现**。寄存器位片位于 `Q42–Q48` 一带（R1 链，见 `exp3.py` 中 26 个 FF 名单；与标准 A5/1 的 19/22/23 级可能不同，**需以网表为准**）。

## 2. 关键结论（已验证/已获得）

### 2.1 已知答案向量（hint vectors，来自实验标定）

| Key (64 bit) | Frame (22 bit) | Keystream (前 16 字节) |
|---|---|---|
| `0x0123456789abcdef` | `0` | `3836c93c175ec224a6db1f8bd6a3b681` |
| `0xdeadbeefcafebabe` | `2796202` | `b1993d4779346b929ceb31822fabaadd` |

来源：`battery.py` / `a51.py` 中的 `HINT1/HINT2` 常量（通过黑盒差分采样标定）。

### 2.2 挑战目标（`target_ks.json`）

```json
{"frame": 515947, "ks16": "f8dc8e4af089fe4eef965ae4a848cade"}
```

即需要给出产生该 (frame, ks16) 的 **64-bit key**（或按赛题实际要求完成相应计算——请接手者先与题目服务端确认提交格式）。

### 2.3 阻塞点：A5/1 标准实现不匹配

- `a51.py`：标准 A5/1 实现（R1 19/R2 22/R3 23，taps 标准，多数表决，100 拍预热，lsb/msb 输出两种打包）——**未命中** hint1。
- `sweep51.py`：**5120 种约定组合大扫描**（key/frame 字节序×位序、装载时是否用多数表决、预热拍数 {0,99,100,101}、预热注入位、先输出后时钟 vs 先时钟后输出、字节 MSB/LSB 打包）× 2 个 hint key —— **全部未命中**。
- 结论：该电路**不是教科书版 A5/1**。差异可能在于：反馈 tap、寄存器级数、输出 tap、表决逻辑位、装载协议（key 注入方式）、或输出在时钟周期中的位置。**必须从网表逐位提取，不能靠猜。**

## 3. 逆向流水线（已完成，可复现）

```
Cryptarithm.bit
  │  prjxray / bitparse.py、decomp*.py（fasm 解析）
  ├─→ crp.fasm / crp_v.fasm / frames.txt（帧数据，5.6 MB）
  │  yosys 脚本 ys.ys / ys2.ys / ys3.ys（fasm→verilog→JSON）
  ├─→ crp.v（prjxray fasm2v 网表，50 万行）        ← 原始网表
  ├─→ flat.json（yosys flatten，4.4 MB）
  ├─→ gates.json（yosys 折叠门级，3.7 MB）
  ├─→ crp_fixed.v / gates_fixed.json               ← 修正版网表（模拟器使用）
  │  gen_c.py → sim.c → sim_c（C 模拟器）
  ├─→ 每时钟周期黑盒仿真 + UART 驱动（exp1/2/3.py）
  └─→ 状态机 BFS（make_bfs.py、sim_bfs.c）→ trans.txt / states.txt
```

辅助产物：`rtl.txt`（FDRE 逐位方程，可读性最好）、`equations.txt/equations2.txt`（LUT 方程）、`lut_init_orig.json`（原始 LUT 初值）、`used_tiles.txt`（占用 tile）、`diffbits*.py`（差分采样）、`checkinit.py`/`direct_extract.py`（FF 初值检查）。

### 已识别的电路结构要点

- `rtl.txt` 中 `Q42A4/Q42A6/Q42B4/Q42C4...Q48A4/Q48B4` 构成**链式异或移位结构**（A5/1 风格），移位使能由多数表决 LUT 控制（`CE: LUT3/ LUT5(...)`）。
- UART 接收状态机已被 BFS 提取（`trans.txt`：S0–S38，含 start bit 校验、逐位接收、输出恒 1 段）。
- `bram_dump.json` 为空：BRAM 无初始化数据（或提取未成功，如需可查 `extract_bram.py`）。

## 4. 文件清单速查

| 类别 | 文件 | 说明 |
|---|---|---|
| 题目原件 | `Cryptarithm.bit`, `crp-11741_*.zip` | bitstream 与原始包 |
| 逆向核心 | `bitparse.py`, `decomp.py/2/3`, `final_decomp.py`, `netlist.py` | bit→fasm→网表解析 |
| 网表/方程 | `crp.v`, `crp_fixed.v`, `gates.json`, `gates_fixed.json`, `flat.json`, `rtl.txt`, `equations*.txt` | **分析主力，勿动** |
| 仿真 | `gen_c.py`, `sim.c`→`sim_c`, `sim.py/2/3`, `sim3f.py`, `exp1.py`(基类), `exp2.py`, `exp3.py` | `exp1.tick(din)` 为标准周期仿真接口 |
| 密码分析 | `a51.py`, `battery.py`, `sweep51.py`, `target_ks.json` | A5/1 验证与扫描 |
| 状态机 | `make_bfs.py`, `sim_bfs.c`→`sim_bfs`, `trans.txt`, `states.txt` | UART/控制 FSM |
| 中间大文件 | `paths.txt`(**1.7 GB**), `o1/o2.txt`(30 MB), `long.out`(20 MB), `states.txt`(110 MB), `uart.txt/hold.txt/rnd.txt/p*.txt/a0/a1/r0/r1` | **可清理或压缩归档** |
| 日志 | `ff.err` | fasm 纯 Python 解析器告警（可装 antlr 加速，非错误） |

## 5. 下一步建议（按优先级）

1. **从网表精确提取三条寄存器的参数**（替代猜测）：
   - 在 `crp_fixed.v`/`gates_fixed.json` 中对 `Q42–Q48` 链逐位追 D 输入来源，确定每级的反馈 tap XOR 组合 → 得到各寄存器级数与 tap 位置；
   - 同法确定输出 bit 取自哪三个 tap、表决控制位（`CE` LUT 的 3 个输入）具体对应哪些寄存器位。
   - 工具：`lsp`/文本搜索 + `datapath.py`（已含命名规约）。
2. **确定装载协议**：用 `exp3.py` 在 UART 期间逐拍监视 R1/R2/R3 值，确认 64 bit key + 22 bit frame 的注入节奏（每 UART bit 注入几位、是否经表决）。
3. **改写 `a51.py` 为"网表精确版"**：用第 1、2 步得到的真实参数替换标准 taps/级数，用 hint1+hint2 双向量回归验证（一个标定、一个验证）。
4. **完成挑战**：算法对齐后，
   - 若任务是"给定 key/frame 算 ks16"：直接实现并在服务端验证；
   - 若任务是"由 (frame, ks16) 恢复 key"：按 A5/1 经典攻击路线做——guess-and-determine（Golić）、相关性攻击（Siegenthaler）或已知帧密钥流的 `2^32` 中间相遇；参考 `HANDOVER` 同目录学术资料（见 §6）。
5. **确认赛题提交格式**：`target_ks.json` 的语义（求 key？求 flag=md5(key)？）请先与平台核对，避免白做。
6. **收尾清理**（可选）：归档/删除 `paths.txt`(1.7 GB)、`p*.txt`、`o1/o2/long.out` 等，保留网表与分析脚本即可。

## 6. 方法论与文献支撑（详见上轮研究记录）

- **A 类（bitstream 逆向框架）**：Project X-Ray 文档、Meade ASPDAC'16、IEEE Access 2019 工具链综述、arXiv:2312.06195、Moraitis–Dubrova 2022（bit 级 LUT 差分——本题 `diffbits.py` 的学术对应）。
- **B 类（序列密码攻击）**：Massey 1969（Berlekamp–Massey，**首验手段：对 ks16 做线性复杂度测试**）、Siegenthaler 1985（相关性攻击）、Courtois–Meier 2003（代数攻击）、Dinur–Shamir 2009（cube attack，与本题黑盒+可控输入接口契合）。
- **C 类（题意）**：Eppstein《On the NP-Completeness of Cryptarithms》——题名或暗指"逐位算术/字谜"，若 A5/1 路线受阻可回到状态机做逐位算术建模（Z3/CP）。

## 7. 环境与复现命令

- Python 3.14（`/tmp/venv`），依赖：`fasm`（有 antlr 加速告警，见 `ff.err`）、prjxray 数据库、yosys。
- 快速复现：
  ```bash
  cd work
  python3 exp1.py 868 'U'                 # 单周期黑盒仿真，观察 TX
  python3 exp3.py 868 '\x01\x23\x45\x67\x89\xab\xcd\xef'   # 监视 R1 移位链
  python3 a51.py                          # 标准 A5/1 vs hint 向量
  python3 sweep51.py                      # 5120 变体扫描（当前无命中）
  gcc -O2 -o sim_c sim.c && ./sim_c       # C 模拟器
  ```
- 仿真接口约定：`exp1.tick(din)` = 一个 CLK 周期，`din` 为 RX 电平；`uart_bits(msg, div=868)` 生成 UART 波形。

## 8. 风险与注意事项

- `sim.c`/`exp1.py` 由网表自动生成，正确性依赖 `gates_fixed.json`；如修改网表重建流程（`ys*.ys`），需重跑 `diffbits.py` 回归。
- `exp3.py` 中段有调试残留代码（无效循环），仅保留其监视逻辑作参考。
- 两个 hint 向量是**本方向一切推导的基准**，任何新实现必须同时通过两者，防止过拟合单一向量。
