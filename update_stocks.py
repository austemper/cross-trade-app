#!/usr/bin/env python3
"""
月1実行: kurosan99.tokyo/15851/ から全銘柄優待データを取得し stocks_all.json を更新する
使い方: python3 update_stocks.py
依存: pip install playwright && python -m playwright install chromium
"""

import json
import sys
from datetime import datetime
from pathlib import Path

OUT = Path(__file__).parent / "stocks_all.json"

def scrape():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        print("ページ取得中...")
        page.goto("https://kurosan99.tokyo/15851/", wait_until="domcontentloaded")

        # スクロールで全コンテンツをロード
        for i in range(1, 8):
            page.evaluate(f"window.scrollTo(0, document.body.scrollHeight * {i} / 7)")
            page.wait_for_timeout(600)
        page.wait_for_timeout(2000)

        stocks = page.evaluate("""() => {
            const result = [];
            const tds = Array.from(document.querySelectorAll('td'));
            const codeTds = tds.filter(td => /^\\d{4}$/.test(td.textContent.trim()));
            codeTds.forEach(codeTd => {
                const tr = codeTd.closest('tr');
                if (!tr) return;
                const cells = Array.from(tr.querySelectorAll('td'))
                    .map(td => td.textContent.trim().replace(/\\n/g, ' '));
                if (cells.length < 9) return;
                const longTermVal = cells[3];
                result.push({
                    name: cells[0],
                    code: cells[1] || cells[0],
                    rightsMonth: cells[2],
                    longTermRequired: longTermVal !== '' && longTermVal !== '長期 条件'
                        && longTermVal !== '長期' && longTermVal !== '-',
                    price: cells[4],
                    dividendYield: cells[5],
                    benefitScore: cells[6],
                    crossScore: cells[7],
                    benefit: cells[8],
                    generalCredit: cells[9] || '',
                    institutionalCredit: cells[10] || ''
                });
            });
            return result;
        }""")

        browser.close()
        return stocks

def main():
    try:
        stocks = scrape()
    except ImportError:
        print("ERROR: playwright未インストール。以下を実行してください:")
        print("  pip install playwright && python -m playwright install chromium")
        sys.exit(1)

    if not stocks:
        print("ERROR: 銘柄データ取得失敗（0件）")
        sys.exit(1)

    # コードが1列目に入っているケースを修正
    fixed = []
    for s in stocks:
        if s["name"] and s["name"] == s["code"]:
            continue  # 重複行スキップ
        import re
        if re.match(r"^\d{4}$", s["name"]):
            s["name"], s["code"] = s["code"], s["name"]
        fixed.append(s)

    OUT.write_text(json.dumps(fixed, ensure_ascii=False, indent=2))

    # index.html の STOCKS_DATA を更新
    html_path = Path(__file__).parent / "index.html"
    if html_path.exists():
        import re as _re
        inline_json = json.dumps(fixed, ensure_ascii=False, separators=(',', ':'))
        html = html_path.read_text()
        html = _re.sub(
            r'const STOCKS_DATA = \[.*?\];',
            f'const STOCKS_DATA = {inline_json};',
            html, flags=_re.DOTALL
        )
        html_path.write_text(html)
        print("index.html の STOCKS_DATA を更新しました")

    crossable = sum(1 for s in fixed if s["generalCredit"] == "○" and not s["longTermRequired"])
    print(f"完了: {len(fixed)}銘柄 / クロス可能: {crossable}件")
    print(f"保存先: {OUT}")
    print(f"更新日時: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    # GitHub Pages へ自動デプロイ
    import subprocess
    repo_dir = Path(__file__).parent
    now_str = datetime.now().strftime('%Y-%m-%d')
    cmds = [
        ["git", "-C", str(repo_dir), "add", "index.html", "stocks_all.json"],
        ["git", "-C", str(repo_dir), "commit", "-m", f"update: 銘柄データ更新 {now_str}"],
        ["git", "-C", str(repo_dir), "push"],
    ]
    for cmd in cmds:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0 and "nothing to commit" not in result.stdout:
            print(f"git エラー: {result.stderr.strip()}")
        else:
            print(result.stdout.strip() or f"{' '.join(cmd[2:])} 完了")

if __name__ == "__main__":
    main()
