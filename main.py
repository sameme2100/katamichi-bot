import hashlib
import json
import os
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

URL = os.getenv(
    "KATAMICHI_URL",
    "https://cp.toyota.jp/rentacar/?padid=ag270_fr_top_onewayma_m",
)

WEBHOOK_URL = os.environ["DISCORD_WEBHOOK_URL"]
STATE_FILE = Path(os.getenv("STATE_FILE", "state.json"))

FILTER_DEPARTURE = os.getenv("FILTER_DEPARTURE", "").strip()
FILTER_ARRIVAL = os.getenv("FILTER_ARRIVAL", "").strip()
FILTER_KEYWORD = os.getenv("FILTER_KEYWORD", "").strip()

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; KatamichiGoDiscordBot/1.0)"
}


def normalize(s):
    return re.sub(r"\s+", " ", s or "").strip()


def fingerprint(record):
    raw = "\x1f".join(
        record.get(k, "")
        for k in ("departure", "arrival", "period", "car", "condition", "phone")
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def parse_records(html):
    soup = BeautifulSoup(html, "html.parser")
    lines = [normalize(x) for x in soup.stripped_strings]

    labels = {
        "出発店舗",
        "返却店舗",
        "出発期間",
        "車種",
        "車両条件",
        "予約電話番号",
    }

    records = []

    # 「出発店舗」が出てくる位置ごとに1案件として処理する
    starts = [i for i, line in enumerate(lines) if line == "出発店舗"]

    for n, start in enumerate(starts):
        end = starts[n + 1] if n + 1 < len(starts) else len(lines)
        block = lines[start:end]

        # 最初の「出発店舗」はページ上部の見出しなので、
        # 実際の店舗名が取れなければスキップ
        def value_after(label):
            try:
                pos = block.index(label)
            except ValueError:
                return ""

            # ラベルの後ろから、別のラベルではない最初の文字列を探す
            for value in block[pos + 1:]:
                if value in labels:
                    continue
                if value in {"出発", "返却", "店舗"}:
                    continue
                return value

            return ""

        departure = value_after("出発店舗")
        arrival = value_after("返却店舗")
        period = value_after("出発期間")
        car = value_after("車種")
        condition = value_after("車両条件")

        # 電話番号は「予約電話番号」の後ろから探す
        phone = ""
        try:
            pos = block.index("予約電話番号")
            for value in block[pos + 1:]:
                if re.fullmatch(r"\d{2,4}-\d{2,4}-\d{3,4}", value):
                    phone = value
                    break
        except ValueError:
            pass

        # 店舗名らしい出発店舗が取れたものだけ採用
        if departure and arrival and period and car and condition:
            records.append({
                "departure": departure,
                "arrival": arrival,
                "period": period,
                "car": car,
                "condition": condition,
                "phone": phone,
            })

    # 重複除去
    unique = {}
    for record in records:
        unique[fingerprint(record)] = record

    return list(unique.values())


def matches(record):
    if FILTER_DEPARTURE and FILTER_DEPARTURE not in record.get("departure", ""):
        return False

    if FILTER_ARRIVAL and FILTER_ARRIVAL not in record.get("arrival", ""):
        return False

    if FILTER_KEYWORD:
        text = " ".join(record.values()).lower()
        if FILTER_KEYWORD.lower() not in text:
            return False

    return True


def load_state():
    if not STATE_FILE.exists():
        return set()

    try:
        return set(json.loads(STATE_FILE.read_text(encoding="utf-8")))
    except Exception:
        return set()


def save_state(state):
    STATE_FILE.write_text(
        json.dumps(list(state)[-5000:], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def discord_send(record):
    def esc(value):
        return (
            value.replace("\\", "\\\\")
            .replace("*", "\\*")
            .replace("_", "\\_")
        )

    fields = [
        {
            "name": "出発",
            "value": esc(record.get("departure", "不明")),
            "inline": False,
        },
        {
            "name": "返却",
            "value": esc(record.get("arrival", "不明")),
            "inline": False,
        },
        {
            "name": "期間",
            "value": esc(record.get("period", "不明")),
            "inline": True,
        },
        {
            "name": "車種",
            "value": esc(record.get("car", "不明")),
            "inline": True,
        },
        {
            "name": "条件",
            "value": esc(record.get("condition", "不明")),
            "inline": False,
        },
        {
            "name": "予約電話",
            "value": esc(record.get("phone", "不明")),
            "inline": True,
        },
    ]

    payload = {
        "username": "片道GO通知",
        "embeds": [
            {
                "title": "🚗 片道GO 新着",
                "url": URL,
                "fields": fields,
            }
        ],
    }

    r = requests.post(WEBHOOK_URL, json=payload, timeout=20)

    # Discordのレート制限
    if r.status_code == 429:
        try:
            retry_after = float(r.json().get("retry_after", 5))
        except Exception:
            retry_after = 5

        print(f"Discordレート制限。{retry_after}秒待機します")
        time.sleep(retry_after)

        r = requests.post(WEBHOOK_URL, json=payload, timeout=20)

    r.raise_for_status()


def main():
    response = requests.get(URL, headers=HEADERS, timeout=30)
    response.raise_for_status()

    records = [
        record
        for record in parse_records(response.text)
        if matches(record)
    ]

    print(f"取得: {len(records)}件")

    current = {
        fingerprint(record): record
        for record in records
    }

    old = load_state()

    # 初回実行
    # 現在掲載されているものを全部通知すると大量になるので、
    # テストとして1件だけ送る
    if not old:
        if current:
            first = next(iter(current.values()))
            print("初回通知:", first)
            discord_send(first)

        save_state(set(current))
        print("初回実行: 現在掲載中の案件を記録しました")
        return

    # 新着だけ通知
    new_ids = [fp for fp in current if fp not in old]

    for fp in new_ids:
        print("新着:", current[fp])
        discord_send(current[fp])

    save_state(set(current))
    print(f"新着通知: {len(new_ids)}件")


if __name__ == "__main__":
    main()
