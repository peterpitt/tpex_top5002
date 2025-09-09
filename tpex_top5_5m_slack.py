# -*- coding: utf-8 -*-
# tpex_top5_5m_slack.py  (含目前價 / 300根均價 + 顯示 bars_used/300, r2, Δ300%)
import os, re, argparse, json
import numpy as np, pandas as pd, requests, yfinance as yf

API = "https://www.tpex.org.tw/www/zh-tw/insti/sitcStat"
HEADERS = {"User-Agent":"Mozilla/5.0",
           "Referer":"https://www.tpex.org.tw/zh-tw/mainboard/trading/major-institutional/domestic-inst/day.html"}

def clean_code(x):
    return re.sub(r"\D","",str(x or ""))

def top5_codes():
    r = requests.get(API, params={"type":"Daily","date":"","searchType":"buy","id":"","response":"json"},
                     headers=HEADERS, timeout=30)
    r.raise_for_status()
    data = r.json()["tables"][0]["data"][:5]
    return [{"code":clean_code(row[1]), "name":row[2]} for row in data]

def fetch_5m(code, days=10):
    code = clean_code(code)
    if not code: return pd.DataFrame()
    for suf in (".TWO",".TW"):  # 先上櫃再上市
        try:
            df = yf.Ticker(f"{code}{suf}").history(
                period=f"{days}d", interval="5m", auto_adjust=False, prepost=False
            )
            if df is None or df.empty: 
                continue
            df = df.rename(columns=str.title)[["Open","High","Low","Close","Volume"]].copy()
            if df.index.tz is None:
                df.index = df.index.tz_localize("UTC").tz_convert("Asia/Taipei")
            else:
                df.index = df.index.tz_convert("Asia/Taipei")
            return df
        except Exception:
            continue
    return pd.DataFrame()

def judge_trend_300(df, window=300, r2_thresh=0.10, strength_abs=0.01):
    """
    回傳 (direction, meta)
    direction: 'UP' / 'DOWN' / 'FLAT'
    meta: {'last': float, 'sma': float, 'bars_used': int, 'strength': float, 'r2': float, 'status': str}
    strength ≈ 用 300 根的總變化幅度 (比例)，可解讀為 Δ300
    """
    if df.empty:
        return "FLAT", {"status":"no_data", "last":None, "sma":None, "bars_used":0, "strength":None, "r2":None}

    d = df.tail(window).dropna(subset=["Close"])
    n = len(d)
    last = float(d["Close"].iloc[-1]) if n else None
    sma = float(d["Close"].mean()) if n else None

    if n < max(60, int(window*0.6)):
        return "FLAT", {
            "status":"insufficient",
            "last": round(last,2) if last is not None else None,
            "sma": round(sma,2) if sma is not None else None,
            "bars_used": n,
            "strength": None,
            "r2": None
        }

    x = np.arange(n, dtype=float)
    y = d["Close"].astype(float).values
    slope, b = np.polyfit(x, y, 1)
    yhat = slope*x + b
    ss_res = float(np.sum((y - yhat)**2))
    ss_tot = float(np.sum((y - y.mean())**2))
    r2 = 0.0 if ss_tot==0 else (1 - ss_res/ss_tot)

    strength = float(slope * window / y.mean())  # ≈ 300 根總變化占比（Δ300）
    up_ok   = (strength >=  strength_abs) and (last > y.mean()) and (r2 >= r2_thresh)
    down_ok = (strength <= -strength_abs) and (last < y.mean()) and (r2 >= r2_thresh)
    direction = "UP" if up_ok else ("DOWN" if down_ok else "FLAT")

    return direction, {
        "status":"ok",
        "last": round(float(last), 2),
        "sma":  round(float(y.mean()), 2),
        "bars_used": n,
        "strength": round(strength, 4),
        "r2": round(r2, 4)
    }

def build_slack_lines(rows, window):
    arrow = {"UP":"⬆️","DOWN":"⬇️","FLAT":"➖","N/A":"❌"}
    lines = []
    for r in rows:
        last = "N/A" if r.get("last") is None else r["last"]
        sma  = "N/A" if r.get("sma")  is None else r["sma"]
        bars = r.get("bars", 0)
        r2   = r.get("r2")
        st   = r.get("strength")
        r2_s = "N/A" if r2 is None else f"{r2:.2f}"
        st_s = "N/A" if st is None else f"{st*100:+.1f}%"
        lines.append(f"{r['code']} {r['name']} {last} / {sma} {arrow.get(r['dir'],'➖')} | 5m: {bars}/{window} | r² {r2_s} | Δ{window} {st_s}")
    return "\n".join(lines)

def build_slack_blocks(rows, window, title="TPEx Top5（買超）— 5m×300 趨勢雷達"):
    def row_block(r):
        arrow = {"UP":"⬆️","DOWN":"⬇️","FLAT":"➖","N/A":"❌"}[r["dir"]]
        last = "N/A" if r.get("last") is None else f"{r['last']}"
        sma  = "N/A" if r.get("sma")  is None else f"{r['sma']}"
        bars = r.get("bars", 0)
        r2   = r.get("r2")
        st   = r.get("strength")
        r2_s = "N/A" if r2 is None else f"{r2:.2f}"
        st_s = "N/A" if st is None else f"{st*100:+.1f}%"
        enough = "✅" if bars >= window else "⚠️"
        return [
            {
                "type":"section",
                "text":{"type":"mrkdwn",
                        "text":f"*{r['code']} {r['name']}*  `{last}/{sma}`  {arrow}"}
            },
            {
                "type":"context",
                "elements":[
                    {"type":"mrkdwn","text":f"*5m:* {bars}/{window} {enough} • *r²:* {r2_s} • *Δ{window}:* {st_s}"}
                ]
            },
            {"type":"divider"}
        ]

    blocks = [
        {"type":"header","text":{"type":"plain_text","text":title}},
        {"type":"context","elements":[
            {"type":"mrkdwn","text":"*解讀*：Δ300 代表 300 根五分K 的總體趨勢強度；bars/300 若不足，多半是停牌或資料不足。"}
        ]},
        {"type":"divider"}
    ]
    for r in rows:
        blocks.extend(row_block(r))
    if blocks and blocks[-1].get("type") == "divider":
        blocks = blocks[:-1]
    return blocks

def send_slack(webhook, text=None, blocks=None):
    if not webhook:
        print("[err] SLACK_WEBHOOK_URL not provided")
        return
    payload = {"text": text or ""}
    if blocks:
        payload["blocks"] = blocks
    try:
        resp = requests.post(webhook, data=json.dumps(payload),
                             headers={"Content-Type":"application/json"}, timeout=15)
        print(f"[slack] status={resp.status_code} body={resp.text!r}")
    except Exception as e:
        print(f"[slack] request failed: {e}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--webhook", help="Slack Incoming Webhook URL (overrides env)")
    ap.add_argument("--window", type=int, default=300)
    ap.add_argument("--days", type=int, default=10)
    ap.add_argument("--strength", type=float, default=0.01, help="threshold for trend strength (±)")
    ap.add_argument("--r2", type=float, default=0.10, help="R^2 threshold")
    ap.add_argument("--title", default="TPEx Top5（買超）— 5m×300 趨勢雷達")
    args = ap.parse_args()

    webhook = (args.webhook or os.getenv("SLACK_WEBHOOK_URL","")).strip()

    watch = top5_codes()
    rows = []
    for it in watch:
        df = fetch_5m(it["code"], days=args.days)
        if df.empty:
            rows.append({"code":it["code"], "name":it["name"],
                         "dir":"N/A","last":None,"sma":None,"bars":0,"r2":None,"strength":None})
            continue
        direction, meta = judge_trend_300(df, window=args.window,
                                          r2_thresh=args.r2, strength_abs=args.strength)
        rows.append({
            "code":it["code"], "name":it["name"], "dir":direction,
            "last":meta.get("last"), "sma":meta.get("sma"),
            "bars":meta.get("bars_used",0), "r2":meta.get("r2"),
            "strength":meta.get("strength")
        })

    text = build_slack_lines(rows, args.window)
    print(text)
    blocks = build_slack_blocks(rows, args.window, title=args.title)
    send_slack(webhook, text=text, blocks=blocks)

if __name__ == "__main__":
    main()
