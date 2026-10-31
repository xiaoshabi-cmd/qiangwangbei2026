#!/usr/bin/env python3
"""Playwright 真实页面自动试提交（签名由官方 JS 生成，不伪造）。
用法:
  .venv/bin/python qwb_submit.py setup   --url https://match.ichunqiu.com/...
  .venv/bin/python qwb_submit.py inspect
  .venv/bin/python qwb_submit.py run     --cands submit_order.txt --delay 6
"""
import argparse, json, os, sys, time
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

CFG, PROFILE, STATE = "qwb_submit_config.json", ".pwprofile", "auth.json"
INPUT_SELS = ["input[placeholder*='flag' i]", "textarea[placeholder*='flag' i]",
              "input.el-input__inner", "textarea.el-textarea__inner", ".el-input__inner",
              "input[type='text']", "textarea"]
BTN_SELS = ["button:has-text('提交')", "a:has-text('提交')", "button:has-text('Submit')",
            "button:has-text('确定')", ".el-button--primary", "button"]
MSG_SELS = [".el-message", ".el-message-box", ".el-dialog", "[role='alert']",
            "[class*='message']", "[class*='toast']", "[class*='modal']"]
OK = ["正确", "恭喜", "成功", "通过", "success", "correct", "solved"]
BAD = ["错误", "不对", "不正确", "失败", "wrong", "incorrect", "fail", "频繁", "太快"]


def load():
    d = {"url": "", "input": "", "button": "", "msg": "", "delay": 6}
    if os.path.exists(CFG):
        d.update(json.load(open(CFG, encoding="utf-8")))
    return d


def save(c):
    json.dump(c, open(CFG, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


def first_visible(pg, sels, cfgkey, cfg):
    cand = cfg.get(cfgkey)
    if cand:
        el = pg.query_selector(cand)
        if el:
            return cand, el
    for s in sels:
        for el in pg.query_selector_all(s):
            try:
                if el.is_visible():
                    return s, el
            except Exception:
                pass
    return None, None


def cmd_setup(a):
    cfg = load()
    cfg["url"] = a.url or cfg["url"]
    save(cfg)
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(PROFILE, headless=False, args=["--no-sandbox"])
        pg = ctx.new_page()
        pg.goto(cfg["url"] or "https://match.ichunqiu.com/2026qwbs10")
        print("\n[setup] 浏览器已打开：请登录并进入本题页面，停在能看到 flag 输入框的地方。")
        input("[setup] 完成后在这里按回车 -> ")
        ctx.storage_state(path=STATE)
        print(f"[setup] 会话已保存到 {STATE}，当前URL: {pg.url}")
        cfg["url"] = pg.url
        save(cfg)
        ctx.close()


def cmd_inspect(a):
    cfg = load()
    with sync_playwright() as p:
        b = p.chromium.launch(headless=bool(a.headless), args=["--no-sandbox"])
        ctx = b.new_context(storage_state=STATE if os.path.exists(STATE) else None)
        pg = ctx.new_page()
        pg.goto(cfg["url"] or "https://match.ichunqiu.com/2026qwbs10", timeout=60000)
        pg.wait_for_timeout(3000)
        print("URL:", pg.url)
        for tag, sels in (("INPUT", INPUT_SELS), ("BUTTON", BTN_SELS)):
            print(f"--- {tag} ---")
            seen = set()
            for s in sels:
                for el in pg.query_selector_all(s):
                    try:
                        if not el.is_visible():
                            continue
                        ph = el.get_attribute("placeholder") or ""
                        cls = el.get_attribute("class") or ""
                        key = (tag, cls[:40], ph)
                        if key in seen:
                            continue
                        seen.add(key)
                        print(f"  sel={s} | cls={cls[:60]} | ph={ph[:40]} | txt={(el.inner_text() or '')[:20]}")
                    except Exception:
                        pass
        b.close()


def cmd_run(a):
    cfg = load()
    cands = [l.strip() for l in open(a.cands, encoding="utf-8")
             if l.strip() and not l.startswith("#")]
    cands = cands[a.start - 1:]
    if a.limit:
        cands = cands[:a.limit]
    log = open("submit_log.txt", "a", encoding="utf-8")
    with sync_playwright() as p:
        b = p.chromium.launch(headless=bool(a.headless), args=["--no-sandbox"])
        ctx = b.new_context(storage_state=STATE if os.path.exists(STATE) else None)
        pg = ctx.new_page()
        pg.goto(cfg["url"], timeout=60000)
        pg.wait_for_timeout(2500)
        for i, flag in enumerate(cands, 1):
            print(f"[{i}/{len(cands)}] {flag}", end=" ", flush=True)
            try:
                isel, inp = first_visible(pg, INPUT_SELS, "input", cfg)
                if not inp:
                    print("找不到输入框，停止"); break
                cfg["input"] = isel
                inp.click(); inp.fill(""); inp.fill(flag)
                bsel, btn = first_visible(pg, BTN_SELS, "button", cfg)
                if not btn:
                    print("找不到提交按钮，停止"); break
                cfg["button"] = bsel
                before = pg.inner_text("body")
                btn.click()
                pg.wait_for_timeout(2500)
                extra = ""
                for s in MSG_SELS:
                    for el in pg.query_selector_all(s):
                        try:
                            t = (el.inner_text() or "").strip()
                            if t and t not in before:
                                extra += " " + t
                        except Exception:
                            pass
                after = pg.inner_text("body")
                new = extra or (after[len(before):] if after.startswith(before[:50]) else after[:200])
                txt = (extra + " " + after[:300]).lower()
                ok = any(w.lower() in txt for w in OK) and not any(w.lower() in txt for w in BAD)
                print("->", (extra or "?")[:120])
                log.write(f"{flag}\t{ok}\t{(extra or '').replace(chr(10),' ')[:200]}\n"); log.flush()
                if ok:
                    print(f"\n########## SUCCESS: {flag} ##########")
                    log.write(f"=== ANSWER {flag} ===\n"); log.close(); b.close(); return
                if "频繁" in txt or "太快" in txt:
                    print("  被限流，等 30s 重试本条")
                    pg.wait_for_timeout(30000); continue
            except Exception as e:
                print("ERR", e); log.write(f"{flag}\tERR\t{e}\n"); log.flush()
            time.sleep(max(3, a.delay))
        print("[done] 跑完未命中")
        b.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["setup", "inspect", "run"])
    ap.add_argument("--url"); ap.add_argument("--cands", default="submit_order.txt")
    ap.add_argument("--start", type=int, default=1); ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--delay", type=float, default=6); ap.add_argument("--headless", action="store_true")
    a = ap.parse_args()
    {"setup": cmd_setup, "inspect": cmd_inspect, "run": cmd_run}[a.mode](a)
