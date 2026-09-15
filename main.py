import hashlib
import json
import os
import re
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


def parse_records(html):
    soup = BeautifulSoup(html, "html.parser")

    # The official page is rendered as repeated blocks containing these labels.
    # We intentionally parse visible text rather than relying on Toyota's CSS class names,
    # which are more likely to change.
    lines = [normalize(x) for x in soup.stripped_strings]
    records = []
    current = None
    label_map = {
        "出発店舗": "departure",
        "返却店舗": "arrival",
        "出発期間": "period",
        "車種": "car",
        "車両条件": "condition",
        "予約電話番号": "phone",
    }

    i = 0
    while i < len(lines):
        line = lines[i]

        if line == "出発店舗":
            if current and current.get("departure"):
                records.append(current)
            current = {}
            if i + 1 < len(lines):
                current["departure"] = lines[i + 1]

        elif current is not None and line in label_map and line != "出発店舗":
            key = label_map[line]
            if i + 1 < len(lines):
                value = lines[i + 1]
                # Some page elements put a label immediately before another label.
                if value not in label_map:
                    current[key] = value

        i += 1

    if current and current.get("departure"):
        records.append(current)

    # Remove obvious duplicates created by responsive/hidden DOM copies.
    unique = {}
    for r in records:
        fp = fingerprint(r)
        unique[fp] = r
    return list(unique.values())


def fingerprint(record):
    raw = "\x1f".join(
        record.get(k, "") for k in
        ("departure", "arrival", "period", "car", "condition", "phone")
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def matches(record):
    if FILTER_DEPARTURE and FILTER_DEPARTURE not in record.get("departure", ""):
        return False
    if FILTER_ARRIVAL and FILTER_ARRIVAL not in record.get("arrival", ""):
        return False
    if FILTER_KEYWORD:
        haystack = " ".join(record.values())
        if FILTER_KEYWORD.lower() not in haystack.lower():
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
    # Keep the state bounded.
    STATE_FILE.write_text(
        json.dumps(list(state)[-5000:], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def discord_send(record):
    def esc(s):
        return s.replace("\\", "\\\\").replace("*", "\\*").replace("_", "\\_")

    fields = [
        {"name": "出発", "value": esc(record.get("departure", "不明")), "inline": False},
        {"name": "返却", "value": esc(record.get("arrival", "不明")), "inline": False},
        {"name": "期間", "value": esc(record.get("period", "不明")), "inline": True},
        {"name": "車種", "value": esc(record.get("car", "不明")), "inline": True},
        {"name": "条件", "value": esc(record.get("condition", "不明")), "inline": False},
        {"name": "予約電話", "value": esc(record.get("phone", "不明")), "inline": True},
    ]

    payload = {
        "username": "片道GO通知",
        "embeds": [{
            "title": "🚗 片道GO 新着",
            "url": URL,
            "fields": fields,
        }],
    }

    r = requests.post(WEBHOOK_URL, json=payload, timeout=20)
    r.raise_for_status()


def main():
    r = requests.get(URL, headers=HEADERS, timeout=30)
    r.raise_for_status()

    records = [r for r in parse_records(r.text) if matches(r)]
    print(f"取得: {len(records)}件")

    old = load_state()
    current = {fingerprint(r): r for r in records}

    if os.getenv("SEND_TEST") == "true" and current:
        first = next(iter(current.values()))
        print("テスト通知:", first)
        discord_send(first)
        return

    # First run is silent by default so the bot doesn't flood Discord with

    # First run is silent by default so the bot doesn't flood Discord with
    # every car currently listed on the official page.
    if not old:
        if current:
            first = next(iter(current.values()))
            print("初回テスト通知:", first)
            discord_send(first)
        save_state(set(current))
        print("初回実行: 現在掲載中の案件を記録しました")
        return

    new_ids = [fp for fp in current if fp not in old]

    for fp in new_ids:
        print("新着:", current[fp])
        discord_send(current[fp])

    save_state(set(current))
    print(f"新着通知: {len(new_ids)}件")


if __name__ == "__main__":
    main()
