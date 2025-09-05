# tpex_insti_daily.py
# 目的：抓「上櫃—三大法人買賣超（日）」，輸出 CSV（不中斷 CI）
# 用法：
#   python tpex_insti_daily.py --side buy --date "" --out tpex_buy.csv
#   --date 留空抓最近交易日；也可填西元或民國：2025/09/01、20250901、114/09/01

import argparse, csv, re, sys
import requests
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

TRY_URL = "https://www.tpex.org.tw/www/zh-tw/insti/sitcStat"
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://www.tpex.org.tw/zh-tw/mainboard/trading/major-institutional/domestic-inst/day.html",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
}

def make_session():
    s = requests.Session()
    retry = Retry(
        total=5,
        backoff_factor=0.6,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        raise_on_status=False,
    )
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.headers.update(HEADERS)
    return s

def clean_code(x):
    return re.sub(r"\D", "", str(x or ""))

def to_num(x):
    if x is None: return 0
    if isinstance(x, (int, float)): return x
    s = str(x).replace(",", "").replace(" ", "")
    try:
        return int(s)
    except ValueError:
        try:
            return float(s)
        except ValueError:
            return 0

def normalize_date(d):
    d = (d or "").strip()
    if not d: return ""
    if "/" in d and len(d.split("/")[0]) <= 3:
        y, m, dd = d.split("/")
        y = int(y) + 1911
        return f"{y:04d}/{int(m):02d}/{int(dd):02d}"
    if re.fullmatch(r"\d{8}", d):
        return f"{d[0:4]}/{d[4:6]}/{d[6:8]}"
    return d

def fetch_daily(side="buy", date_str=""):
    params = {
        "type": "Daily",
        "date": normalize_date(date_str),
        "searchType": "buy" if side.lower() == "buy" else "sell",
        "id": "",
        "response": "json",
    }
    s = make_session()
    try:
        r = s.get(TRY_URL, params=params, timeout=30)
        r.raise_for_status()
        js = r.json()
    except requests.exceptions.SSLError:
        print("⚠️ SSL 憑證過於嚴格，改用 verify=False 再試一次。", file=sys.stderr)
        r = s.get(TRY_URL, params=params, timeout=30, verify=False)
        r.raise_for_status()
        js = r.json()

    tables = js.get("tables") or []
    if not tables:
        return (params["date"] or "最近交易日"), []

    data = tables[0].get("data") or []
    rows = []
    for row in data:
        code = clean_code(row[1] if len(row) > 1 else "")
        name = str(row[2] if len(row) > 2 else "")
        buy_val = to_num(row[3] if len(row) > 3 else 0)
        sell_val = to_num(row[4] if len(row) > 4 else 0)
        net = to_num(row[5] if len(row) > 5 else (buy_val - sell_val))
        if not code or not name:
            continue
        rows.append({
            "code": code,
            "name": name,
            "buy": int(buy_val),
            "sell": int(sell_val),
            "net": int(net),
        })
    return (params["date"] or "最近交易日"), rows

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--side", choices=["buy","sell"], default="buy")
    ap.add_argument("--date", default="")
    ap.add_argument("--out", default="tpex_buy.csv")
    args = ap.parse_args()

    day, rows = fetch_daily(args.side, args.date)

    # 不中斷 CI：非交易日輸出空檔案也回傳 0
    if not rows:
        print("⚠️ 今天沒有資料（可能非交易日或 API 無回應）。輸出空檔案並成功結束。")
        with open(args.out, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["code","name","buy","sell","net"])
            w.writeheader()
        sys.exit(0)

    rows.sort(key=lambda x: x["net"], reverse=(args.side=="buy"))
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["code","name","buy","sell","net"])
        w.writeheader()
        w.writerows(rows)

    print(f"✅ 抓到 {len(rows)} 筆（{day}, {args.side}）→ {args.out}")
    for r in rows[:5]:
        print(f"{r['code']} {r['name']}  買:{r['buy']:,} 賣:{r['sell']:,} 淨:{r['net']:,}")

if __name__ == "__main__":
    main()
