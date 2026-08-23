import { useEffect, useState } from "react";
import { api } from "./api";
import { EmptyState, Field, Notice } from "./ui";

function formatWhen(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

function CategoryBars({ achievements }) {
  const families = [
    ["ACADEMIC", "Academic"],
    ["SPORTS", "Sports"],
    ["HACKATHON", "Innovation"],
    ["NSS", "Community"],
  ];
  const totals = {};
  (achievements || []).forEach((item) => {
    if (item.status !== "APPROVED") return;
    totals[item.category] = (totals[item.category] || 0) + Number(item.awardedPoints || 0);
  });
  const max = Math.max(1, ...Object.values(totals), 100);
  return (
    <div className="mt-4 space-y-2" aria-label="Achievement progress by category">
      {families.map(([code, label]) => {
        const value = totals[code] || 0;
        const width = Math.min(100, Math.round((value / max) * 100));
        return (
          <div key={code}>
            <p className="text-xs text-[#64748B]">{label} {value} pts</p>
            <div className="h-2 overflow-hidden rounded bg-[#E2E8F0]" aria-hidden="true">
              <div className="h-full bg-[#0F172A]" style={{ width: `${width}%` }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}

export function RewardHealthSummary({ summary, onOpen }) {
  const wallet = summary?.wallet;
  if (!summary?.available) {
    return <EmptyState title="You haven't earned any Reward Points yet." body="Start participating in academic, sports, innovation, community and campus activities." />;
  }
  return (
    <div className="space-y-3">
      <div className="co-chips co-anomaly-chips">
        <div><em>Available</em><strong>{wallet?.available ?? "—"}</strong></div>
        <div><em>Pending</em><strong>{wallet?.pending ?? "—"}</strong></div>
        <div><em>Expiring soon</em><strong>{wallet?.expiringSoon ?? "—"}</strong></div>
        <div><em>Redeemed</em><strong>{wallet?.totalRedeemed ?? "—"}</strong></div>
      </div>
      {onOpen && <button type="button" className="co-btn" onClick={onOpen}>Open My Rewards</button>}
    </div>
  );
}

export default function ClassoraRewards({ session, variant = "page" }) {
  const role = session?.user_role;
  const isStudent = role === "student";
  const isAdmin = role === "administrator";
  const isStaff = ["teacher", "faculty", "mentor", "counsellor", "administrator"].includes(role);
  const isMerchant = role === "merchant";
  const [tab, setTab] = useState(isMerchant ? "scan" : isStudent ? "home" : "award");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [wallet, setWallet] = useState(null);
  const [txns, setTxns] = useState([]);
  const [achs, setAchs] = useState([]);
  const [offers, setOffers] = useState([]);
  const [vouchers, setVouchers] = useState([]);
  const [rules, setRules] = useState(null);
  const [requests, setRequests] = useState(null);
  const [analytics, setAnalytics] = useState(null);
  const [merchants, setMerchants] = useState([]);
  const [claimedToken, setClaimedToken] = useState("");
  const [form, setForm] = useState({
    studentId: "", category: "SPORTS", achievementType: "PARTICIPATION",
    achievementLevel: "INTER_COLLEGE", title: "", description: "", organization: "",
    occurredAt: "", evidenceUrl: "", reason: "",
  });
  const [recommended, setRecommended] = useState(null);
  const [merchantForm, setMerchantForm] = useState({ name: "", category: "CANTEEN", location: "", accessCode: "" });
  const [offerForm, setOfferForm] = useState({ merchantId: "", title: "", pointsCost: 100, discountType: "PERCENTAGE", discountValue: 10, terms: "" });
  const [scan, setScan] = useState({ token: "", preview: null });
  const [submitForm, setSubmitForm] = useState({ category: "CERTIFICATION", achievementType: "COMPLETION", achievementLevel: "INSTITUTIONAL", title: "", description: "", organization: "", evidenceUrl: "" });

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      if (isStudent) {
        const [w, t, a, m, v, r] = await Promise.all([
          api.rewardWallet(),
          api.rewardTransactions({ limit: 40 }),
          api.rewardAchievements({ limit: 40 }),
          api.rewardMarketplace(),
          api.rewardVouchers(),
          api.rewardRules(),
        ]);
        setWallet(w.wallet);
        setTxns(t.transactions || []);
        setAchs(a.achievements || []);
        setOffers(m.offers || []);
        setVouchers(v.vouchers || []);
        setRules(r);
      } else if (isMerchant) {
        const v = await api.rewardVouchers();
        setVouchers(v.vouchers || []);
      } else if (isStaff) {
        const [req, r, mer] = await Promise.all([
          api.rewardRequests(),
          api.rewardRules(),
          api.rewardMerchants(),
        ]);
        setRequests(req);
        setRules(r);
        setMerchants(mer.merchants || []);
        if (isAdmin) {
          const an = await api.rewardAnalytics().catch(() => null);
          setAnalytics(an);
        }
      }
    } catch (err) {
      setError(err.message || "We couldn't load your rewards right now. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    if (!isStaff) return;
    api.recommendReward({ category: form.category, achievementType: form.achievementType, achievementLevel: form.achievementLevel })
      .then(setRecommended)
      .catch(() => setRecommended(null));
  }, [form.category, form.achievementType, form.achievementLevel, isStaff]);

  const run = async (fn, ok) => {
    setBusy(true);
    setNotice("");
    try {
      const result = await fn();
      setNotice(ok || "Saved.");
      await load();
      return result;
    } catch (err) {
      setNotice(err.message || "That action could not be completed.");
      return null;
    } finally {
      setBusy(false);
    }
  };

  if (variant === "embedded" && isStudent) {
    return <RewardHealthSummary summary={{ available: true, wallet }} onOpen={null} />;
  }

  const tabs = isStudent
    ? [["home", "Balance"], ["submit", "Submit"], ["market", "Marketplace"], ["vouchers", "My vouchers"], ["history", "History"], ["rules", "How to earn"]]
    : isMerchant
      ? [["scan", "Scan"], ["today", "Today"]]
      : [["award", "Award"], ["queue", "Approvals"], ...(isAdmin ? [["admin", "Admin"], ["analytics", "Analytics"]] : [])];

  return (
    <div className="space-y-4">
      <div>
        <p className="co-section-kicker">CLASSORA Rewards</p>
        <h2 className="text-xl font-semibold">{isStudent ? "My Rewards" : isMerchant ? "Merchant redemption" : "Recognize achievement"}</h2>
        <p className="text-sm text-[#64748B]">
          {isStudent
            ? "Improve. Participate. Achieve. Earn. Reward Points are institutional recognition, not money."
            : "Every award is verified, ledgered, and auditable. Points are calculated from policy, not typed by default."}
        </p>
      </div>
      {notice && <Notice title="Update" body={notice} tone="info" />}
      {error && <Notice title="Rewards unavailable" body={error} tone="danger" />}
      <div className="flex flex-wrap gap-2">
        {tabs.map(([id, label]) => (
          <button key={id} type="button" className={`co-btn ${tab === id ? "" : "co-btn-secondary"}`} onClick={() => setTab(id)}>{label}</button>
        ))}
      </div>
      {loading && (
        <div aria-busy="true">
          <div className="co-resource-skel" />
          <p className="mt-2 text-sm text-[#64748B]">Loading rewards…</p>
        </div>
      )}

      {!loading && isStudent && tab === "home" && (
        <div className="space-y-4">
          <div className="co-card">
            <p className="co-section-kicker">My Reward Points</p>
            <p className="co-reward-hero">{wallet ? wallet.available : "—"}</p>
            <p className="text-sm text-[#64748B]">Keep achieving. Keep earning.</p>
            <div className="co-chips co-anomaly-chips mt-3">
              <div><em>Pending</em><strong>{wallet?.pending ?? "—"}</strong></div>
              <div><em>Expiring soon</em><strong>{wallet?.expiringSoon ?? "—"}</strong></div>
              <div><em>Lifetime earned</em><strong>{wallet?.totalEarned ?? "—"}</strong></div>
              <div><em>Redeemed</em><strong>{wallet?.totalRedeemed ?? "—"}</strong></div>
            </div>
            {(wallet?.expiringLots || []).map((lot) => (
              <p key={lot.transactionId} className="mt-2 text-sm text-[#92400E]">{lot.points} points expire on {formatWhen(lot.expiresAt)}.</p>
            ))}
            <CategoryBars achievements={achs} />
          </div>
          <div className="co-card">
            <h3 className="mb-3 font-semibold">Achievement timeline</h3>
            {!achs.length && <EmptyState title="Your achievement history will appear here." />}
            {achs.map((item) => (
              <div key={item.id} className="mb-3 border-b border-[#E2E8F0] pb-3">
                <strong>{item.title}</strong>
                <p className="text-sm text-[#64748B]">{item.category} · {item.status} · {item.awardedPoints != null ? `+${item.awardedPoints}` : `proposed ${item.proposedPoints}`} · {formatWhen(item.createdAt)}</p>
                {item.reviewReason && <p className="text-sm text-[#92400E]">{item.reviewReason}</p>}
              </div>
            ))}
          </div>
        </div>
      )}

      {!loading && isStudent && tab === "submit" && (
        <div className="co-card space-y-3">
          <h3 className="font-semibold">Submit achievement</h3>
          <div className="co-anomaly-filters">
            <Field label="Category">
              <select className="co-input" value={submitForm.category} onChange={(e) => setSubmitForm({ ...submitForm, category: e.target.value })}>
                {(rules?.categories || []).map((c) => <option key={c.code} value={c.code}>{c.name}</option>)}
              </select>
            </Field>
            <Field label="Type"><input className="co-input" value={submitForm.achievementType} onChange={(e) => setSubmitForm({ ...submitForm, achievementType: e.target.value })} /></Field>
            <Field label="Level"><input className="co-input" value={submitForm.achievementLevel} onChange={(e) => setSubmitForm({ ...submitForm, achievementLevel: e.target.value })} /></Field>
          </div>
          <Field label="Title"><input className="co-input" value={submitForm.title} onChange={(e) => setSubmitForm({ ...submitForm, title: e.target.value })} /></Field>
          <Field label="Description"><textarea className="co-input" rows={3} value={submitForm.description} onChange={(e) => setSubmitForm({ ...submitForm, description: e.target.value })} /></Field>
          <Field label="Organization"><input className="co-input" value={submitForm.organization} onChange={(e) => setSubmitForm({ ...submitForm, organization: e.target.value })} /></Field>
          <Field label="Evidence URL"><input className="co-input" value={submitForm.evidenceUrl} onChange={(e) => setSubmitForm({ ...submitForm, evidenceUrl: e.target.value })} /></Field>
          <button type="button" className="co-btn" disabled={busy} onClick={() => run(() => api.submitRewardAchievement({
            ...submitForm,
            evidence: { url: submitForm.evidenceUrl },
          }), "Submitted for verification.")}>Submit</button>
        </div>
      )}

      {!loading && isStudent && tab === "market" && (
        <div className="space-y-3">
          {!offers.length && <EmptyState title="No reward vouchers are currently available." />}
          {offers.map((offer) => (
            <div key={offer.id} className="co-card">
              <h3 className="font-semibold">{offer.title}</h3>
              <p className="text-sm text-[#64748B]">{offer.merchant?.name} · {offer.discountType} {offer.discountValue} · {offer.pointsCost} points</p>
              <p className="text-sm text-[#64748B]">Min purchase {offer.minimumPurchase || 0} · Max discount {offer.maximumDiscount || "—"} · Per-student limit {offer.perStudentLimit || 1}</p>
              <p className="text-sm text-[#64748B]">{offer.terms || "Institutional closed-loop offer. Not cash. Not combinable unless the terms say so."}</p>
              <button type="button" className="co-btn mt-2" disabled={busy || (wallet && wallet.available < offer.pointsCost)} onClick={async () => {
                const result = await run(() => api.claimRewardOffer(offer.id), "Voucher claimed.");
                if (result?.voucher?.token) setClaimedToken(result.voucher.token);
              }}>Claim voucher</button>
            </div>
          ))}
          {claimedToken && (
            <Notice title="Show this redemption token to the merchant" body={claimedToken} tone="ok" />
          )}
        </div>
      )}

      {!loading && isStudent && tab === "vouchers" && (
        <div className="space-y-3">
          {!vouchers.length && <EmptyState title="No reward vouchers are currently available." body="Claim an offer from the marketplace." />}
          {vouchers.map((voucher) => (
            <div key={voucher.id} className="co-card">
              <strong>{voucher.title}</strong>
              <p className="text-sm text-[#64748B]">{voucher.status} · {voucher.merchant?.name} · expires {formatWhen(voucher.expiresAt)}</p>
              {voucher.token && <p className="mt-2 break-all font-mono text-sm">{voucher.token}</p>}
              <p className="text-sm text-[#94A3B8]">Hint {voucher.tokenHint}… The full token is shown only at claim time.</p>
            </div>
          ))}
        </div>
      )}

      {!loading && isStudent && tab === "history" && (
        <div className="co-card">
          {!txns.length && <EmptyState title="Reward history will appear here." />}
          {txns.map((row) => (
            <p key={row.id} className="mb-2 text-sm">
              <strong>{row.points > 0 ? "+" : ""}{row.points}</strong> {row.description} · {row.type} · {formatWhen(row.createdAt)}
            </p>
          ))}
        </div>
      )}

      {!loading && isStudent && tab === "rules" && (
        <div className="co-card">
          <p className="mb-3 text-sm text-[#64748B]">{rules?.note}</p>
          {(rules?.rules || []).map((group) => (
            <div key={group.category} className="mb-3">
              <strong>{group.category}</strong>
              {group.items.map((item) => <p key={item} className="text-sm text-[#64748B]">{item}</p>)}
            </div>
          ))}
        </div>
      )}

      {!loading && isStaff && tab === "award" && (
        <div className="co-card space-y-3">
          <h3 className="font-semibold">Recognize a student</h3>
          <div className="co-anomaly-filters">
            <Field label="Student ID"><input className="co-input" value={form.studentId} onChange={(e) => setForm({ ...form, studentId: e.target.value })} /></Field>
            <Field label="Category">
              <select className="co-input" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
                {(rules?.categories || []).map((c) => <option key={c.code} value={c.code}>{c.name}</option>)}
              </select>
            </Field>
            <Field label="Type"><input className="co-input" value={form.achievementType} onChange={(e) => setForm({ ...form, achievementType: e.target.value })} /></Field>
            <Field label="Level"><input className="co-input" value={form.achievementLevel} onChange={(e) => setForm({ ...form, achievementLevel: e.target.value })} /></Field>
          </div>
          <Field label="Title"><input className="co-input" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} /></Field>
          <Field label="Reason"><textarea className="co-input" rows={3} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></Field>
          <p className="text-sm text-[#334155]">Recommended points from policy: <strong>{recommended?.points ?? "—"}</strong>{recommended?.approvalRequired ? " (approval required)" : ""}</p>
          <button type="button" className="co-btn" disabled={busy} onClick={() => run(() => api.awardReward({
            studentId: Number(form.studentId),
            category: form.category,
            achievementType: form.achievementType,
            achievementLevel: form.achievementLevel,
            title: form.title,
            description: form.description,
            evidence: { note: form.description },
          }), "Recognition submitted.")}>Submit recognition</button>
        </div>
      )}

      {!loading && isStaff && tab === "queue" && (
        <div className="space-y-3">
          {!(requests?.pending || []).length && !(requests?.approval || []).length && <EmptyState title="No pending reward requests." />}
          {[...(requests?.pending || []), ...(requests?.approval || [])].map((item) => (
            <div key={item.id} className="co-card">
              <strong>{item.title}</strong>
              <p className="text-sm text-[#64748B]">Student {item.studentId} · {item.category} · {item.proposedPoints} pts · {item.status}</p>
              <p className="text-sm text-[#64748B]">{item.description}</p>
              <div className="mt-2 flex flex-wrap gap-2">
                <button type="button" className="co-btn" disabled={busy} onClick={() => run(() => api.approveReward(item.id), "Approved.")}>Approve</button>
                <button type="button" className="co-btn co-btn-secondary" disabled={busy} onClick={() => {
                  const reason = window.prompt("Rejection reason");
                  if (reason) run(() => api.rejectReward(item.id, { reason }), "Rejected.");
                }}>Reject</button>
              </div>
            </div>
          ))}
        </div>
      )}

      {!loading && isAdmin && tab === "admin" && (
        <div className="space-y-4">
          <div className="co-card space-y-3">
            <h3 className="font-semibold">Campus merchant</h3>
            <div className="co-anomaly-filters">
              <Field label="Name"><input className="co-input" value={merchantForm.name} onChange={(e) => setMerchantForm({ ...merchantForm, name: e.target.value })} /></Field>
              <Field label="Category"><input className="co-input" value={merchantForm.category} onChange={(e) => setMerchantForm({ ...merchantForm, category: e.target.value })} /></Field>
              <Field label="Access code"><input className="co-input" value={merchantForm.accessCode} onChange={(e) => setMerchantForm({ ...merchantForm, accessCode: e.target.value })} /></Field>
            </div>
            <button type="button" className="co-btn" disabled={busy} onClick={() => run(() => api.saveRewardMerchant(merchantForm), "Merchant saved.")}>Save merchant</button>
            <p className="text-sm text-[#64748B]">{merchants.length} merchants.</p>
          </div>
          <div className="co-card space-y-3">
            <h3 className="font-semibold">Offer</h3>
            <div className="co-anomaly-filters">
              <Field label="Merchant ID"><input className="co-input" value={offerForm.merchantId} onChange={(e) => setOfferForm({ ...offerForm, merchantId: e.target.value })} /></Field>
              <Field label="Title"><input className="co-input" value={offerForm.title} onChange={(e) => setOfferForm({ ...offerForm, title: e.target.value })} /></Field>
              <Field label="Points"><input className="co-input" type="number" value={offerForm.pointsCost} onChange={(e) => setOfferForm({ ...offerForm, pointsCost: Number(e.target.value) })} /></Field>
              <Field label="Discount value"><input className="co-input" type="number" value={offerForm.discountValue} onChange={(e) => setOfferForm({ ...offerForm, discountValue: Number(e.target.value) })} /></Field>
            </div>
            <button type="button" className="co-btn" disabled={busy} onClick={() => run(() => api.saveRewardOffer({ ...offerForm, merchantId: Number(offerForm.merchantId) }), "Offer saved.")}>Save offer</button>
          </div>
        </div>
      )}

      {!loading && isAdmin && tab === "analytics" && analytics && (
        <div className="co-card">
          <div className="co-chips co-anomaly-chips">
            <div><em>Issued</em><strong>{analytics.pointsIssued}</strong></div>
            <div><em>Redeemed</em><strong>{analytics.pointsRedeemed}</strong></div>
            <div><em>Expired</em><strong>{analytics.pointsExpired}</strong></div>
            <div><em>Pending</em><strong>{analytics.pendingApprovals}</strong></div>
          </div>
          <p className="mt-3 text-sm text-[#64748B]">{analytics.disclaimer}</p>
          {analytics.concentrationNote && <p className="text-sm text-[#92400E]">{analytics.concentrationNote}</p>}
        </div>
      )}

      {!loading && isMerchant && tab === "scan" && (
        <div className="co-card space-y-3">
          <Field label="Redemption token">
            <input className="co-input" value={scan.token} onChange={(e) => setScan({ ...scan, token: e.target.value })} placeholder="Paste student token" />
          </Field>
          <button type="button" className="co-btn co-btn-secondary" disabled={busy} onClick={async () => {
            const preview = await run(() => api.validateRedemption({ token: scan.token }), "Validated. Confirm to redeem.");
            setScan((cur) => ({ ...cur, preview }));
          }}>Validate</button>
          {scan.preview?.valid && (
            <div>
              <p className="text-sm">{scan.preview.title} · {scan.preview.merchant?.name} · expires {formatWhen(scan.preview.expiresAt)}</p>
              <p className="text-sm text-[#64748B]">Student {scan.preview.studentName || "on file"} — no academic or counselling data is shown.</p>
              <button type="button" className="co-btn mt-2" disabled={busy} onClick={() => run(() => api.confirmRedemption({ token: scan.token }), "Voucher redeemed.")}>Confirm redemption</button>
            </div>
          )}
        </div>
      )}

      {!loading && isMerchant && tab === "today" && (
        <div className="co-card">
          {(vouchers.filter((v) => v.status === "REDEEMED") || []).map((v) => (
            <p key={v.id} className="text-sm">{v.title} · {formatWhen(v.redeemedAt)}</p>
          ))}
          {!vouchers.some((v) => v.status === "REDEEMED") && <EmptyState title="No redemptions yet." />}
        </div>
      )}
    </div>
  );
}
