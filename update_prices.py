#!/usr/bin/env python3
"""
毎日18時実行: 全銘柄の株価をYahoo Finance Japanから取得してindex.htmlを更新する
依存: pip install yfinance
"""

import json
import re
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

REPO = Path(__file__).parent
OUT = REPO / "stocks_all.json"
HTML = REPO / "index.html"


def fetch_prices(codes: list[str]) -> dict[str, int]:
    try:
        import yfinance as yf
    except ImportError:
        print("ERROR: yfinance未インストール: pip install yfinance")
        sys.exit(1)

    tickers = [f"{c}.T" for c in codes]
    print(f"株価取得中... {len(tickers)}銘柄")

    prices = {}
    # 100件ずつバッチ処理
    batch_size = 100
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i:i + batch_size]
        batch_codes = codes[i:i + batch_size]
        try:
            data = yf.download(batch, period="5d", auto_adjust=True, progress=False)
            close = data["Close"]
            for code, ticker in zip(batch_codes, batch):
                try:
                    series = close[ticker] if len(batch) > 1 else close
                    last = series.dropna().iloc[-1]
                    prices[code] = round(float(last))
                except Exception:
                    pass
        except Exception as e:
            print(f"  バッチ{i//batch_size+1} 失敗: {e}")
    return prices


def main():
    # 週末はスキップ（市場クローズ）
    if date.today().weekday() >= 5:
        print("週末のためスキップ")
        return

    if not OUT.exists():
        print("ERROR: stocks_all.json が見つかりません。先に update_stocks.py を実行してください。")
        sys.exit(1)

    stocks = json.loads(OUT.read_text())
    codes = [s["code"] for s in stocks if s.get("code")]

    prices = fetch_prices(codes)
    print(f"取得成功: {len(prices)}/{len(codes)}件")

    updated = 0
    for s in stocks:
        if s["code"] in prices:
            s["price"] = f"{prices[s['code']]:,}"
            updated += 1

    OUT.write_text(json.dumps(stocks, ensure_ascii=False, indent=2))

    if not HTML.exists():
        print(f"完了: {updated}銘柄の株価を更新 (index.html なし)")
        return

    inline_json = json.dumps(stocks, ensure_ascii=False, separators=(',', ':'))
    html = HTML.read_text()
    html = re.sub(
        r'const STOCKS_DATA = \[.*?\];',
        f'const STOCKS_DATA = {inline_json};',
        html, flags=re.DOTALL
    )
    HTML.write_text(html)

    now_str = datetime.now().strftime('%Y-%m-%d')
    for cmd in [
        ["git", "-C", str(REPO), "add", "index.html", "stocks_all.json"],
        ["git", "-C", str(REPO), "commit", "-m", f"update: 株価更新 {now_str}"],
        ["git", "-C", str(REPO), "push"],
    ]:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0 and "nothing to commit" not in result.stdout + result.stderr:
            print(f"git: {result.stderr.strip()}")

    print(f"完了: {updated}銘柄の株価を更新 / {datetime.now().strftime('%Y-%m-%d %H:%M')}")


if __name__ == "__main__":
    main()
