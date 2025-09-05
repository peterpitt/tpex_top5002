# TPEX Actions Starter

這是一個可直接用的 GitHub Actions 範例，每天盤後自動抓「上櫃三大法人買賣超（日）」並：
- 產生 `tpex_buy.csv`
- 上傳為 Actions Artifact
- 若檔案有更新，直接 commit 回 repo
- （可選）透過 Slack Webhook 通知

## 如何使用
1. 把整個專案放到你的 GitHub repo（public/private 皆可）。
2. 若要 Slack 通知：到 **Settings → Secrets and variables → Actions → New repository secret** 新增 `SLACK_WEBHOOK_URL`。
3. 到 **Settings → Actions → General → Workflow permissions** 勾選 **Read and write permissions**（讓 GITHUB_TOKEN 可推回 repo）。
4. Actions 會在台北時間 **每個交易日 16:10** 自動跑；可用 **Run workflow** 手動測試。

> cron: `10 8 * * 1-5` 是 UTC，等於台北 UTC+8 的 16:10。

## 本地測試
```bash
pip install requests
python tpex_insti_daily.py --side buy --date "" --out tpex_buy.csv
```

## 其它
- 如要抓「賣超榜」，把 workflow 的 `--side buy` 改成 `--side sell`。
- 非交易日會產生空 CSV，但 CI 不會失敗。

