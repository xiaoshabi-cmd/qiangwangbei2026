# SIMD_TINY_BLOCK_IS_A_NIGHTMARE — Writeup

**题目**：第十届"强网杯"全国网络安全挑战赛（线上赛）— Crypto `vmshare`（100 pt）
**题目文件**：`encryptor`（x86-64 ELF，使用 AVX2）+ `cipher.bin`（32 字节密文）
Flag 格式：`flag{XXXXXXX_YYYYYYY}`，两组各 7 位十六进制。

> **FLAG：`flag{3174812_31af718}`**（平台判定正确，本地官方程序复核一致）

---

## 1. 程序流程逆向

### 1.1 参数与 flag 校验（main @0x1eb0）

```
usage: %s flag{XXXXXXX_YYYYYYY} [out.bin]
       (or place the flag in flag.txt)
error: flag must match flag{XXXXXXX_YYYYYYY}
       where each XXXXXXX/YYYYYYY is 7 uppercase hex digits
```

无参数时从 `flag.txt` 读取 flag，默认输出 `cipher.bin`。校验逻辑（`0x1f00` 起）：

| 检查 | 实现 |
|---|---|
| 长度 | `strlen(argv[1]) == 0x15`（21） |
| 前缀 | `strncmp(s, "flag{", 5) == 0` |
| 结尾/分隔 | `s[0x14] == '}'` 且 `s[0xc] == '_'` |
| 内容 | 下标 `5..0x13`（跳过 `0xc`）逐字节判断十六进制（`& 0xdf` 后判 `A-F`，否则判 `0-9`，大小写均可） |

然后把两组数字拷进两个 16 字节栈缓冲（注意 buf2 与 buf1 尾部重叠，但 NUL 位置正确，不影响）：

```c
memcpy(b1+0, flag+0x5, 4); memcpy(b1+3, flag+0x8, 4);  // b1 = flag[5..11]
memcpy(b2+0, flag+0xd, 4); memcpy(b2+3, flag+0x10, 4); // b2 = flag[13..19]
X = strtoul(b1, NULL, 16);
Y = strtoul(b2, NULL, 16);
```

### 1.2 密钥流生成器 prng @0x1c60

```asm
1c60: mov eax,edi
1c62: and eax,0xffffff        ; ← 只保留低 24 bit！最高 4 bit 被丢弃
1c67: xor eax,esi             ; esi = seed
      s ^= s>>13; s *= 0x45d9f3b; s ^= s>>16
1c80: lea eax,[rax+rsi-0x61c88647]   ; s += acc + 0x9E3779B9
1c87: add esi,0x7f4a7c15             ; acc += 0x7f4a7c15
      t = s ^ (s>>13); t *= 0x85ebca6b; t ^= t>>16   ; murmur3 fmix32
      u = t ^ (t>>16)
      out[i] = (uint16)u;  s = t
1cb0: cmp esi,0xfa53e0a8 ; jne 1c80   ; 8 × 0x7f4a7c15 ≡ 0xfa53e0a8 → 恰好 8 轮
```

即：输入 24 bit → 8 个 `uint16` 密钥字。两次调用的 seed 分别是 `0x31415926`（π）和 `0x27182818`（e）：

```c
prng(X, 0x31415926, ks1);   // 0x2039
prng(Y, 0x27182818, ks2);   // 0x2049
```

### 1.3 SIMD 轮函数 @0x1cc0

`ymm0` = 16 个 16-bit lane；每轮把输入密钥字的一个 word 广播后作用到全部 lane，共 8 轮（编译期完全展开，无循环）。单轮单 lane 的运算：

```c
y ^= y >> 5;
y  = w + c[j] + rotl16(y, 3);   // c[j] 为常量表
y ^= y >> 7;
y  = rotl16(y, 9);
```

- 常量表 `C[16]` @0xa60：`1357 2468 369c 48ad 5be1 6cf2 7d03 8e14 9f25 a036 b147 c258 d369 e47a f58b 069c`
- 初始状态 @0xa80：ASCII `"SIMD_TINY_BLOCK_IS_A_NIGHTMARE!!"` 按 little-endian 拆成 16 个 lane
- 第二个参数 `rsi`（`"wb"` 字符串）在函数体内未被使用，是干扰项

### 1.4 加密过程

```c
ymm0 = IV;
S1  = F(IV , ks1);      // 0x2060
OUT = F(S1 , ks2);      // 0x2068
fwrite(&OUT, 1, 32, f); // 16 lane × uint16(LE) = 32 字节
```

整体是一个 2 轮的 16 路并发生成器/压缩函数，**密钥只有 2×24 = 48 bit**。

---

## 2. 建模与对拍

完整 Python 模型见 `model.py`（核心如下）：

```python
def prng(val, seed):
    s = ((val & 0xFFFFFF) ^ seed) & M32
    s ^= s >> 13; s = (s * 0x45d9f3b) & M32; s ^= s >> 16
    out, acc = [], 0
    for _ in range(8):
        s = (s + acc + 0x9E3779B9) & M32
        acc = (acc + 0x7f4a7c15) & M32
        t = s ^ (s >> 13); t = (t * 0x85ebca6b) & M32; t ^= t >> 16
        u = t ^ (t >> 16)
        out.append(u & M16); s = t
    return out
```

对拍验证（模型输出 = 真实二进制输出）：

```
./encryptor "flag{1234567_89ABCDE}" /tmp/t1.bin   →  与 python3 model.py 1234567 89ABCDE 完全一致
```

---

## 3. 攻击：中间相遇（Meet-in-the-Middle）

轮函数**完全可逆**：

- `rotl16` / `+ w + c` 直接逆；
- `y = x ^ (x >> k)` 的逆用不动点迭代 `x ← y ^ (x >> k)`，16 bit 下迭代 3 次即收敛。

```python
def rnd_inv(y, w, c):
    y = rotr16(y, 9)
    y = inv_xor_shr(y, 7)
    y = rotr16((y - w - c) & M16, 3)
    return inv_xor_shr(y, 5)
```

但两侧密钥各 24 bit，共 2^48，且两个 prng seed 不同，不能独立分治。利用"第二轮只依赖中间态 S1"这一点做 MITM：

1. **正向**：枚举 X ∈ [0, 2²⁴)，算 `S1 = F(IV, ks1)`，取 `lane0 | lane1<<16` 作为 32 bit key，建表（2²⁴ × 8 B ≈ 128 MiB）并排序；
2. **反向**：枚举 Y ∈ [0, 2²⁴)，从密文的 lane0/lane1 逆推 `S1' = F⁻¹(OUT, ks2)`，取同样 32 bit key，二分查表；
3. 期望候选数 = 2⁴⁸ / 2³² = 2¹⁶ = 65536，对每个候选做 16 lane 全量正向校验。

复杂度：时间 ≈ 2 × 2²⁴ 次轮函数（单线程约 20 s），内存 ≈ 128 MiB。实现见 `solve.c`。

**结果（唯一解）：**

```
X & 0xffffff = 0x174812
Y & 0xffffff = 0x1AF718
```

（密文只含这两组 24 bit 的信息，完整 28 bit 值 `0x3174812` / `0x31AF718` 由平台判定补全，见第 4 节。）

---

## 4. Flag 与验证

密文 `cipher.bin`：

```
e717f224 9f53836b 6e1792c0 1ddf37d4
3782463c e9671154 6045b23d dd537527
```

```
$ ./encryptor "flag{3174812_31af718}" /tmp/ans.bin
wrote 32 bytes to /tmp/ans.bin
$ cmp /tmp/ans.bin cipher.bin            # 逐字节相同
```

**Flag：`flag{3174812_31af718}`**

平台返回（用于判定，正确/错误响应格式）：

```
错误：{"code":101,"message":"答案错误","is_switch":1}
正确：恭喜您，回答正确          —— 我的得分 101.00
```

### 关键难点：密文只编码 48 bit，flag 却有 56 bit

`prng` 第一句是 `and eax,0xffffff`，**只用了 X、Y 的低 24 bit**，而 flag 每组是 7 位十六进制（28 bit）；并且 `strtoul(...,16)` 对 `a-f/A-F` 一视同仁。于是：

- 每组**首位字符 d1、d2 不参与任何运算** —— 密文中不含它的任何信息（信息论上不可恢复）；
- **字母大小写同样不参与运算**。

因此合法原像是 `flag{d1}174812_{d2}1AF718}`（d1、d2 ∈ 0-f，大小写自由）共 **256 × 大小写变体** 个，用官方程序加密都精确得到同一份 `cipher.bin`：

```
./encryptor "flag{D1}174812_{D2}1AF718}" out.bin   # D1、D2 任意取 0-F
cmp out.bin cipher.bin     # 全部相同（已实测 256 种）
```

### 如何确定 d1、d2 与大小写（平台作为 oracle）

无法从数据推出，只能缩小范围后交给平台判定：

1. **大写 256 个全部判错** → 不是大写（先验证 `question_id` 确属本题，排除提交错位）；
2. **补零（`0174812`）与不补零（`174812`）的全部大小写组合判错** → X、Y 都 **> 0xFFFFFF**，即 **d1、d2 均 ≠ 0** → 候选从 256 缩到 **15×15 = 225**；
3. 作者最可能用 `os.urandom(7).hex()` 之类生成 → **全小写**优先枚举；
4. 用 `qwb_auto.py`（Playwright 驱动真实页面，签名由官方前端生成）以 5 秒间隔逐个提交，**第 33 条命中**：

```
X = 0x3174812  → 低 24 位 0x174812 ✓
Y = 0x31AF718  → 低 24 位 0x1AF718 ✓   （与 MITM 结果完全吻合）
```

这也反证了整个逆向与 MITM 的正确性：真正的 28 bit 值高位都是 `3`，而其低 24 位正是我们唯一恢复出的那一组。

---

## 5. 附件

| 文件 | 说明 |
|---|---|
| `model.py` | 加密器等价 Python 模型，自带往返自测（`python3 model.py`） |
| `solve.c` | MITM 求解器，`gcc -O2 -march=native -o solve solve.c && ./solve`，约 20 s 输出唯一解 |
| `qwb_auto.py` | Playwright 真实页面自动提交器（`.venv/bin/python qwb_auto.py --cands <清单> --delay 5`），命中即停 |
| `submit_log.txt` | 提交记录（含最终 `=== ANSWER flag{3174812_31af718} ===`） |
