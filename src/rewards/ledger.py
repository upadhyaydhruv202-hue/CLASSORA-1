"""Immutable-style reward ledger and derived wallet.

Accounting: every posted row is permanent. Corrections are new rows
(REVERSAL, REFUND, ADJUSTMENT, EXPIRE). Wallet is always computed
server-side from posted transactions. Points are integers.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.rewards.policy import TX_ADJUSTMENT, TX_EARN, TX_EXPIRE, parse_ts, signed_points


def _now():
    return datetime.now(timezone.utc)


def posted(rows):
    out = []
    for row in rows or []:
        if str(row.get("status") or "POSTED").upper() != "POSTED":
            continue
        out.append(row)
    out.sort(key=lambda row: str(row.get("created_at") or ""))
    return out


def wallet(rows, *, now=None, expiring_days=7):
    stamp = now or _now()
    lots = []
    earned = redeemed = expired = reversed_pts = 0
    pending = 0
    for row in rows or []:
        status = str(row.get("status") or "POSTED").upper()
        kind = str(row.get("transaction_type") or "")
        signed = signed_points(kind, row.get("points"))
        if status == "PENDING":
            if signed > 0:
                pending += signed
            continue
        if status != "POSTED":
            continue
        if signed > 0:
            earned += signed
            lots.append({
                "id": row.get("id"),
                "remaining": signed,
                "expires_at": parse_ts(row.get("expires_at")),
                "created_at": row.get("created_at"),
                "category": row.get("category"),
            })
        elif kind == TX_EXPIRE:
            expired += abs(signed)
            _consume(lots, abs(signed))
        elif kind == "REVERSAL":
            reversed_pts += abs(signed)
            _consume(lots, abs(signed))
        elif kind == "REDEEM":
            redeemed += abs(signed)
            _consume(lots, abs(signed))
        else:
            if signed < 0:
                _consume(lots, abs(signed))
            else:
                earned += signed
                lots.append({
                    "id": row.get("id"),
                    "remaining": signed,
                    "expires_at": parse_ts(row.get("expires_at")),
                    "created_at": row.get("created_at"),
                    "category": row.get("category"),
                })
    available = sum(lot["remaining"] for lot in lots)
    soon_cut = stamp + timedelta(days=max(1, int(expiring_days)))
    expiring = []
    for lot in lots:
        if lot["remaining"] <= 0:
            continue
        exp = lot.get("expires_at")
        if exp and stamp < exp <= soon_cut:
            expiring.append({
                "points": lot["remaining"],
                "expiresAt": exp.isoformat(),
                "transactionId": lot.get("id"),
            })
    due = [lot for lot in lots if lot["remaining"] > 0 and lot.get("expires_at") and lot["expires_at"] <= stamp]
    return {
        "available": int(available),
        "pending": int(pending),
        "locked": 0,
        "expiringSoon": int(sum(item["points"] for item in expiring)),
        "expiringLots": expiring,
        "expiredLots": [{"transactionId": lot.get("id"), "points": lot["remaining"]} for lot in due],
        "totalEarned": int(earned),
        "totalRedeemed": int(redeemed),
        "totalExpired": int(expired),
        "totalReversed": int(reversed_pts),
    }


def _consume(lots, amount):
    left = int(amount)
    for lot in lots:
        if left <= 0:
            break
        take = min(lot["remaining"], left)
        lot["remaining"] -= take
        left -= take
    return left


def expire_due(rows, *, now=None):
    """Lots whose remaining points are past expires_at."""
    snap = wallet(rows, now=now or _now(), expiring_days=0)
    return snap.get("expiredLots") or []


def as_of_available(rows, now=None):
    return int((wallet(rows, now=now) or {}).get("available") or 0)
