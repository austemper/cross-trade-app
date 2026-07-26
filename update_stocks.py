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

def check_guide_updates():
    """SBI証券の信用取引ルールページを取得してハッシュを比較、変化があれば警告を出す"""
    import urllib.request
    import hashlib

    repo_dir = Path(__file__).parent
    hash_file = repo_dir / ".guide_check_hashes.json"

    # 監視対象URL（SBI証券の信用取引ルール・現渡し関連ページ）
    targets = {
        "sbi_shinyo_rule": "https://search.sbisec.co.jp/v2/popwin/attention/trading/stock_06.html",
        "sbi_trade_hours": "https://search.sbisec.co.jp/v2/popwin/help/trade_stock_08_01.html",
    }

    prev_hashes = {}
    if hash_file.exists():
        try:
            prev_hashes = json.loads(hash_file.read_text())
        except Exception:
            pass

    new_hashes = {}
    changed = []
    for key, url in targets.items():
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                content = resp.read()
            h = hashlib.sha256(content).hexdigest()
            new_hashes[key] = h
            if key in prev_hashes and prev_hashes[key] != h:
                changed.append(url)
        except Exception as e:
            print(f"  チェック失敗 ({key}): {e}")
            if key in prev_hashes:
                new_hashes[key] = prev_hashes[key]

    hash_file.write_text(json.dumps(new_hashes, ensure_ascii=False, indent=2))

    if changed:
        print("\n" + "="*60)
        print("⚠️  手順ガイド改訂チェック: 以下のページに変化を検出")
        for url in changed:
            print(f"   {url}")
        print("→ 手順ガイドの内容を確認・更新してください")
        print("="*60 + "\n")
    else:
        print("手順ガイドチェック: 変化なし")


def _estimate_kenri_tsuki(year, month):
    from datetime import date, timedelta
    last = date(year, month % 12 + 1, 1) - timedelta(days=1) if month < 12 else date(year, 12, 31)
    kakutei = last
    while kakutei.weekday() >= 5:
        kakutei -= timedelta(days=1)
    d, n = kakutei, 2
    while n > 0:
        d -= timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d

def _subtract_biz_days(d, n):
    from datetime import timedelta
    while n > 0:
        d -= timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d

def _next_biz_day(d):
    from datetime import timedelta
    d += timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d

def sync_google_calendar(stocks):
    """Google Calendarにクロス取引スケジュールを同期（credentials.json必須）"""
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
    except ImportError:
        print("Google Calendar同期スキップ: ライブラリ未インストール")
        print("  pip install google-api-python-client google-auth-oauthlib google-auth-httplib2")
        return

    repo_dir = Path(__file__).parent
    creds_path = repo_dir / "credentials.json"
    token_path = repo_dir / "token.json"

    if not creds_path.exists():
        print("Google Calendar同期スキップ: credentials.json が見つかりません")
        print("  → セットアップ手順: https://console.cloud.google.com/")
        print("    1. プロジェクト作成 → Google Calendar API 有効化")
        print("    2. OAuthクライアントID(デスクトップ)作成 → credentials.json をこのフォルダに配置")
        return

    SCOPES = ["https://www.googleapis.com/auth/calendar"]
    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
            creds = flow.run_local_server(port=0)
        token_path.write_text(creds.to_json())

    service = build("calendar", "v3", credentials=creds)

    # カレンダー取得または作成
    cal_name = "クロス取引スケジュール"
    cal_id = None
    for cal in service.calendarList().list().execute().get("items", []):
        if cal.get("summary") == cal_name:
            cal_id = cal["id"]
            break
    if not cal_id:
        cal_id = service.calendars().insert(body={
            "summary": cal_name, "timeZone": "Asia/Tokyo",
            "description": "クロス取引スケジュール管理アプリ自動生成"
        }).execute()["id"]
        print(f"Googleカレンダー作成: {cal_name}")

    # 既存の自動イベント削除（過去30日〜未来180日）
    from datetime import datetime, timedelta, timezone
    tz = timezone.utc
    tmin = (datetime.now(tz) - timedelta(days=30)).isoformat()
    tmax = (datetime.now(tz) + timedelta(days=180)).isoformat()
    page_token = None
    deleted = 0
    while True:
        evs = service.events().list(
            calendarId=cal_id, timeMin=tmin, timeMax=tmax,
            privateExtendedProperty="source=cross-trade-app",
            pageToken=page_token, maxResults=250
        ).execute()
        for ev in evs.get("items", []):
            service.events().delete(calendarId=cal_id, eventId=ev["id"]).execute()
            deleted += 1
        page_token = evs.get("nextPageToken")
        if not page_token:
            break
    print(f"既存イベント削除: {deleted}件")

    # 新イベント作成
    import re as _re
    from datetime import date as _date
    today = _date.today()
    tag = {"source": "cross-trade-app"}
    created = 0

    for s in stocks:
        if s.get("generalCredit") != "○" or s.get("longTermRequired"):
            continue
        months = [int(m) for m in _re.findall(r"\d+", s.get("rightsMonth", ""))]
        for m in months:
            year = today.year
            kt = _estimate_kenri_tsuki(year, m)
            if (kt - today).days < -5:
                year += 1
                kt = _estimate_kenri_tsuki(year, m)
            if (kt - today).days < -5 or (kt - today).days > 90:
                continue

            flying = _subtract_biz_days(kt, 16)
            delivery = _next_biz_day(kt)
            name, code = s["name"], s["code"]
            benefit = s.get("benefit", "")
            price = s.get("price", "")
            score = s.get("crossScore", "")

            # フライング開始日（全日イベント）
            service.events().insert(calendarId=cal_id, body={
                "summary": f"🚀 [フライング開始] {name}({code})",
                "description": f"一般信用（短期15日）売り注文を発注可能\n優待: {benefit}\n株価: ¥{price}\nクロスお得度: {score}",
                "start": {"date": flying.isoformat()},
                "end": {"date": flying.isoformat()},
                "colorId": "2",
                "extendedProperties": {"private": tag},
            }).execute()

            # 権利付最終日（クロス注文 + 現渡し注文）
            service.events().insert(calendarId=cal_id, body={
                "summary": f"⚡ [クロス締切・現渡し注文] {name}({code})",
                "description": (
                    f"【朝 〜8:59】信用売り(一般/無期限)+現物買い を寄成で発注\n"
                    f"  または 引成(信用)+成行(現物) で15:25頃に発注\n"
                    f"  ※両方成行は不可（2021年7月以降）\n\n"
                    f"【16:00以降】現渡し注文を発注\n"
                    f"  SBI: 取引→信用取引→返済・現引現渡→現渡\n"
                    f"  ⚠️16:00前発注は当日約定で優待取得不可！\n\n"
                    f"優待: {benefit}\n株価: ¥{price}\nクロスお得度: {score}"
                ),
                "start": {"dateTime": f"{kt.isoformat()}T08:00:00", "timeZone": "Asia/Tokyo"},
                "end": {"dateTime": f"{kt.isoformat()}T17:00:00", "timeZone": "Asia/Tokyo"},
                "colorId": "11",
                "reminders": {"useDefault": False, "overrides": [
                    {"method": "popup", "minutes": 24*60},
                    {"method": "popup", "minutes": 60},
                ]},
                "extendedProperties": {"private": tag},
            }).execute()

            # 権利落ち日（現渡し約定確認）
            service.events().insert(calendarId=cal_id, body={
                "summary": f"✅ [現渡し約定確認] {name}({code})",
                "description": f"前日16:00以降に現渡し注文を発注済みであれば本日朝に約定処理される\nSBI証券で約定確認を行うこと",
                "start": {"date": delivery.isoformat()},
                "end": {"date": delivery.isoformat()},
                "colorId": "9",
                "extendedProperties": {"private": tag},
            }).execute()
            created += 1

    print(f"Google Calendar同期完了: {created}銘柄 × 3イベント = {created*3}件作成")


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

    # 手順ガイドの改訂チェック（SBI証券の主要ページを確認）
    check_guide_updates()

    # Google Calendar同期
    sync_google_calendar(fixed)

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
