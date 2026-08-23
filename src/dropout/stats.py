"""Explainable association statistics for institutional dropout analysis.

Never returns NaN or Inf. Does not claim causation.
"""

from __future__ import annotations

import math

from src.cohort.stats import clamp, finite, safe_div


def dropout_rate(dropouts, total):
    return safe_div(100.0 * (finite(dropouts, 0) or 0), finite(total, 0), default=None)


def relative_risk(exposed_rate, comparison_rate):
    exp = finite(exposed_rate)
    comp = finite(comparison_rate)
    if exp is None or comp is None:
        return None
    if comp == 0:
        return None if exp == 0 else None
    return finite(round(exp / comp, 3))


def risk_difference(exposed_rate, comparison_rate):
    exp = finite(exposed_rate)
    comp = finite(comparison_rate)
    if exp is None or comp is None:
        return None
    return round(exp - comp, 2)


def odds_ratio(a, b, c, d):
    """OR from 2x2: exposed dropout (a), exposed retained (b), unexposed dropout (c), unexposed retained (d)."""
    aa, bb, cc, dd = finite(a, 0) or 0, finite(b, 0) or 0, finite(c, 0) or 0, finite(d, 0) or 0
    if min(aa, bb, cc, dd) == 0:
        aa, bb, cc, dd = aa + 0.5, bb + 0.5, cc + 0.5, dd + 0.5
    return finite(round((aa / bb) / (cc / dd), 3))


def chi_square_2x2(a, b, c, d):
    aa, bb, cc, dd = finite(a, 0) or 0, finite(b, 0) or 0, finite(c, 0) or 0, finite(d, 0) or 0
    n = aa + bb + cc + dd
    if n <= 0:
        return None, None
    row1, row2 = aa + bb, cc + dd
    col1, col2 = aa + cc, bb + dd
    if min(row1, row2, col1, col2) <= 0:
        return None, None
    chi = n * ((aa * dd - bb * cc) ** 2) / (row1 * row2 * col1 * col2)
    chi = finite(chi)
    if chi is None:
        return None, None
    p = _chi2_p_1df(chi)
    return round(chi, 3), p


def _chi2_p_1df(x):
    """Survival function of chi-square with 1 df: erfc(sqrt(x/2))."""
    if x is None or x < 0:
        return None
    p = math.erfc(math.sqrt(x / 2.0))
    return round(min(1.0, max(0.0, p)), 4)


def fisher_exact_2x2(a, b, c, d):
    """Two-sided Fisher exact p-value for a 2x2 table (small samples)."""
    aa, bb, cc, dd = int(finite(a, 0) or 0), int(finite(b, 0) or 0), int(finite(c, 0) or 0), int(finite(d, 0) or 0)
    n = aa + bb + cc + dd
    if n == 0:
        return None
    def _choose(n, k):
        if k < 0 or k > n:
            return 0.0
        k = min(k, n - k)
        out = 1.0
        for i in range(k):
            out *= (n - i) / (i + 1)
        return out

    def _prob(x):
        return _choose(aa + bb, x) * _choose(cc + dd, aa + cc - x) / _choose(n, aa + cc)

    lo = max(0, (aa + cc) - (cc + dd))
    hi = min(aa + bb, aa + cc)
    observed = _prob(aa)
    total = 0.0
    for x in range(lo, hi + 1):
        px = _prob(x)
        if px <= observed + 1e-15:
            total += px
    return round(min(1.0, max(0.0, total)), 4)


def association_p(a, b, c, d):
    n = (finite(a, 0) or 0) + (finite(b, 0) or 0) + (finite(c, 0) or 0) + (finite(d, 0) or 0)
    cells = [finite(a, 0) or 0, finite(b, 0) or 0, finite(c, 0) or 0, finite(d, 0) or 0]
    if n < 40 or min(cells) < 5:
        return fisher_exact_2x2(a, b, c, d), "fisher"
    _chi, p = chi_square_2x2(a, b, c, d)
    return p, "chi_square"


def confidence_label(*, exposed_n, comparison_n, p_value, min_n, relative_risk=None, risk_diff=None):
    if (finite(exposed_n, 0) or 0) < min_n or (finite(comparison_n, 0) or 0) < min_n:
        return "INSUFFICIENT_DATA"
    strong = False
    if p_value is not None and p_value < 0.05:
        strong = True
    if relative_risk is not None and relative_risk >= 1.8:
        strong = True
    if risk_diff is not None and abs(risk_diff) >= 10:
        strong = True
    if (exposed_n or 0) >= 30 and (comparison_n or 0) >= 30 and strong:
        return "HIGH"
    if strong:
        return "MODERATE"
    if p_value is not None and p_value < 0.15:
        return "MODERATE"
    return "LOW"


def classify_factor(*, relative_risk, risk_diff, trend, confidence):
    if confidence == "INSUFFICIENT_DATA":
        return "INSUFFICIENT_DATA"
    if trend == "EMERGING":
        return "EMERGING"
    if trend == "DECREASING":
        return "DECLINING"
    rr = finite(relative_risk, 1) or 1
    rd = finite(risk_diff, 0) or 0
    if rr >= 2.0 or rd >= 15:
        return "SIGNIFICANT"
    if rr >= 1.4 or rd >= 8:
        return "MODERATE"
    return "STABLE"


def classify_trend(series):
    """series: chronological rates. Returns INCREASING/STABLE/DECREASING/EMERGING/RESOLVED."""
    vals = [finite(v) for v in (series or [])]
    vals = [v for v in vals if v is not None]
    if len(vals) < 2:
        return "STABLE"
    first, last = vals[0], vals[-1]
    delta = last - first
    recent = vals[-1] - vals[-2]
    if last < 3 and first >= 8:
        return "RESOLVED"
    if len(vals) >= 3 and vals[-1] >= vals[-2] >= vals[-3] and (last - vals[-3]) >= 5:
        return "EMERGING"
    if recent >= 5 and delta >= 5:
        return "EMERGING"
    if delta >= 4:
        return "INCREASING"
    if delta <= -4:
        return "DECREASING"
    return "STABLE"


def sigmoid(z):
    z = clamp(z, -30, 30) or 0
    return 1.0 / (1.0 + math.exp(-z))


def logistic_fit(rows, feature_names, l2=0.6, steps=250, lr=0.15):
    """Simple L2-regularized logistic regression. rows: [{features..., y: 0/1}]."""
    names = list(feature_names)
    data = []
    for row in rows or []:
        y = 1 if row.get("y") else 0
        xs = [1.0]
        ok = True
        for name in names:
            val = finite(row.get(name))
            if val is None:
                ok = False
                break
            xs.append(val)
        if ok:
            data.append((xs, y))
    if len(data) < 20 or sum(y for _x, y in data) < 3:
        return None
    dim = len(names) + 1
    w = [0.0] * dim
    n = len(data)
    for _ in range(steps):
        grad = [0.0] * dim
        for xs, y in data:
            z = sum(wj * xj for wj, xj in zip(w, xs))
            err = sigmoid(z) - y
            for j in range(dim):
                grad[j] += err * xs[j]
        for j in range(dim):
            penalty = 0.0 if j == 0 else l2 * w[j]
            w[j] -= lr * ((grad[j] / n) + penalty)
    coef = {names[i]: round(w[i + 1], 4) for i in range(len(names))}
    return {"intercept": round(w[0], 4), "coefficients": coef, "n": n, "positives": sum(y for _x, y in data)}


def classification_metrics(pairs):
    """pairs: [(prob, y)]. Threshold 0.5. Safe on empty."""
    if not pairs:
        return {"precision": None, "recall": None, "f1": None, "auc": None}
    tp = fp = tn = fn = 0
    for prob, y in pairs:
        pred = 1 if (finite(prob, 0) or 0) >= 0.5 else 0
        if pred == 1 and y == 1:
            tp += 1
        elif pred == 1 and y == 0:
            fp += 1
        elif pred == 0 and y == 0:
            tn += 1
        else:
            fn += 1
    precision = safe_div(tp, tp + fp)
    recall = safe_div(tp, tp + fn)
    f1 = None
    if precision is not None and recall is not None and (precision + recall) > 0:
        f1 = round(2 * precision * recall / (precision + recall), 3)
    auc = roc_auc(pairs)
    return {
        "precision": round(precision, 3) if precision is not None else None,
        "recall": round(recall, 3) if recall is not None else None,
        "f1": f1,
        "auc": auc,
        "tp": tp, "fp": fp, "tn": tn, "fn": fn,
    }


def roc_auc(pairs):
    ranked = sorted(pairs, key=lambda item: finite(item[0], 0) or 0, reverse=True)
    pos = sum(1 for _p, y in ranked if y)
    neg = len(ranked) - pos
    if pos == 0 or neg == 0:
        return None
    tp = fp = 0
    prev_tpr = prev_fpr = 0.0
    area = 0.0
    last_score = None
    for score, y in ranked + [(None, None)]:
        if score != last_score and last_score is not None:
            tpr = tp / pos
            fpr = fp / neg
            area += (fpr - prev_fpr) * (tpr + prev_tpr) / 2.0
            prev_tpr, prev_fpr = tpr, fpr
        if y is None:
            break
        last_score = score
        if y:
            tp += 1
        else:
            fp += 1
    return round(min(1.0, max(0.0, area)), 3)


def predict_proba(row, model, feature_names):
    if not model:
        return None
    z = finite(model.get("intercept"), 0) or 0
    coef = model.get("coefficients") or {}
    for name in feature_names:
        val = finite(row.get(name))
        if val is None:
            return None
        z += (finite(coef.get(name), 0) or 0) * val
    return sigmoid(z)
