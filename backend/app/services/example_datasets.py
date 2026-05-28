from __future__ import annotations

import csv
import io
import math
from datetime import date, timedelta

DEMO_COLUMNS = [
    "date",
    "subscriptions",
    "revenue_per_subscription",
    "meta_impressions",
    "meta_spend",
    "google_clicks",
    "google_spend",
    "tiktok_impressions",
    "tiktok_spend",
    "promo",
    "competitor_sales",
]

SCHEMA_PREVIEW_ROWS = [
    ["2024-01-01", "1245", "42.50", "1234567", "12345.67", "45678", "8765.43", "789012", "6543.21", "0.12", "98765"],
    ["2024-01-08", "1312", "41.80", "1345678", "13210.11", "47890", "9012.34", "812345", "6987.65", "0.10", "101234"],
    ["2024-01-15", "1398", "43.10", "1456789", "13987.65", "49123", "9543.21", "845678", "7234.56", "0.15", "103456"],
]


def _seeded_noise(index: int, salt: int) -> float:
    value = math.sin(index * 12.9898 + salt * 78.233) * 43758.5453
    return value - math.floor(value) - 0.5


def _fmt(value: float, digits: int = 2) -> str:
    return f"{value:.{digits}f}"


def rows_to_csv(rows: list[list[str]], columns: list[str] | None = None) -> str:
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(columns or DEMO_COLUMNS)
    writer.writerows(rows)
    return output.getvalue()


def blank_template_csv() -> str:
    return rows_to_csv([])


def schema_preview_csv() -> str:
    return rows_to_csv(SCHEMA_PREVIEW_ROWS)


def runnable_demo_rows(periods: int = 156) -> list[list[str]]:
    start = date(2023, 1, 2)
    rows: list[list[str]] = []
    for index in range(periods):
        current_date = start + timedelta(days=index * 7)
        week = index % 52
        annual = math.sin((2 * math.pi * week) / 52)
        summer = math.sin((2 * math.pi * (week - 18)) / 52)
        holiday = math.exp(-((week - 47) ** 2) / 28)
        promo_pulse = (0.22 if index % 26 == 7 else 0) + (0.16 if index % 39 == 12 else 0)
        promo_index = max(0, 0.08 + promo_pulse + _seeded_noise(index, 4) * 0.04)
        competitor_index = max(80, 105 + 7 * math.sin((2 * math.pi * (week + 9)) / 52) + _seeded_noise(index, 5) * 8)

        meta_spend = max(4200, 12800 + 2600 * annual + 1100 * math.sin(index / 5.5) + _seeded_noise(index, 1) * 2200)
        google_spend = max(3800, 11200 + 1800 * summer + 1400 * math.cos(index / 7.2) + _seeded_noise(index, 2) * 1900)
        tiktok_spend = max(2600, 7600 + 2100 * math.sin((2 * math.pi * (week + 15)) / 52) + 900 * math.cos(index / 4.7) + _seeded_noise(index, 3) * 1500)

        meta_impressions = max(100000, meta_spend * (92 + _seeded_noise(index, 6) * 12))
        google_clicks = max(5000, google_spend * (4.7 + _seeded_noise(index, 7) * 0.7))
        tiktok_impressions = max(80000, tiktok_spend * (118 + _seeded_noise(index, 8) * 18))
        subscriptions = max(
            300,
            690
            + 0.010 * math.sqrt(meta_impressions)
            + 0.055 * math.sqrt(google_clicks)
            + 0.007 * math.sqrt(tiktok_impressions)
            + 120 * annual
            + 260 * holiday
            + 250 * promo_index
            - 1.7 * (competitor_index - 100)
            + _seeded_noise(index, 9) * 65,
        )

        rows.append(
            [
                current_date.isoformat(),
                str(round(subscriptions)),
                "42.50",
                str(round(meta_impressions)),
                _fmt(meta_spend),
                str(round(google_clicks)),
                _fmt(google_spend),
                str(round(tiktok_impressions)),
                _fmt(tiktok_spend),
                _fmt(promo_index, 3),
                _fmt(competitor_index),
            ]
        )
    return rows


def runnable_demo_csv() -> str:
    return rows_to_csv(runnable_demo_rows())
