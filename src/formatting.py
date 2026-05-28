"""Shared formatting and value-safety helpers.

Consolidates duplicated utilities that were previously defined independently
in reporting.render, reporting.metrics, and reporting.make_qc_gate.
"""

from __future__ import annotations

import math
import re

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Missing-value detection
# ---------------------------------------------------------------------------

def is_missing_value(x) -> bool:
    """Return True for None, NaN, and common NA-like string tokens."""
    if x is None:
        return True
    if isinstance(x, str):
        s = x.strip().lower()
        return s in {"", "nan", "na", "n/a", "none", "null"}
    try:
        return math.isnan(float(x))
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Numeric safety
# ---------------------------------------------------------------------------

def to_float_safe(x) -> float | None:
    """Convert *x* to float, returning None on any failure or NA-like input."""
    if is_missing_value(x):
        return None
    if isinstance(x, str):
        cleaned = re.sub(r"[^0-9eE+\-.]", "", x.strip())
        if cleaned in {"", "-", "+", ".", "-.", "+."}:
            return None
        try:
            return float(cleaned)
        except Exception:
            return None
    try:
        out = float(x)
        if np.isnan(out):
            return None
        return out
    except Exception:
        return None


def to_bool(value: object) -> bool:
    """Coerce *value* to bool (truthy strings: 1/true/t/yes/y)."""
    if isinstance(value, bool):
        return value
    txt = str(value).strip().lower()
    return txt in {"1", "true", "t", "yes", "y"}


# ---------------------------------------------------------------------------
# Money / numeric formatting
# ---------------------------------------------------------------------------

def fmt_money(x: float) -> str:
    """Format a dollar value with sign, magnitude abbreviation (K/M/B).

    Returns ``"NA"`` for NaN / missing values.
    """
    if is_missing_value(x):
        return "NA"
    v = float(x)
    sign = "-" if v < 0 else ""
    av = abs(v)
    if av >= 1_000_000_000:
        return f"{sign}${av / 1_000_000_000:.2f}B"
    if av >= 1_000_000:
        return f"{sign}${av / 1_000_000:.2f}M"
    if av >= 1_000:
        return f"{sign}${av / 1_000:.1f}K"
    return f"{sign}${av:,.2f}"


def fmt_money_short(x: float) -> str:
    """Alias kept for call-sites that used the ``_short`` variant."""
    return fmt_money(x)


def fmt_float_safe(x, digits: int = 6, missing_label: str = "-") -> str:
    """Format a float with *digits* decimals, returning *missing_label* for NA."""
    if is_missing_value(x):
        return missing_label
    return f"{float(x):.{digits}f}"


# ---------------------------------------------------------------------------
# QC status helpers
# ---------------------------------------------------------------------------

def status_bucket(value: object) -> str:
    """Normalize a QC status string to PASS / REVIEW / FAIL / UNKNOWN.

    Handles compound tokens like ``"PASS: looks good"`` by splitting on ``:``.
    """
    txt = str(value).strip()
    if not txt or txt.lower() in {"nan", "none", "na", "n/a"}:
        return "UNKNOWN"
    head = txt.split(":", 1)[0].strip().upper()
    if head in {"PASS", "REVIEW", "FAIL"}:
        return head
    return "UNKNOWN"
