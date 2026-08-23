"""CLASSORA Rewards: ledger, wallet, vouchers, RBAC, expiry, concurrency."""

from __future__ import annotations

import threading
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.features import _modules, router
from src.auth.session import session_payload
from src.auth.tokens import encode_token
from src.rewards import ledger as L
from src.rewards import policy as P
from src.rewards import service as rewards


class MemoryStore:
    def __init__(self):
        self.tables = {}
        self.seq = {}
        self.lock = threading.Lock()

    def available(self, table):
        return True

    def last_error(self, table):
        return ""

    def insert(self, table, row):
        with self.lock:
            rows = self.tables.setdefault(table, [])
            payload = dict(row)
            payload.setdefault("id", self.seq.get(table, 1))
            self.seq[table] = int(payload["id"]) + 1
            rows.append(payload)
            return [payload]

    def select(self, table, **eq):
        rows = list(self.tables.get(table) or [])
        if not eq:
            return rows
        return [row for row in rows if all(row.get(key) == value for key, value in eq.items())]

    def update(self, table, match, values):
        with self.lock:
            changed = []
            for row in self.tables.setdefault(table, []):
                if all(row.get(key) == value for key, value in match.items()):
                    row.update(values)
                    changed.append(row)
            return changed

    def delete(self, table, **eq):
        with self.lock:
            kept, removed = [], []
            for row in self.tables.get(table) or []:
                if all(row.get(key) == value for key, value in eq.items()):
                    removed.append(row)
                else:
                    kept.append(row)
            self.tables[table] = kept
            return removed


def _bearer(role, **kwargs):
    if role == "student":
        session = session_payload(
            role="student",
            student={"student_id": kwargs.get("student_id", 1), "name": kwargs.get("name", "Aarav")},
        )
    elif role == "teacher":
        session = session_payload(role="teacher", teacher={"teacher_id": kwargs.get("teacher_id", 1), "username": kwargs.get("username", "tea")})
    elif role == "merchant":
        session = session_payload(
            role="merchant",
            merchant={"merchant_id": kwargs.get("merchant_id", 1), "name": kwargs.get("name", "Canteen")},
        )
    else:
        session = session_payload(
            role=role,
            staff={
                "staff_id": kwargs.get("staff_id", 1),
                "username": kwargs.get("username", role),
                "name": kwargs.get("name", role.title()),
                "role": role,
            },
        )
    return {"Authorization": f"Bearer {encode_token(session)}"}, session


def _client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


class LedgerTests(unittest.TestCase):
    def test_signed_points_are_integers(self):
        self.assertEqual(P.signed_points(P.TX_EARN, 150), 150)
        self.assertEqual(P.signed_points(P.TX_REDEEM, 100), -100)
        self.assertEqual(P.signed_points(P.TX_REVERSAL, 200), -200)
        self.assertEqual(P.signed_points(P.TX_REFUND, 100), 100)
        self.assertEqual(P.signed_points(P.TX_ADJUSTMENT, -50), -50)
        self.assertEqual(P.signed_points(P.TX_ADJUSTMENT, 50), 50)

    def test_wallet_fifo_and_expiry_lots(self):
        now = datetime(2026, 8, 23, tzinfo=timezone.utc)
        rows = [
            {"id": 1, "transaction_type": P.TX_EARN, "points": 100, "status": "POSTED", "created_at": "2026-08-01", "expires_at": "2026-08-25T00:00:00+00:00"},
            {"id": 2, "transaction_type": P.TX_REDEEM, "points": 40, "status": "POSTED", "created_at": "2026-08-10"},
        ]
        snap = L.wallet(rows, now=now, expiring_days=7)
        self.assertEqual(snap["available"], 60)
        self.assertEqual(snap["totalEarned"], 100)
        self.assertEqual(snap["totalRedeemed"], 40)
        self.assertEqual(snap["expiringSoon"], 60)


class RewardApiTests(unittest.TestCase):
    def setUp(self):
        self.mem = MemoryStore()
        rewards._RATES.clear()
        self.patches = [
            patch("src.rewards.service.store", self.mem),
            patch("src.success.notify.store", self.mem),
        ]
        for item in self.patches:
            item.start()
        rewards.ensure_seed()
        rewards.save_settings(
            {**rewards.get_settings(), "automatic_rewards_enabled": False, "leaderboard_enabled": False},
            {"user_role": "administrator", "staff_data": {"username": "seed"}},
        )
        self.client = _client()
        self.student, _ = _bearer("student", student_id=1)
        self.student2, _ = _bearer("student", student_id=2, name="Diya")
        self.faculty, _ = _bearer("faculty", staff_id=2, username="faculty1")
        self.admin, _ = _bearer("administrator", staff_id=9, username="admin1")
        self.counsellor, _ = _bearer("counsellor", staff_id=3, username="counsel1")
        self.teacher, _ = _bearer("teacher", teacher_id=1, username="tea")

    def tearDown(self):
        for item in self.patches:
            item.stop()

    def _award(self, headers, student_id, **kwargs):
        body = {
            "studentId": student_id,
            "category": kwargs.get("category", "SPORTS"),
            "achievementType": kwargs.get("achievementType", "PARTICIPATION"),
            "achievementLevel": kwargs.get("achievementLevel", "INTER_COLLEGE"),
            "title": kwargs.get("title", "Inter-college sports"),
            "description": kwargs.get("description", "Verified participation"),
            "evidence": {"note": "roster"},
            "idempotencyKey": kwargs.get("idempotencyKey", f"award-{student_id}-{kwargs.get('title', 'sports')}"),
            "eventKey": kwargs.get("eventKey", kwargs.get("title", "sports-event")),
            "occurredAt": kwargs.get("occurredAt", "2026-08-20T10:00:00+00:00"),
        }
        if "points" in kwargs:
            body["points"] = kwargs["points"]
            body["overrideReason"] = kwargs.get("overrideReason", "")
        return self.client.post("/api/rewards/awards", headers=headers, json=body)

    def _wallet(self, headers, student_id=None):
        q = f"?student_id={student_id}" if student_id is not None else ""
        return self.client.get(f"/api/rewards/wallet{q}", headers=headers)

    def test_modules_include_rewards(self):
        self.assertIn("My Rewards", _modules("student"))
        self.assertIn("CLASSORA Rewards", _modules("teacher"))
        self.assertIn("CLASSORA Rewards", _modules("faculty"))
        self.assertIn("Merchant Rewards", _modules("merchant"))
        self.assertNotIn("Dropout Root Causes", _modules("counsellor"))

    def test_approved_award_credits_ledger(self):
        res = self._award(self.faculty, 1)
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.json()["achievement"]["status"], "APPROVED")
        self.assertEqual(res.json()["achievement"]["awardedPoints"], 100)
        wallet = self._wallet(self.student).json()["wallet"]
        self.assertEqual(wallet["available"], 100)
        self.assertEqual(wallet["totalEarned"], 100)
        txns = self.client.get("/api/rewards/transactions", headers=self.student).json()["transactions"]
        self.assertEqual(txns[0]["type"], "EARN")
        self.assertEqual(txns[0]["points"], 100)

    def test_client_cannot_choose_points(self):
        res = self._award(self.faculty, 1, points=999, overrideReason="because I said so", title="typed-points")
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.json()["achievement"]["awardedPoints"], 100)

    def test_rejected_achievement_awards_zero(self):
        submitted = self.client.post("/api/rewards/achievements", headers=self.student, json={
            "category": "CERTIFICATION",
            "achievementType": "COMPLETION",
            "achievementLevel": "INSTITUTIONAL",
            "title": "AWS Cloud Practitioner",
            "description": "Certificate",
            "organization": "Amazon",
            "certificateId": "AWS-1",
            "evidence": {"url": "https://example.test/cert"},
            "idempotencyKey": "cert-1",
        })
        self.assertEqual(submitted.status_code, 200, submitted.text)
        self.assertEqual(submitted.json()["achievement"]["status"], "PENDING_VERIFICATION")
        aid = submitted.json()["achievement"]["id"]
        rejected = self.client.post(
            f"/api/rewards/requests/{aid}/reject",
            headers=self.faculty,
            json={"reason": "Certificate could not be verified."},
        )
        self.assertEqual(rejected.status_code, 200, rejected.text)
        self.assertEqual(self._wallet(self.student).json()["wallet"]["available"], 0)
        self.assertEqual(self._wallet(self.student).json()["wallet"]["totalEarned"], 0)

    def test_reject_requires_reason(self):
        submitted = self.client.post("/api/rewards/achievements", headers=self.student, json={
            "category": "NSS",
            "achievementType": "PARTICIPATION",
            "achievementLevel": "INSTITUTIONAL",
            "title": "NSS camp",
            "description": "Camp",
            "idempotencyKey": "nss-1",
        })
        aid = submitted.json()["achievement"]["id"]
        res = self.client.post(f"/api/rewards/requests/{aid}/reject", headers=self.faculty, json={"reason": ""})
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["detail"], "REASON_REQUIRED")

    def test_duplicate_achievement_does_not_double_credit(self):
        first = self._award(self.faculty, 1, idempotencyKey="dup-1", title="Same event", eventKey="cup-2026")
        second = self._award(self.faculty, 1, idempotencyKey="dup-1", title="Same event", eventKey="cup-2026")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json().get("notice"), "DUPLICATE_REQUEST")
        self.assertEqual(self._wallet(self.student).json()["wallet"]["available"], 100)
        earns = [row for row in self.mem.select("reward_transactions") if row.get("transaction_type") == "EARN"]
        self.assertEqual(len(earns), 1)

    def test_reversal_is_compensating_row(self):
        self._award(self.faculty, 1, title="to-reverse")
        earn = [row for row in self.mem.select("reward_transactions") if row.get("transaction_type") == "EARN"][0]
        original_points = earn["points"]
        res = self.client.post(
            f"/api/rewards/transactions/{earn['id']}/reverse",
            headers=self.admin,
            json={"reason": "Duplicate reward"},
        )
        self.assertEqual(res.status_code, 200, res.text)
        earn_after = [row for row in self.mem.select("reward_transactions") if row.get("id") == earn["id"]][0]
        self.assertEqual(earn_after["points"], original_points)
        self.assertEqual(earn_after["transaction_type"], "EARN")
        reversals = [row for row in self.mem.select("reward_transactions") if row.get("transaction_type") == "REVERSAL"]
        self.assertEqual(len(reversals), 1)
        self.assertEqual(reversals[0]["points"], 100)
        wallet = self._wallet(self.student).json()["wallet"]
        self.assertEqual(wallet["available"], 0)
        self.assertEqual(wallet["totalReversed"], 100)

    def test_adjustment_requires_reason_and_is_ledgered(self):
        res = self.client.post("/api/rewards/adjustments", headers=self.admin, json={
            "studentId": 1,
            "points": 50,
            "reason": "Institution correction",
        })
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(self._wallet(self.student).json()["wallet"]["available"], 50)
        kinds = [row.get("transaction_type") for row in self.mem.select("reward_transactions")]
        self.assertIn("ADJUSTMENT", kinds)

    def test_wallet_claim_and_insufficient_points(self):
        self._award(self.faculty, 1, title="base-100")
        merchant = self.client.post("/api/rewards/merchants", headers=self.admin, json={
            "name": "Campus Canteen",
            "category": "CANTEEN",
            "accessCode": "canteen-secret",
        }).json()["merchant"]
        cheap = self.client.post("/api/rewards/offers", headers=self.admin, json={
            "merchantId": merchant["id"],
            "title": "10% OFF",
            "pointsCost": 50,
            "discountType": "PERCENTAGE",
            "discountValue": 10,
            "terms": "Canteen only. Not cash.",
        }).json()["offer"]
        expensive = self.client.post("/api/rewards/offers", headers=self.admin, json={
            "merchantId": merchant["id"],
            "title": "₹100 OFF",
            "pointsCost": 100,
            "discountType": "FIXED_AMOUNT",
            "discountValue": 10000,
        }).json()["offer"]
        claimed = self.client.post(f"/api/rewards/offers/{cheap['id']}/claim", headers=self.student, json={"idempotencyKey": "claim-50"})
        self.assertEqual(claimed.status_code, 200, claimed.text)
        self.assertTrue(claimed.json()["voucher"]["token"])
        self.assertEqual(self._wallet(self.student).json()["wallet"]["available"], 50)
        fail = self.client.post(f"/api/rewards/offers/{expensive['id']}/claim", headers=self.student, json={"idempotencyKey": "claim-100"})
        self.assertEqual(fail.status_code, 400)
        self.assertEqual(fail.json()["detail"], "INSUFFICIENT_POINTS")
        self.assertEqual(self._wallet(self.student).json()["wallet"]["available"], 50)

    def test_claim_rolls_back_voucher_if_ledger_fails(self):
        self._award(self.faculty, 1, title="ledger-fail")
        merchant = self.client.post("/api/rewards/merchants", headers=self.admin, json={
            "name": "Stationery", "category": "STATIONERY", "accessCode": "stat-1",
        }).json()["merchant"]
        offer = self.client.post("/api/rewards/offers", headers=self.admin, json={
            "merchantId": merchant["id"], "title": "₹50 OFF", "pointsCost": 100,
            "discountType": "FIXED_AMOUNT", "discountValue": 5000,
        }).json()["offer"]
        original = self.mem.insert

        def flaky(table, row):
            if table == "reward_transactions" and row.get("transaction_type") == "REDEEM":
                return None
            return original(table, row)

        with patch.object(self.mem, "insert", side_effect=flaky):
            res = self.client.post(f"/api/rewards/offers/{offer['id']}/claim", headers=self.student, json={"idempotencyKey": "claim-fail"})
        self.assertEqual(res.status_code, 400)
        self.assertEqual(self._wallet(self.student).json()["wallet"]["available"], 100)
        statuses = [row.get("status") for row in self.mem.select("reward_vouchers")]
        self.assertTrue(all(status != "ACTIVE" for status in statuses))

    def test_refund_does_not_edit_original_redeem(self):
        self._award(self.faculty, 1, title="refund-base")
        merchant = self.client.post("/api/rewards/merchants", headers=self.admin, json={
            "name": "Xerox", "category": "XEROX", "accessCode": "xerox-1",
        }).json()["merchant"]
        offer = self.client.post("/api/rewards/offers", headers=self.admin, json={
            "merchantId": merchant["id"], "title": "Print pack", "pointsCost": 100,
            "discountType": "FIXED_AMOUNT", "discountValue": 10000,
        }).json()["offer"]
        voucher = self.client.post(f"/api/rewards/offers/{offer['id']}/claim", headers=self.student, json={"idempotencyKey": "claim-ref"}).json()["voucher"]
        redeem_row = [row for row in self.mem.select("reward_transactions") if row.get("transaction_type") == "REDEEM"][0]
        original_points = redeem_row["points"]
        cancel = self.client.post(
            f"/api/rewards/vouchers/{voucher['id']}/cancel",
            headers=self.admin,
            json={"reason": "Merchant temporarily unavailable.", "refund": True},
        )
        self.assertEqual(cancel.status_code, 200, cancel.text)
        redeem_after = [row for row in self.mem.select("reward_transactions") if row.get("id") == redeem_row["id"]][0]
        self.assertEqual(redeem_after["points"], original_points)
        self.assertEqual(redeem_after["transaction_type"], "REDEEM")
        refunds = [row for row in self.mem.select("reward_transactions") if row.get("transaction_type") == "REFUND"]
        self.assertEqual(len(refunds), 1)
        self.assertEqual(self._wallet(self.student).json()["wallet"]["available"], 100)

    def test_policy_change_does_not_rewrite_old_earn(self):
        first = self._award(
            self.faculty, 1,
            category="HACKATHON", achievementType="PARTICIPATION", achievementLevel="INSTITUTIONAL",
            title="Hack old policy", eventKey="hack-old",
        )
        self.assertEqual(first.json()["achievement"]["awardedPoints"], 100)
        policy = next(
            row for row in self.client.get("/api/rewards/policies", headers=self.admin).json()["policies"]
            if row["category"] == "HACKATHON" and row["achievementType"] == "PARTICIPATION"
        )
        updated = self.client.post("/api/rewards/policies", headers=self.admin, json={
            "id": policy["id"],
            "category": "HACKATHON",
            "achievementType": "PARTICIPATION",
            "achievementLevel": "INSTITUTIONAL",
            "points": 200,
            "approvalRequired": False,
        })
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertGreater(updated.json()["policy"]["version"], 1)
        second = self._award(
            self.admin, 2,
            category="HACKATHON", achievementType="PARTICIPATION", achievementLevel="INSTITUTIONAL",
            title="Hack new policy", eventKey="hack-new",
        )
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(second.json()["achievement"]["awardedPoints"], 200)
        old_earn = [row for row in self.mem.select("reward_transactions") if row.get("student_id") == 1 and row.get("transaction_type") == "EARN"][0]
        new_earn = [row for row in self.mem.select("reward_transactions") if row.get("student_id") == 2 and row.get("transaction_type") == "EARN"][0]
        self.assertEqual(old_earn["points"], 100)
        self.assertEqual(new_earn["points"], 200)

    def test_self_approval_blocked(self):
        pending = self._award(
            self.faculty, 1,
            category="SPORTS", achievementType="PARTICIPATION", achievementLevel="INTER_UNIVERSITY",
            title="Inter-university", eventKey="iu-1",
        )
        self.assertEqual(pending.json()["achievement"]["status"], "PENDING_APPROVAL")
        aid = pending.json()["achievement"]["id"]
        blocked = self.client.post(f"/api/rewards/requests/{aid}/approve", headers=self.faculty, json={})
        self.assertEqual(blocked.status_code, 403)
        self.assertEqual(blocked.json()["detail"], "SELF_APPROVAL_FORBIDDEN")
        self.assertEqual(self._wallet(self.student).json()["wallet"]["available"], 0)
        approved = self.client.post(f"/api/rewards/requests/{aid}/approve", headers=self.admin, json={})
        self.assertEqual(approved.status_code, 200, approved.text)
        self.assertEqual(self._wallet(self.student).json()["wallet"]["available"], 150)

    def test_double_approve_does_not_double_credit(self):
        pending = self._award(
            self.faculty, 1,
            category="SPORTS", achievementType="PARTICIPATION", achievementLevel="INTER_UNIVERSITY",
            title="State wait", eventKey="iu-2",
        )
        aid = pending.json()["achievement"]["id"]
        self.client.post(f"/api/rewards/requests/{aid}/approve", headers=self.admin, json={})
        again = self.client.post(f"/api/rewards/requests/{aid}/approve", headers=self.admin, json={})
        self.assertEqual(again.status_code, 200)
        earns = [row for row in self.mem.select("reward_transactions") if row.get("transaction_type") == "EARN"]
        self.assertEqual(len(earns), 1)
        self.assertEqual(self._wallet(self.student).json()["wallet"]["available"], 150)

    def _merchant_offer(self, limit=None, cost=100):
        merchant = self.client.post("/api/rewards/merchants", headers=self.admin, json={
            "name": "Campus Canteen",
            "category": "CANTEEN",
            "accessCode": "scan-me",
        }).json()["merchant"]
        offer = self.client.post("/api/rewards/offers", headers=self.admin, json={
            "merchantId": merchant["id"],
            "title": "10% OFF",
            "pointsCost": cost,
            "discountType": "PERCENTAGE",
            "discountValue": 10,
            "redemptionLimit": limit,
            "perStudentLimit": 1,
        }).json()["offer"]
        return merchant, offer

    def test_validate_does_not_redeem(self):
        self._award(self.faculty, 1, title="for-scan")
        merchant, offer = self._merchant_offer()
        token = self.client.post(f"/api/rewards/offers/{offer['id']}/claim", headers=self.student, json={"idempotencyKey": "scan-1"}).json()["voucher"]["token"]
        login = self.client.post("/api/rewards/merchant/login", json={"merchantId": merchant["id"], "accessCode": "scan-me"})
        self.assertEqual(login.status_code, 200, login.text)
        mheaders = {"Authorization": f"Bearer {login.json()['token']}"}
        preview = self.client.post("/api/rewards/redemptions/validate", headers=mheaders, json={"token": token})
        self.assertEqual(preview.status_code, 200, preview.text)
        self.assertTrue(preview.json()["valid"])
        self.assertEqual(preview.json()["status"], "ACTIVE")
        self.assertNotIn("risk", str(preview.json()).lower())
        still = self.client.get("/api/rewards/vouchers", headers=self.student).json()["vouchers"][0]
        self.assertEqual(still["status"], "ACTIVE")

    def test_double_redemption_rejected(self):
        self._award(self.faculty, 1, title="for-redeem")
        merchant, offer = self._merchant_offer()
        token = self.client.post(f"/api/rewards/offers/{offer['id']}/claim", headers=self.student, json={"idempotencyKey": "red-1"}).json()["voucher"]["token"]
        login = self.client.post("/api/rewards/merchant/login", json={"merchantId": merchant["id"], "accessCode": "scan-me"})
        mheaders = {"Authorization": f"Bearer {login.json()['token']}"}
        first = self.client.post("/api/rewards/redemptions/confirm", headers=mheaders, json={"token": token})
        second = self.client.post("/api/rewards/redemptions/confirm", headers=mheaders, json={"token": token})
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(second.status_code, 400)
        self.assertEqual(second.json()["detail"], "VOUCHER_ALREADY_REDEEMED")
        redeemed = [row for row in self.mem.select("reward_vouchers") if row.get("status") == "REDEEMED"]
        self.assertEqual(len(redeemed), 1)

    def test_concurrent_redemption_one_winner(self):
        self._award(self.faculty, 1, title="race-redeem")
        merchant, offer = self._merchant_offer()
        token = self.client.post(f"/api/rewards/offers/{offer['id']}/claim", headers=self.student, json={"idempotencyKey": "race-red"}).json()["voucher"]["token"]
        login = self.client.post("/api/rewards/merchant/login", json={"merchantId": merchant["id"], "accessCode": "scan-me"})
        mheaders = {"Authorization": f"Bearer {login.json()['token']}"}
        results = []

        def confirm():
            results.append(self.client.post("/api/rewards/redemptions/confirm", headers=mheaders, json={"token": token}))

        threads = [threading.Thread(target=confirm) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        codes = sorted(row.status_code for row in results)
        self.assertEqual(codes, [200, 400])
        self.assertEqual(sum(1 for row in self.mem.select("reward_vouchers") if row.get("status") == "REDEEMED"), 1)

    def test_inventory_one_remaining(self):
        self._award(self.faculty, 1, title="inv-a")
        self._award(self.faculty, 2, title="inv-b")
        _merchant, offer = self._merchant_offer(limit=1, cost=100)
        results = []

        def claim(headers, key):
            results.append(self.client.post(f"/api/rewards/offers/{offer['id']}/claim", headers=headers, json={"idempotencyKey": key}))

        threads = [
            threading.Thread(target=claim, args=(self.student, "inv-1")),
            threading.Thread(target=claim, args=(self.student2, "inv-2")),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        oks = [row for row in results if row.status_code == 200]
        fails = [row for row in results if row.status_code == 400]
        self.assertEqual(len(oks), 1)
        self.assertEqual(len(fails), 1)
        self.assertEqual(fails[0].json()["detail"], "VOUCHER_UNAVAILABLE")
        offer_row = self.mem.select("reward_offers", id=offer["id"])[0]
        self.assertEqual(int(offer_row["claimed_count"]), 1)

    def test_point_expiry_writes_expire_row(self):
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        self.mem.insert("reward_transactions", {
            "student_id": 1,
            "transaction_type": "EARN",
            "points": 100,
            "status": "POSTED",
            "category": "SPORTS",
            "description": "expired lot",
            "expires_at": past,
            "created_at": "2026-01-01T00:00:00+00:00",
        })
        tick = self.client.post("/api/rewards/jobs/tick", headers=self.admin)
        self.assertEqual(tick.status_code, 200, tick.text)
        self.assertGreaterEqual(tick.json()["expiredPoints"], 100)
        expires = [row for row in self.mem.select("reward_transactions") if row.get("transaction_type") == "EXPIRE"]
        self.assertTrue(expires)
        wallet = self._wallet(self.student).json()["wallet"]
        self.assertEqual(wallet["available"], 0)
        self.assertEqual(wallet["totalExpired"], 100)
        earns = [row for row in self.mem.select("reward_transactions") if row.get("transaction_type") == "EARN"]
        self.assertTrue(all(row.get("points") == 100 for row in earns))

    def test_voucher_expiry_blocks_redeem(self):
        self._award(self.faculty, 1, title="expiring-voucher")
        merchant, offer = self._merchant_offer()
        claimed = self.client.post(f"/api/rewards/offers/{offer['id']}/claim", headers=self.student, json={"idempotencyKey": "v-exp"})
        token = claimed.json()["voucher"]["token"]
        voucher_id = claimed.json()["voucher"]["id"]
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        self.mem.update("reward_vouchers", {"id": voucher_id}, {"expires_at": past})
        login = self.client.post("/api/rewards/merchant/login", json={"merchantId": merchant["id"], "accessCode": "scan-me"})
        mheaders = {"Authorization": f"Bearer {login.json()['token']}"}
        res = self.client.post("/api/rewards/redemptions/validate", headers=mheaders, json={"token": token})
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["detail"], "VOUCHER_EXPIRED")

    def test_wrong_merchant_cannot_redeem(self):
        self._award(self.faculty, 1, title="wrong-shop")
        merchant, offer = self._merchant_offer()
        other = self.client.post("/api/rewards/merchants", headers=self.admin, json={
            "name": "Book Store", "category": "BOOKS", "accessCode": "books-1",
        }).json()["merchant"]
        token = self.client.post(f"/api/rewards/offers/{offer['id']}/claim", headers=self.student, json={"idempotencyKey": "wrong-m"}).json()["voucher"]["token"]
        login = self.client.post("/api/rewards/merchant/login", json={"merchantId": other["id"], "accessCode": "books-1"})
        mheaders = {"Authorization": f"Bearer {login.json()['token']}"}
        res = self.client.post("/api/rewards/redemptions/confirm", headers=mheaders, json={"token": token})
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()["detail"], "MERCHANT_NOT_AUTHORIZED")

    def test_rbac_student_cannot_award(self):
        res = self._award(self.student, 1, title="self-award")
        self.assertEqual(res.status_code, 403)
        self.assertEqual(self._wallet(self.student).json()["wallet"]["available"], 0)

    def test_rbac_merchant_cannot_change_points_or_workspace(self):
        merchant_headers, _ = _bearer("merchant", merchant_id=1)
        award = self._award(merchant_headers, 1, title="merchant-award")
        self.assertEqual(award.status_code, 403)
        adjust = self.client.post("/api/rewards/adjustments", headers=merchant_headers, json={"studentId": 1, "points": 50, "reason": "no"})
        self.assertEqual(adjust.status_code, 403)
        workspace = self.client.get("/api/success/workspace", headers=merchant_headers)
        self.assertEqual(workspace.status_code, 403)
        dropout = self.client.get("/api/institutional-dropout/overview", headers=merchant_headers)
        self.assertEqual(dropout.status_code, 403)
        academic = self.client.get("/api/academic-years", headers=merchant_headers)
        self.assertEqual(academic.status_code, 403)

    def test_counsellor_cannot_view_dropout(self):
        res = self.client.get("/api/institutional-dropout/overview", headers=self.counsellor)
        self.assertEqual(res.status_code, 403)

    def test_faculty_cannot_reverse(self):
        self._award(self.faculty, 1, title="no-rev")
        earn = [row for row in self.mem.select("reward_transactions") if row.get("transaction_type") == "EARN"][0]
        res = self.client.post(f"/api/rewards/transactions/{earn['id']}/reverse", headers=self.faculty, json={"reason": "no"})
        self.assertEqual(res.status_code, 403)

    def test_tampered_token_rejected(self):
        self._award(self.faculty, 1, title="tamper")
        merchant, offer = self._merchant_offer()
        self.client.post(f"/api/rewards/offers/{offer['id']}/claim", headers=self.student, json={"idempotencyKey": "tamper-1"})
        login = self.client.post("/api/rewards/merchant/login", json={"merchantId": merchant["id"], "accessCode": "scan-me"})
        mheaders = {"Authorization": f"Bearer {login.json()['token']}"}
        res = self.client.post("/api/rewards/redemptions/validate", headers=mheaders, json={"token": "not-a-real-token"})
        self.assertEqual(res.status_code, 404)

    def test_analytics_are_numeric(self):
        self._award(self.faculty, 1, title="analytics")
        data = self.client.get("/api/rewards/analytics", headers=self.admin).json()
        self.assertIsInstance(data["pointsIssued"], int)
        self.assertIsInstance(data["redemptionRate"], (int, float))
        self.assertFalse(str(data["redemptionRate"]) == "nan")
        self.assertIn("do not claim that rewards caused", data["disclaimer"].lower())

    def test_leaderboard_off_by_default(self):
        data = self.client.get("/api/rewards/leaderboard", headers=self.student).json()
        self.assertFalse(data["enabled"])
        self.assertEqual(data["rows"], [])

    def test_rules_are_public_to_students(self):
        data = self.client.get("/api/rewards/rules", headers=self.student).json()
        self.assertEqual(data["educationLevel"], "UNDERGRADUATE")
        self.assertTrue(any(row["category"] == "SPORTS" for row in data["rules"]))
        self.assertIn("not money", data["note"].lower())

    def test_combined_categories_stack(self):
        self._award(self.faculty, 1, category="SPORTS", achievementType="PARTICIPATION", achievementLevel="INTER_COLLEGE", title="Sports", eventKey="s1")
        pending = self._award(self.faculty, 1, category="NSS", achievementType="PARTICIPATION", achievementLevel="INSTITUTIONAL", title="NSS", eventKey="n1")
        self.assertEqual(pending.status_code, 200, pending.text)
        self.assertEqual(self._wallet(self.student).json()["wallet"]["available"], 175)

    def test_reconcile_ok_on_clean_ledger(self):
        self._award(self.faculty, 1, title="recon")
        data = self.client.get("/api/rewards/reconcile", headers=self.admin).json()
        self.assertTrue(data["ok"])


if __name__ == "__main__":
    unittest.main()
