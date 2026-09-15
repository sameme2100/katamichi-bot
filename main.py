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
    lines = [normalize(x) for x in soup.stripped_strings]

    records = []
    current = None

    def next_value(start, skip):
        j = start
        while j < len(lines):
            if lines[j] not in skip:
                return lines[j], j
            j += 1
        return "", j

    skip = {
        "出発店舗",
        "返却店舗",
        "出発期間",
        "車種",
        "車両条件",
        "予約電話番号",
        "出発",
        "返却",
        "店舗",
    }

    i = 0
    while i < len(lines):
        if lines[i] != "出発店舗":
            i += 1
            continue

        # 「出発店舗」の次にある実際の店舗名を探す
        departure, j = next_value(i + 1, skip)

        # ページ上部の見出し部分は無視
        if not departure or "県" not in departure and "店" not in departure:
            i += 1
            continue

        current = {"departure": departure}

        # 返却店舗
        try:
            k = lines.index("返却店舗", j)
            arrival, k = next_value(k + 1, skip)
            current["arrival"] = arrival
        except ValueError:
            current["arrival"] = ""

        # 出発期間
        try:
            k = lines.index("出発期間", j)
            period, k = next_value(k + 1, skip)
            current["period"] = period
        except ValueError:
            current["period"] = ""

        # 車種
        try:
            k = lines.index("車種", j)
            car, k = next_value(k + 1, skip)
            current["car"] = car
        except ValueError:
            current["car"] = ""

        # 車両条件
        try:
            k = lines.index("車両条件", j)
            condition, k = next_value(k + 1, skip)
            current["condition"] = condition
        except ValueError:
            current["condition"] = ""

        # 予約電話番号
        try:
            k = lines.index("予約電話番号", j)
            # 電話番号の直前に店舗名が入るため、
            # 電話番号形式の文字列を探す
            phone = ""
            for candidate in lines[k + 1:k + 5]:
                if re.fullmatch(r"\d{2,4}-\d{2,4}-\d{3,4}", candidate):
                    phone = candidate
                    break
            current["phone"] = phone
        except ValueError:
            current["phone"] = ""

        if current["departure"] and current["arrival"]:
            records.append(current)

        i = j + 1

    # 重複除去
    unique = {}
    for r in records:
        unique[fingerprint(r)] = r

    return list(unique.values())
