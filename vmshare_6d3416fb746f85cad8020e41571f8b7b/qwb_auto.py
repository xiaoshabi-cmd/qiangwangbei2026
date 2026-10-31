#!/usr/bin/env python3
"""vmshare 题目：真实页面 UI 自动试提交（签名由官方前端生成，不伪造）。
  .venv/bin/python qwb_auto.py --cands submit_final.txt --limit 2   # 先验证流程
  .venv/bin/python qwb_auto.py --cands submit_final.txt             # 全量，命中即停
"""
import argparse, json, time, os
from playwright.sync_api import sync_playwright

CFG = "qwb_submit_config.json"
INPUT_SEL = "input[placeholder='请输入目标答案']"
BTN_SEL = "button.btn:has-text('提交')"
CARD_SEL = "li:has-text('vmshare')"
CRYPTO_SEL = "li:has-text('Crypto')"
MSG_SELS = [".el-message", ".el-message__content", ".el-dialog", ".el-notification",
            "[class*='message']", "[class*='toast']", "[class*='tips']", "[class*='modal']"]
OK = ["正确", "恭喜", "成功", "通过", "solved", "success", "correct"]
BAD = ["错误", "不对", "不正确", "失败", "wrong", "fail", "incorrect", "频繁", "太快"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cands", default="submit_final.txt")
    ap.add_argument("--start", type=int, default=1)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--delay", type=float, default=6)
    a = ap.parse_args()

    cfg = json.load(open(CFG, encoding="utf-8"))
    cands = [l.strip() for l in open(a.cands, encoding="utf-8")
             if l.strip() and not l.startswith("#")]
    cands = cands[a.start - 1:]
    if a.limit:
        cands = cands[:a.limit]

    log = open("submit_log.txt", "a", encoding="utf-8")
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = b.new_context(storage_state="auth.json")
        pg = ctx.new_page()
        pg.goto(cfg["url"], timeout=60000)
        pg.wait_for_timeout(5000)
        try:
            pg.click(CRYPTO_SEL); pg.wait_for_timeout(2500)
        except Exception as e:
            print("[warn] 切换 Crypto 失败:", e)
        pg.click(CARD_SEL); pg.wait_for_timeout(3500)
        pg.wait_for_selector(INPUT_SEL, timeout=20000)
        print("[ready] 已进入 vmshare 题目面板")

        for i, flag in enumerate(cands, 1):
            print(f"[{i}/{len(cands)}] {flag}", end=" ", flush=True)
            try:
                inp = pg.query_selector(INPUT_SEL)
                inp.click(); inp.fill(""); inp.fill(flag)
                before = pg.inner_text("body")
                btn = pg.query_selector(BTN_SEL)
                if not btn:
                    for el in pg.query_selector_all("button"):
                        if "提交" in (el.inner_text() or ""):
                            btn = el; break
                btn.click()
                pg.wait_for_timeout(2500)
                msg = ""
                for s in MSG_SELS:
                    for el in pg.query_selector_all(s):
                        try:
                            t = (el.inner_text() or "").strip()
                            if t and t not in before:
                                msg += " | " + t.replace("\n", " ")
                        except Exception:
                            pass
                after = pg.inner_text("body")
                if not msg:
                    diff = [w for w in OK + BAD if (w in after and w not in before)]
                    msg = "diff:" + ",".join(diff)
                low = msg.lower()
                ok = any(w.lower() in low for w in OK) and not any(w.lower() in low for w in BAD)
                print("->", msg[:150])
                log.write(f"{flag}\t{ok}\t{msg[:200]}\n"); log.flush()
                if ok:
                    print(f"\n########## SUCCESS: {flag} ##########\n{msg}")
                    log.write(f"=== ANSWER {flag} ===\n"); log.close(); b.close(); return
                if "频繁" in low or "太快" in low:
                    print("  [限流] 等 30s"); pg.wait_for_timeout(30000); continue
            except Exception as e:
                print("ERR", e); log.write(f"{flag}\tERR\t{e}\n"); log.flush()
            time.sleep(max(3, a.delay))
        print("[done] 本批跑完未命中")
        b.close()


if __name__ == "__main__":
    main()
