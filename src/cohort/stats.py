"""Explainable statistical helpers for cohort anomaly detection.

No machine-learning models. Every value is finite or None — never NaN/Inf.
"""

from __future__ import annotations

import math


def finite(value, default=None):
    if value is None:
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(number) or math.isinf(number):
        return default
    return number


def safe_div(numerator, denominator, default=None):
    num = finite(numerator)
    den = finite(denominator)
    if num is None or den is None or den == 0:
        return default
    return finite(num / den, default)


def clamp(value, lo, hi):
    number = finite(value)
    if number is None:
        return None
    return max(lo, min(hi, number))


def mean(values):
    nums = [finite(v) for v in (values or [])]
    nums = [v for v in nums if v is not None]
    if not nums:
        return None
    return sum(nums) / len(nums)


def median(values):
    nums = sorted(v for v in (finite(x) for x in (values or [])) if v is not None)
    if not nums:
        return None
    mid = len(nums) // 2
    if len(nums) % 2:
        return nums[mid]
    return (nums[mid - 1] + nums[mid]) / 2.0


def stdev(values, sample=True):
    nums = [v for v in (finite(x) for x in (values or [])) if v is not None]
    n = len(nums)
    if n == 0:
        return None
    if n == 1:
        return 0.0
    avg = sum(nums) / n
    denom = (n - 1) if sample else n
    if denom <= 0:
        return 0.0
    variance = sum((x - avg) ** 2 for x in nums) / denom
    return math.sqrt(variance)


def mad(values):
    nums = [v for v in (finite(x) for x in (values or [])) if v is not None]
    if not nums:
        return None
    mid = median(nums)
    if mid is None:
        return None
    return median([abs(x - mid) for x in nums])


def percentage_point_change(current, baseline):
    cur = finite(current)
    base = finite(baseline)
    if cur is None or base is None:
        return None
    return round(cur - base, 2)


def relative_percentage_change(current, baseline):
    cur = finite(current)
    base = finite(baseline)
    if cur is None or base is None:
        return None
    if base == 0:
        return 0.0 if cur == 0 else None
    return round(100.0 * (cur - base) / abs(base), 2)


def z_score(current, baseline_values):
    cur = finite(current)
    avg = mean(baseline_values)
    spread = stdev(baseline_values)
    if cur is None or avg is None or spread is None:
        return None
    if spread == 0:
        if cur == avg:
            return 0.0
        return 4.5 if cur > avg else -4.5
    return finite((cur - avg) / spread)


def robust_z_score(current, baseline_values):
    """Median + MAD robust z-score (0.6745 scaling)."""
    cur = finite(current)
    mid = median(baseline_values)
    spread = mad(baseline_values)
    if cur is None or mid is None or spread is None:
        return None
    if spread == 0:
        if cur == mid:
            return 0.0
        return 4.5 if cur > mid else -4.5
    return finite(0.6745 * (cur - mid) / spread)


def ewma(values, alpha=0.3):
    nums = [v for v in (finite(x) for x in (values or [])) if v is not None]
    if not nums:
        return None
    alpha = clamp(alpha, 0.01, 0.99) or 0.3
    acc = nums[0]
    for item in nums[1:]:
        acc = alpha * item + (1 - alpha) * acc
    return acc


def affected_percentage(affected_count, cohort_size):
    size = finite(cohort_size, 0) or 0
    count = finite(affected_count, 0) or 0
    if size <= 0:
        return 0.0
    return round(100.0 * max(0.0, count) / size, 1)


def classify_severity(score, bands=None):
    bands = bands or {}
    value = finite(score, 0) or 0
    critical = finite(bands.get("critical_score"), 85) or 85
    high = finite(bands.get("high_score"), 70) or 70
    moderate = finite(bands.get("moderate_score"), 50) or 50
    watch = finite(bands.get("watch_score"), 30) or 30
    if value >= critical:
        return "CRITICAL"
    if value >= high:
        return "HIGH"
    if value >= moderate:
        return "MODERATE"
    if value >= watch:
        return "WATCH"
    return "NORMAL"


def anomaly_score(
    *,
    pp_change=None,
    robust_z=None,
    z=None,
    affected_pct=None,
    metric_count=1,
    persistence=0,
    confidence=0.6,
    rarity=None,
):
    """Normalized 0–100 score from explainable parts. Declines use absolute magnitude."""
    magnitude = min(40.0, abs(finite(pp_change, 0) or 0) * 1.75)
    rz = finite(robust_z)
    zz = finite(z)
    if rz is not None:
        z_part = min(25.0, abs(rz) * 7.0)
    elif zz is not None:
        z_part = min(25.0, abs(zz) * 6.0)
    else:
        z_part = min(18.0, abs(finite(pp_change, 0) or 0) * 0.7)
    aff = min(15.0, max(0.0, (finite(affected_pct, 0) or 0) * 0.15))
    multi = min(12.0, max(0, int(metric_count or 1) - 1) * 6.0)
    persist = min(8.0, max(0, int(persistence or 0)) * 2.0)
    rare = min(5.0, max(0.0, finite(rarity, 0) or 0))
    if (rz is not None and abs(rz) >= 4) or (zz is not None and abs(zz) >= 4):
        rare = max(rare, 5.0)
    raw = magnitude + z_part + aff + multi + persist + rare
    conf = clamp(confidence, 0.0, 1.0)
    if conf is None:
        conf = 0.6
    raw *= 0.78 + 0.22 * conf
    return round(min(100.0, max(0.0, raw)), 1)


def confidence_from_evidence(*, baseline_periods, min_periods, cohort_size, min_size, record_count, expected_count):
    periods = finite(baseline_periods, 0) or 0
    needed = max(1, finite(min_periods, 4) or 4)
    period_q = min(1.0, periods / needed)
    size = finite(cohort_size, 0) or 0
    size_q = min(1.0, size / max(1, finite(min_size, 10) or 10))
    rec = finite(record_count, 0) or 0
    exp = finite(expected_count)
    if exp and exp > 0:
        vol_q = min(1.0, rec / exp)
    else:
        vol_q = 0.55 if rec > 0 else 0.35
    value = 0.45 * period_q + 0.3 * size_q + 0.25 * vol_q
    return round(clamp(value, 0.2, 0.98) or 0.2, 2)
