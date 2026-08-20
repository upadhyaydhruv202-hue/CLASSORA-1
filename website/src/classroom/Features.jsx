import { useEffect, useMemo, useState } from "react";
import { api } from "./api";
import {
  cellText,
  driverList,
  flattenRecords,
  interventionRows,
  labelize,
  scenarioRows,
  trajectoryRows,
  whyLines,
  widgetLevelLabel,
} from "./display";
import {
  ActionItems,
  Chips,
  DriverBars,
  EmptyState,
  Notice,
  NotifyCard,
  NumberedWhy,
  RecoveryCompare,
  ScoreLineChart,
  ShareBarChart,
  TimelineList,
} from "./ui";

function Card({ title, children }) {
  return (
    <div className="co-card">
      {title && <h3 className="mb-3 font-semibold">{title}</h3>}
      {children}
    </div>
  );
}

function Table({ rows, columns, rename, empty = "No records yet." }) {
  const prepared = flattenRecords(rows, columns);
  if (!prepared.length) return <EmptyState title={empty} />;
  const keys = Object.keys(prepared[0]);
  return (
    <div className="co-table-wrap">
      <table className="co-table">
        <thead>
          <tr>{keys.map((k) => <th key={k}>{rename?.[k] || labelize(k)}</th>)}</tr>
        </thead>
        <tbody>
          {prepared.slice(0, 40).map((row, i) => (
            <tr key={i}>
              {keys.map((k) => <td key={k}>{row[k]}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Metrics({ items }) {
  return <Chips items={items} />;
}

function profileRows(profiles = []) {
  return profiles.map((p) => ({
    Student: p.name,
    Standing: p.prediction?.category,
    Score: p.prediction?.score,
    Attendance: p.attendance?.rate != null ? `${p.attendance.rate}%` : "—",
  }));
}

export default function SuccessWorkspace({ session, setError, defaultModule, cached = null, onCached }) {
  const [data, setData] = useState(cached);
  const [module, setModule] = useState(defaultModule || "");
  const [pick, setPick] = useState("");
  const [busy, setBusy] = useState(false);
  const [stalled, setStalled] = useState("");

  const load = async (force = false) => {
    try {
      setStalled("");
      const ws = await api.workspace(force);
      setData(ws);
      onCached?.(ws);
      setModule((current) => defaultModule || current || ws.modules?.[0] || "");
      if (!pick && ws.profiles?.[0]) setPick(String(ws.profiles[0].student_id));
    } catch (err) {
      setError(err.message);
      setStalled(err.message || "Could not load Success Hub modules.");
    }
  };

  useEffect(() => {
    if (cached) setData(cached);
  }, [cached]);

  useEffect(() => {
    if (defaultModule) setModule(defaultModule);
  }, [defaultModule]);

  useEffect(() => {
    if (cached) return undefined;
    load();
    return undefined;
  }, []);

  useEffect(() => {
    const onGoto = (event) => {
      const map = { explain: "AI Explanation", recovery: "Recovery AI", twin: "My Digital Twin" };
      if (map[event.detail]) setModule(map[event.detail]);
    };
    window.addEventListener("classora-risk-goto", onGoto);
    return () => window.removeEventListener("classora-risk-goto", onGoto);
  }, []);

  const profile = useMemo(
    () => (data?.profiles || []).find((p) => String(p.student_id) === String(pick)) || data?.mine,
    [data, pick],
  );
  const twin = data?.twins?.[String(profile?.student_id)] || data?.twins?.[String(data?.mine?.student_id)];

  const run = async (fn) => {
    setBusy(true);
    setError("");
    try {
      await fn();
      await load(true);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  if (!data) {
    return (
      <p className="text-sm text-[#64748B]">
        {stalled ? `Could not load modules: ${stalled}` : "Loading CLASSORA modules…"}
      </p>
    );
  }

  const showPicker = session.user_role !== "student" && (data.profiles || []).length > 0;

  return (
    <div className="space-y-5">
      <p className="text-sm text-[#64748B]">{data.disclaimer}</p>
      <div className="co-modules">
        {(data.modules || []).map((name) => (
          <button key={name} type="button" onClick={() => setModule(name)} className={`co-btn ${module === name ? "" : "co-btn-secondary"}`}>
            {name}
          </button>
        ))}
      </div>
      {showPicker && (
        <select className="co-input max-w-md" value={pick} onChange={(e) => setPick(e.target.value)}>
          {(data.profiles || []).map((p) => <option key={p.student_id} value={p.student_id}>{p.name} ({p.student_id})</option>)}
        </select>
      )}
      <ModuleView
        module={module}
        data={data}
        profile={profile}
        twin={twin}
        session={session}
        busy={busy}
        run={run}
      />
    </div>
  );
}

function ModuleView({ module, data, profile, twin, session, busy, run }) {
  const pred = profile?.prediction || {};
  const att = profile?.attendance || {};
  const recov = twin?.recovery || {};
  const traj = twin?.trajectory || {};
  const drivers = driverList(twin, pred);
  const why = twin?.risk?.why || {};

  if (module === "Counsellor" || module === "Institution success") {
    const queue = (data.profiles || []).filter((p) => ["Critical", "High"].includes(p.prediction?.category));
    const inst = data.institution || {};
    return (
      <div className="space-y-4">
        <Metrics items={[
          { label: "Caseload", value: data.profiles?.length },
          { label: "Critical/High", value: queue.length },
          { label: "Cases", value: data.cases?.length },
          { label: "Overall attendance", value: inst.overall_rate != null ? `${inst.overall_rate}%` : "—" },
        ]} />
        <Card title="Priority queue"><Table rows={profileRows(queue)} empty="No Critical or High cases in this set." /></Card>
        {module === "Institution success" && <Card title="Watchlist"><Table rows={inst.watchlist} empty="No watchlist students." /></Card>}
        <Card title="Cases / SLA"><Table rows={data.cases} empty="No open cases." /></Card>
        {session.user_role !== "student" && profile && (
          <Card title="Assign anonymous mentorship">
            <button disabled={busy} className="co-btn" onClick={() => run(() => api.mentorshipAssign({ student_id: Number(profile.student_id) }))}>Assign mentor</button>
          </Card>
        )}
        {session.user_role === "administrator" && (
          <Card title="Invite staff">
            <AdminInvite busy={busy} run={run} />
          </Card>
        )}
      </div>
    );
  }

  if (module === "Student 360" || module === "Student snapshot" || module === "My Risk") {
    const temporal = pred.temporal || twin?.overview?.temporal || {};
    return (
      <div className="space-y-4">
        <p className="co-section-kicker">Predict → Explain → Recover</p>
        <Metrics items={[
          { label: "Support-risk estimate", value: pred.score != null ? `${pred.score}%` : "—" },
          { label: "Standing", value: pred.category },
          { label: "Attendance", value: att.rate != null ? `${att.rate}%` : "—" },
          { label: "Confidence", value: pred.confidence },
        ]} />
        <p className="text-sm text-[#64748B]">{pred.disclaimer || data.disclaimer}</p>
        {temporal.label && <Notice title={labelize(temporal.pattern || "Pattern")} body={temporal.label} tone="info" />}
        {data.risk?.weekChange != null && (
          <p className="text-sm text-[#64748B]">
            {data.risk.weekChange > 0 ? "↑" : data.risk.weekChange < 0 ? "↓" : "→"} {Math.abs(data.risk.weekChange)} points vs last stored week.
          </p>
        )}
        {pred.missing?.length ? <Notice title="Not enough data in" body={pred.missing.join(", ")} tone="warn" /> : null}
        <Card title="Identity & courses">
          <p>{profile?.name} · ID {profile?.student_id}</p>
          <p className="text-sm text-[#64748B]">{(profile?.courses || []).join(", ") || "No enrolled courses in this view."}</p>
        </Card>
        <Card title="Attendance / academic / engagement">
          <Table rows={[{
            Attendance: att.rate != null ? `${att.rate}%` : "—",
            Present: `${att.present ?? 0} / ${att.marked ?? 0}`,
            Consecutive: att.consecutive_absences,
            GPA: profile?.academic?.gpa,
            Average: profile?.academic?.avg_score,
            LMS: profile?.engagement?.count,
            Trend: profile?.engagement?.trend,
          }]} />
        </Card>
      </div>
    );
  }

  if (module === "Early warning") return <Card title="Early warning"><Table rows={data.alerts} empty="No early-warning alerts." /></Card>;

  if (module === "Recommender") {
    return (
      <div className="space-y-4">
        <Card title="Recommendations">
          <Table
            rows={(profile?.recommendations || []).map((r) => ({ Name: r.name, Reason: r.reason, Owner: r.owner }))}
            empty="No recommendations yet."
          />
        </Card>
        <Card title="Library"><Table rows={data.library} empty="Intervention library is empty." /></Card>
        <button disabled={busy || !profile} className="co-btn" onClick={() => run(() => api.submitRecommend({ student_id: Number(profile.student_id) }))}>Submit for human review</button>
      </div>
    );
  }

  if (module === "Human review" || module === "Cases") {
    return (
      <div className="space-y-4">
        <Card title="Open cases"><Table rows={data.cases} empty="No open cases." /></Card>
        <Card title="Create case">
          <button disabled={busy || !profile} className="co-btn" onClick={() => run(() => api.createCase({ student_id: Number(profile.student_id), intervention_name: profile?.recommendations?.[0]?.name || "Attendance check-in" }))}>Open case for selected student</button>
        </Card>
      </div>
    );
  }

  if (module === "Outcomes") {
    return <Card title="Record outcome"><button disabled={busy || !profile} className="co-btn" onClick={() => run(() => api.recordOutcome({ student_id: Number(profile.student_id), result: "improved" }))}>Record improved outcome</button></Card>;
  }

  if (module === "My Digital Twin" || module === "Digital Twin") {
    return <TwinPanel twin={twin} pred={pred} role={session.user_role} />;
  }

  if (module === "AI Explanation" || module === "Explainable AI") {
    return (
      <div className="space-y-4">
        <Card title={why.title || "WHAT IS AFFECTING YOUR SUPPORT PICTURE?"}>
          <NumberedWhy lines={whyLines(twin, pred)} />
        </Card>
        <Card title="Risk drivers">
          <DriverBars drivers={drivers} />
          <ShareBarChart items={drivers} />
        </Card>
        <ActionItems items={why.recommended || []} title="What can you do?" />
        {why.method && <p className="text-sm text-[#64748B]">{why.method}</p>}
        <p className="text-sm text-[#64748B]">{why.disclaimer || data.disclaimer}</p>
      </div>
    );
  }

  if (module === "Recovery" || module === "Recovery AI" || module === "What-if") {
    return <RecoveryPanel recov={recov} pred={pred} twin={twin} role={session.user_role} />;
  }

  if (module === "Future trajectory" || module === "Predictive Twin") {
    return <TrajectoryPanel traj={traj} />;
  }

  if (module === "Academic") return <Card title="Academic intelligence"><Table rows={data.academic} empty="No academic records in this view." /></Card>;
  if (module === "Attendance intel") {
    return (
      <Card title="Attendance intelligence">
        <Table
          rows={(data.profiles || []).map((p) => ({
            Student: p.name,
            Rate: p.attendance?.rate != null ? `${p.attendance.rate}%` : "—",
            Consecutive: p.attendance?.consecutive_absences,
            "Sudden decline": p.attendance?.sudden_decline,
            Chronic: p.attendance?.chronic,
          }))}
          empty="No attendance intelligence yet."
        />
      </Card>
    );
  }
  if (module === "LMS") return <Card title="LMS & behavioral intelligence"><Table rows={data.lms} empty="No LMS records yet." /></Card>;

  if (module === "Notifications") {
    const notes = data.notifications || [];
    if (!notes.length) return <EmptyState title="No notifications yet." body="Support updates will appear here." />;
    return (
      <div className="space-y-3">
        {notes.slice(0, 20).map((note, i) => (
          <NotifyCard
            key={note.id || i}
            title={note.title || "Update"}
            body={note.body || cellText(note)}
            when={note.created_at || note.when || ""}
          />
        ))}
      </div>
    );
  }

  if (module === "Appointments" || module === "Interventions") {
    const recs = profile?.recommendations || [];
    return (
      <div className="space-y-4">
        {module === "Interventions" && (
          <Card title="Recommended actions">
            {recs.length ? (
              <ul className="list-disc pl-5 text-sm">{recs.map((r, i) => <li key={i}>{r.name || cellText(r)}</li>)}</ul>
            ) : (
              <EmptyState title="No actions assigned yet." body="Keep attending class. Recommended actions will appear here." />
            )}
          </Card>
        )}
        <Card title="Appointments"><Table rows={data.appointments} empty="No appointments requested." /></Card>
        <Card title="Tasks"><Table rows={data.tasks} columns={["task", "done", "student_id", "created_at"]} empty="No recovery tasks yet." /></Card>
        {session.user_role === "student" && (
          <Card title="Request appointment">
            <button disabled={busy} className="co-btn" onClick={() => run(() => api.bookAppointment({ kind: "counsellor" }))}>Request counsellor meeting</button>
          </Card>
        )}
      </div>
    );
  }

  if (module === "Communication" || module === "Ask for support" || module === "Assistant") {
    return <SupportForms data={data} session={session} busy={busy} run={run} />;
  }

  if (module === "Reports" || module === "Search" || module === "Monitoring" || module === "Health" || module === "Settings" || module === "Import" || module === "Ecosystem analytics" || module === "Faculty portal") {
    return (
      <div className="space-y-4">
        <Metrics items={[
          { label: "Students", value: data.profiles?.length },
          { label: "High/Critical", value: data.alerts?.length },
          { label: "Cases", value: data.cases?.length },
          { label: "Mode", value: "Live" },
        ]} />
        <Card title={module}><Table rows={profileRows(data.profiles)} empty="No student profiles in this view." /></Card>
        {module === "Settings" && session.user_role === "administrator" && (
          <Card title="Invite staff"><AdminInvite busy={busy} run={run} /></Card>
        )}
      </div>
    );
  }

  if (module === "Anonymous Mentorship" || module === "Mentorship admin") {
    return <MentorshipDesk data={data} session={session} busy={busy} run={run} profile={profile} />;
  }

  if (module === "Report Student" || module === "Complaint Management" || module === "Account") {
    return (
      <div className="space-y-4">
        <ModerationDesk data={data} session={session} busy={busy} run={run} />
        {module === "Account" && <SupportForms data={data} session={session} busy={busy} run={run} />}
      </div>
    );
  }

  return <Card title={module}><Table rows={profileRows(data.profiles)} empty="Nothing to show for this module yet." /></Card>;
}

function TwinPanel({ twin, pred, role }) {
  if (!twin) {
    return <EmptyState title="Digital Twin is not ready yet." body="The twin appears after attendance or academic records exist." />;
  }
  const ov = twin.overview || {};
  const att = twin.attendance || {};
  const aca = twin.academic || {};
  const eng = twin.engagement || {};
  const rec = twin.intervention || {};
  const recov = twin.recovery || {};
  const traj = twin.trajectory || {};
  const drivers = driverList(twin, pred);
  const why = twin.risk?.why || {};
  const temporal = ov.temporal || {};
  const minimum = recov.minimum_practical;
  return (
    <div className="space-y-4">
      <p className="co-section-kicker">AI Student Digital Twin</p>
      <h3 className="text-xl font-extrabold tracking-[-0.03em]">{twin.displayName || `Student ${twin.studentId}`}</h3>
      <Metrics items={[
        { label: "Current risk", value: ov.riskScore != null ? `${ov.riskScore}%` : "—" },
        { label: "Status", value: ov.category },
        { label: "Widget level", value: widgetLevelLabel(ov.widgetLevel) },
        { label: "Pattern", value: labelize(temporal.pattern || "—") },
      ]} />
      {temporal.label && <p className="text-sm text-[#64748B]">{temporal.label}</p>}
      <p className="text-sm text-[#64748B]">{twin.disclaimer}</p>
      <Metrics items={[
        { label: "Attendance", value: att.rate != null ? `${att.rate}%` : "—" },
        { label: "Academic avg", value: aca.avg_score != null ? `${aca.avg_score}%` : "—" },
        { label: "Engagement", value: eng.trend || (eng.count ? "ok" : "—") },
        { label: "Recovery", value: rec.recoveryProgress != null ? `${rec.recoveryProgress}%` : "—" },
      ]} />
      <p className="text-sm">Mentorship: <strong>{labelize(twin.mentorship?.status || "None")}</strong></p>
      <Card title="Risk drivers">
        <DriverBars drivers={drivers} />
        <ShareBarChart items={drivers} />
        {twin.method && <p className="mt-2 text-sm text-[#64748B]">{twin.method}</p>}
        {(twin.risk?.missing || []).length ? <Notice title="Missing layers (not fabricated)" body={twin.risk.missing.join(", ")} tone="warn" /> : null}
      </Card>
      <Card title={why.title || "Why / actions"}>
        <NumberedWhy lines={whyLines(twin, pred)} />
        <ActionItems items={why.recommended || []} title="What can you do?" />
      </Card>
      <RecoveryPanel recov={recov} pred={pred} twin={twin} role={role} embedded />
      <TrajectoryPanel traj={traj} embedded />
      <Card title="Timeline"><TimelineList events={twin.timeline || []} /></Card>
    </div>
  );
}

function RecoveryPanel({ recov = {}, pred = {}, twin, role, embedded }) {
  const minimum = recov.minimum_practical;
  const current = pred.score ?? twin?.overview?.riskScore;
  const inner = (
    <>
      <Notice title={recov.label || "SIMULATED / ESTIMATED"} body="These figures are practical what-if estimates from recorded layers, not a guaranteed outcome." tone="warn" />
      <RecoveryCompare current={current} estimated={minimum?.estimated_score} />
      {minimum && (
        <Notice
          title="A practical next step package"
          body={`${minimum.title} (estimated ${minimum.estimated_score}%, Δ ${minimum.delta} pts).`}
          tone="ok"
        />
      )}
      <Table rows={scenarioRows(recov.scenarios)} empty="Need recorded attendance to simulate recovery." />
      <ActionItems items={recov.actions || []} title="Recommended actions" />
      {role !== "student" && twin?.scenarios?.length ? (
        <Card title="Intervention comparison">
          <Table rows={interventionRows(twin.scenarios)} empty="No scenario table." />
        </Card>
      ) : null}
    </>
  );
  if (embedded) return <Card title="Recovery AI">{inner}</Card>;
  return <div className="space-y-4">{inner}</div>;
}

function TrajectoryPanel({ traj = {}, embedded }) {
  const pts = traj.points || [];
  const inner = (
    <>
      {traj.label && <Notice title={traj.label} body={traj.note || ""} tone={traj.insufficient_history ? "info" : "warn"} />}
      {!traj.insufficient_history && <ScoreLineChart points={pts} />}
      <Table rows={trajectoryRows(pts)} empty="Trajectory needs more attendance history." />
    </>
  );
  if (embedded) return <Card title="Future trajectory">{inner}</Card>;
  return <div className="space-y-4">{inner}</div>;
}

function AdminInvite({ busy, run }) {
  const [form, setForm] = useState({ invited_name: "", invited_username: "", role: "counsellor" });
  return (
    <div className="grid gap-2 sm:grid-cols-4">
      <input className="rounded-2xl border px-4 py-2" placeholder="Name" value={form.invited_name} onChange={(e) => setForm({ ...form, invited_name: e.target.value })} />
      <input className="rounded-2xl border px-4 py-2" placeholder="Username" value={form.invited_username} onChange={(e) => setForm({ ...form, invited_username: e.target.value })} />
      <select className="rounded-2xl border px-4 py-2" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
        <option value="counsellor">Counsellor</option>
        <option value="administrator">Administrator</option>
        <option value="faculty">Faculty</option>
        <option value="mentor">Mentor</option>
      </select>
      <button disabled={busy} className="co-btn" onClick={() => run(async () => {
        const res = await api.staffInvite(form);
        window.alert(`${res.detail}\nCode: ${res.token}`);
      })}>Invite</button>
    </div>
  );
}

function SupportForms({ session, busy, run }) {
  const [msg, setMsg] = useState("");
  const [q, setQ] = useState("");
  const [answer, setAnswer] = useState("");
  return (
    <div className="space-y-4">
      {session.user_role === "student" && (
        <Card title="Ask for support">
          <textarea className="w-full rounded-2xl border border-[#E2E8F0] p-3" rows={3} value={msg} onChange={(e) => setMsg(e.target.value)} placeholder="I would like help with attendance / studies / a meeting." />
          <button disabled={busy} className="mt-2 rounded-full bg-[#2563EB] px-4 py-2 text-sm text-white" onClick={() => run(() => api.sendHelp({ message: msg || "Help request" }))}>Send help request</button>
        </Card>
      )}
      <Card title="Ask the assistant">
        <input className="w-full rounded-2xl border border-[#E2E8F0] px-4 py-2" value={q} onChange={(e) => setQ(e.target.value)} placeholder="What is my attendance?" />
        <button disabled={busy} className="mt-2 rounded-full border border-[#E2E8F0] px-4 py-2 text-sm" onClick={async () => { const res = await api.askAssistant({ question: q }); setAnswer(res.answer); }}>Ask</button>
        {answer && <p className="mt-2 text-sm">{answer}</p>}
      </Card>
    </div>
  );
}

function MentorshipDesk({ data, session, busy, run, profile }) {
  const [body, setBody] = useState("");
  const [title, setTitle] = useState("Check-in");
  const rows = Array.isArray(data.mentorship) ? data.mentorship : data.mentorship?.open || [];
  const first = rows[0];
  const id = first?.mentorshipId || first?.mentorship_id;
  const admin = data.mentorship_admin;
  const metrics = admin?.metrics || {};
  return (
    <div className="space-y-4">
      <Card title="Mentorships">
        <Table
          rows={rows}
          columns={["mentorship_id", "student_alias", "mentor_alias", "status", "started_at", "feedback_due_at"]}
          empty="No mentorships in this view."
        />
      </Card>
      {admin && (
        <Card title="Admin overview">
          {!admin.installed ? (
            <EmptyState title="Mentorship store is not installed." body="Connect the mentorship tables to see aggregates. Identities stay hidden here." />
          ) : (
            <>
              <Metrics items={[
                { label: "Total", value: metrics.total },
                { label: "Acceptance", value: metrics.acceptanceRate != null ? `${metrics.acceptanceRate}%` : "—" },
                { label: "Reassignment", value: metrics.reassignmentRate != null ? `${metrics.reassignmentRate}%` : "—" },
                { label: "Avg feedback", value: metrics.averageFeedback },
              ]} />
              <Table
                rows={admin.rows}
                columns={["mentorship_id", "student_alias", "mentor_alias", "status", "started_at"]}
                empty="No mentorship rows."
              />
            </>
          )}
        </Card>
      )}
      {session.user_role !== "student" && profile && (
        <button disabled={busy} className="co-btn" onClick={() => run(() => api.mentorshipAssign({ student_id: Number(profile.student_id) }))}>Assign anonymous mentorship</button>
      )}
      {id && (
        <Card title="Workspace">
          <input className="mb-2 w-full rounded-2xl border px-4 py-2" value={body} onChange={(e) => setBody(e.target.value)} placeholder="Message (no names)" />
          <button disabled={busy} className="mr-2 rounded-full bg-[#0F172A] px-4 py-2 text-sm text-white" onClick={() => run(() => api.mentorshipMessage(id, { body }))}>Send message</button>
          <input className="mb-2 mt-3 w-full rounded-2xl border px-4 py-2" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Session title" />
          <button disabled={busy} className="mr-2 rounded-full border px-4 py-2 text-sm" onClick={() => run(() => api.mentorshipSession(id, { title, notes: body }))}>Log session</button>
          {session.user_role === "student" && (
            <>
              <button disabled={busy} className="mr-2 rounded-full border px-4 py-2 text-sm" onClick={() => run(() => api.mentorshipFeedback(id, { answers: { helpful: "yes" } }))}>Submit feedback</button>
              <button disabled={busy} className="rounded-full border px-4 py-2 text-sm" onClick={() => run(() => api.mentorshipReassign(id))}>Request reassignment</button>
            </>
          )}
          {session.user_role === "administrator" && (
            <button disabled={busy} className="rounded-full bg-red-600 px-4 py-2 text-sm text-white" onClick={() => run(() => api.mentorshipSuspend(id))}>Suspend</button>
          )}
        </Card>
      )}
    </div>
  );
}

function ModerationDesk({ data, session, busy, run }) {
  const meta = data.moderation_meta || {};
  const [form, setForm] = useState({ student_reference: "", category: meta.categories?.[0] || "", severity: "medium", description: "", requested_action: "review" });
  const [decision, setDecision] = useState({ complaint_id: "", action: "warning", notes: "Reviewed with written reason." });
  const firstId = data.complaints?.[0]?.complaint_id || data.complaints?.[0]?.id || "";
  return (
    <div className="space-y-4">
      <Card title="Complaints"><Table rows={data.complaints} empty="No complaints." /></Card>
      <Card title="Appeals"><Table rows={data.appeals} empty="No appeals." /></Card>
      {session.user_role !== "student" && (
        <Card title="Report student">
          <div className="grid gap-2">
            <input className="rounded-2xl border px-4 py-2" placeholder="Student ID or alias STU-…" value={form.student_reference} onChange={(e) => setForm({ ...form, student_reference: e.target.value })} />
            <select className="rounded-2xl border px-4 py-2" value={form.requested_action} onChange={(e) => setForm({ ...form, requested_action: e.target.value })}>
              {(meta.actions || ["review", "warning"]).map((c) => <option key={c}>{c}</option>)}
            </select>
            <textarea className="rounded-2xl border p-3" rows={3} placeholder="Describe the incident (20+ characters)" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
            <button disabled={busy} className="rounded-full bg-red-600 px-4 py-2 text-sm text-white" onClick={() => run(() => api.createComplaint(form))}>Submit complaint</button>
          </div>
        </Card>
      )}
      {session.user_role === "administrator" && (
        <Card title="Execute moderation">
          <input className="mb-2 w-full rounded-2xl border px-4 py-2" placeholder="Complaint ID" value={decision.complaint_id || firstId} onChange={(e) => setDecision({ ...decision, complaint_id: e.target.value })} />
          <select className="mb-2 w-full rounded-2xl border px-4 py-2" value={decision.action} onChange={(e) => setDecision({ ...decision, action: e.target.value })}>
            {(meta.execute_actions || meta.actions || ["warning", "restrict", "ban"]).map((a) => <option key={a}>{a}</option>)}
          </select>
          <textarea className="mb-2 w-full rounded-2xl border p-3" rows={2} value={decision.notes} onChange={(e) => setDecision({ ...decision, notes: e.target.value })} />
          <button disabled={busy} className="mr-2 rounded-full border px-4 py-2 text-sm" onClick={() => run(() => api.openComplaint(decision.complaint_id || firstId))}>Open investigation</button>
          <button disabled={busy} className="co-btn" onClick={() => run(() => api.decideComplaint(decision.complaint_id || firstId, { action: decision.action, notes: decision.notes }))}>Record decision</button>
        </Card>
      )}
      {session.user_role === "student" && (
        <Card title="Appeal">
          <p className="mb-2 text-sm text-[#64748B]">{data.account?.status ? `Account status: ${data.account.status}` : "No active restriction on this account."}</p>
          <button disabled={busy} className="co-btn" onClick={() => run(() => api.submitAppeal({ reason: "appeal", explanation: "I would like this decision reviewed by an administrator." }))}>Submit appeal</button>
        </Card>
      )}
    </div>
  );
}

export function InstitutionPanel({ setError }) {
  const [data, setData] = useState(null);
  useEffect(() => {
    api.institution().then(setData).catch((err) => setError(err.message));
  }, []);
  const m = data?.metrics || {};
  return (
    <div className="space-y-4">
      <Metrics items={[
        { label: "Students", value: m.student_count },
        { label: "Present", value: m.present },
        { label: "Absent", value: m.absent },
        { label: "Overall", value: m.overall_rate != null ? `${m.overall_rate}%` : "—" },
      ]} />
      <Card title="Bands"><Table rows={Object.entries(m.bands || {}).map(([Band, Students]) => ({ Band, Students }))} empty="No band data." /></Card>
      <Card title="Watchlist"><Table rows={m.watchlist} empty="No watchlist students." /></Card>
      <Card title="Latest-session absences"><Table rows={m.alerts} empty="No latest-session absences." /></Card>
      <Card title="Daily trend"><Table rows={m.trend} empty="No daily trend yet." /></Card>
      <Card title="Courses"><Table rows={m.courses} empty="No course rows." /></Card>
      <Card title="Sections"><Table rows={m.sections} empty="No section rows." /></Card>
    </div>
  );
}

export function AccountPanel({ session, setError }) {
  const [pw, setPw] = useState({ current_password: "", new_password: "", confirm_password: "" });
  const [invite, setInvite] = useState({ invited_name: "", invited_username: "" });
  const [invites, setInvites] = useState([]);
  const [history, setHistory] = useState([]);
  const [msg, setMsg] = useState("");
  useEffect(() => {
    if (session.user_role !== "teacher") return;
    api.teacherInvites().then(setInvites).catch(() => {});
    api.loginHistory().then(setHistory).catch(() => {});
  }, [session]);
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Card title="Change password">
        {["current_password", "new_password", "confirm_password"].map((k) => (
          <input key={k} type="password" placeholder={k.replaceAll("_", " ")} className="mb-2 w-full rounded-2xl border px-4 py-2" value={pw[k]} onChange={(e) => setPw({ ...pw, [k]: e.target.value })} />
        ))}
        <button className="co-btn" onClick={async () => {
          try { const res = await api.changePassword(pw); setMsg(res.detail); } catch (err) { setError(err.message); }
        }}>Update password</button>
      </Card>
      <Card title="Invite teacher">
        <input className="mb-2 w-full rounded-2xl border px-4 py-2" placeholder="Name" value={invite.invited_name} onChange={(e) => setInvite({ ...invite, invited_name: e.target.value })} />
        <input className="mb-2 w-full rounded-2xl border px-4 py-2" placeholder="Username" value={invite.invited_username} onChange={(e) => setInvite({ ...invite, invited_username: e.target.value })} />
        <button className="co-btn" onClick={async () => {
          try { const res = await api.inviteTeacher(invite); setMsg(`${res.detail} Code: ${res.token}`); } catch (err) { setError(err.message); }
        }}>Create invitation</button>
        <Table rows={invites} empty="No invitations yet." />
      </Card>
      <Card title="Login history"><Table rows={history} empty="No login history." /></Card>
      {msg && <p className="text-sm text-green-700">{msg}</p>}
    </div>
  );
}
