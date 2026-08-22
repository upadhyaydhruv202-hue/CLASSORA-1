import { useEffect, useMemo, useRef, useState } from "react";
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

function downloadCsv(filename, rows = []) {
  if (!rows.length) return;
  const keys = Object.keys(rows[0]);
  const escape = (value) => `"${String(value ?? "").replaceAll('"', '""')}"`;
  const lines = [keys.join(","), ...rows.map((row) => keys.map((key) => escape(row[key])).join(","))];
  const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
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
      setModule((current) => current || defaultModule || ws.modules?.[0] || "");
      setPick((current) => current || (ws.profiles?.[0] ? String(ws.profiles[0].student_id) : current));
    } catch (err) {
      setError(err.message);
      setStalled(err.message || "Could not load Success Hub modules.");
    }
  };

  useEffect(() => {
    if (cached) setData(cached);
  }, [cached]);

  useEffect(() => {
    if (!pick && data?.profiles?.[0]) setPick(String(data.profiles[0].student_id));
  }, [data, pick]);

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
    } catch (err) {
      setError(err.message);
    } finally {
      try {
        await load(true);
      } catch {
        /* keep prior workspace if reload fails */
      }
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
        onOpenMentorship={() => setModule("Anonymous Mentorship")}
      />
    </div>
  );
}

function ModuleView({ module, data, profile, twin, session, busy, run, onOpenMentorship }) {
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
    const submitted = (data.recommendations || []).filter((row) => row.recommendation || row.status);
    return (
      <div className="space-y-4">
        <Card title="Recommendations">
          <Table
            rows={(profile?.recommendations || []).map((r) => ({ Name: r.name, Reason: r.reason, Owner: r.owner }))}
            empty="No recommendations yet."
          />
        </Card>
        <Card title="Queued for review"><Table rows={submitted} empty="No recommendations queued for review." /></Card>
        <Card title="Library"><Table rows={data.library} empty="Intervention library is empty." /></Card>
        <button disabled={busy || !profile} className="co-btn" onClick={() => run(() => api.submitRecommend({ student_id: Number(profile.student_id) }))}>Submit for human review</button>
      </div>
    );
  }

  if (module === "Human review" || module === "Cases") {
    const queued = (data.recommendations || []).filter((row) => String(row.status || "").toLowerCase() === "pending");
    return (
      <div className="space-y-4">
        <Card title="Pending recommendations"><Table rows={queued} empty="No recommendations waiting for review." /></Card>
        <Card title="Open cases"><Table rows={data.cases} empty="No open cases." /></Card>
        <Card title="Create case">
          <button disabled={busy || !profile} className="co-btn" onClick={() => run(() => api.createCase({ student_id: Number(profile.student_id), intervention_name: profile?.recommendations?.[0]?.name || "Attendance check-in" }))}>Open case for selected student</button>
        </Card>
      </div>
    );
  }

  if (module === "Outcomes") {
    return (
      <div className="space-y-4">
        <Card title="Recorded outcomes"><Table rows={data.outcomes} empty="No outcomes recorded yet." /></Card>
        <Card title="Record outcome">
          <button disabled={busy || !profile} className="co-btn" onClick={() => run(() => api.recordOutcome({ student_id: Number(profile.student_id), result: "improved" }))}>Record improved outcome</button>
        </Card>
      </div>
    );
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
    const appts = data.appointments || [];
    const requested = appts.filter((row) => String(row.status || "").toLowerCase() === "requested");
    const canConnect = ["counsellor", "administrator", "mentor", "faculty"].includes(session.user_role);
    const waiting = session.user_role === "student" && appts.some((row) => String(row.status || "").toLowerCase() === "requested");
    const linked = session.user_role === "student" && appts.some((row) => String(row.status || "").toLowerCase() === "connected");
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
        <Card title="Appointments"><Table rows={appts} empty="No appointments requested." /></Card>
        {canConnect && (
          <Card title="Connect privately">
            <p className="mb-3 text-sm text-[#64748B]">
              A request is only a ticket. Click connect to open an alias-only chat in Anonymous Mentorship. The student will not see your name.
            </p>
            {requested.length ? requested.map((row) => (
              <button
                key={row.id}
                disabled={busy}
                className="co-btn mr-2 mb-2"
                onClick={async () => {
                  await run(async () => {
                    const res = await api.connectAppointment({ appointment_id: Number(row.id) });
                    window.alert(res.detail || "Private chat opened. Talk in Anonymous Mentorship using aliases only.");
                  });
                  onOpenMentorship?.();
                }}
              >
                Connect privately — student {row.student_id} (#{row.id})
              </button>
            )) : (
              <p className="text-sm text-[#64748B]">No waiting requests. If a chat already exists, open Anonymous Mentorship.</p>
            )}
          </Card>
        )}
        {session.user_role === "student" && waiting && (
          <Notice title="Waiting for the counsellor" body="They will open a private alias chat. You cannot message them from this ticket. Watch Notifications, then open Anonymous Mentorship." tone="info" />
        )}
        {session.user_role === "student" && linked && (
          <Card title="Private chat is open">
            <p className="mb-3 text-sm text-[#64748B]">Talk in Anonymous Mentorship. You will see an alias such as MTR-…, not the counsellor’s name.</p>
            <button type="button" className="co-btn" onClick={() => onOpenMentorship?.()}>Open Anonymous Mentorship</button>
          </Card>
        )}
        <Card title="Tasks">
          <Table rows={data.tasks} columns={["id", "task", "done", "student_id"]} empty="No recovery tasks yet." />
          {(data.tasks || []).length > 0 && (
            <div className="mt-3 flex flex-wrap gap-2">
              {(data.tasks || []).slice(0, 12).map((row) => (
                <button
                  key={row.id}
                  type="button"
                  disabled={busy}
                  className="co-btn co-btn-secondary"
                  onClick={() => run(() => api.completeTask({ task_id: Number(row.id), done: !row.done }))}
                >
                  {row.done ? "Reopen" : "Mark done"} — {row.task}
                </button>
              ))}
            </div>
          )}
        </Card>
        {session.user_role !== "student" && profile && (
          <Card title="Assign recovery task">
            <TaskAssign studentId={profile.student_id} busy={busy} run={run} />
          </Card>
        )}
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
      <HubOps
        module={module}
        data={data}
        profile={profile}
        session={session}
        busy={busy}
        run={run}
        onOpenMentorship={onOpenMentorship}
      />
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

function TaskAssign({ studentId, busy, run }) {
  const [task, setTask] = useState("");
  return (
    <div className="flex flex-wrap gap-2">
      <input
        className="min-w-[16rem] flex-1 rounded-2xl border px-4 py-2"
        value={task}
        onChange={(e) => setTask(e.target.value)}
        placeholder="Attend next two sessions / submit assignment"
      />
      <button
        type="button"
        disabled={busy || !task.trim()}
        className="co-btn"
        onClick={() => run(async () => {
          await api.createTask({ student_id: Number(studentId), task: task.trim() });
          setTask("");
        })}
      >
        Assign task
      </button>
    </div>
  );
}

function bandRows(bands = {}) {
  return Object.entries(bands).map(([Band, Students]) => ({ Band, Students }));
}

function ReportDesk({ module, data }) {
  const [payload, setPayload] = useState(null);
  const [err, setErr] = useState("");
  const [standing, setStanding] = useState("all");
  useEffect(() => {
    api.successReport().then((res) => {
      setPayload(res);
      setErr("");
    }).catch((error) => setErr(error.message));
  }, [data.report, data.profiles?.length]);
  const report = payload?.report || data.report || {};
  const rows = payload?.rows?.length ? payload.rows : (data.profiles || []).map((p) => ({
    student_id: p.student_id,
    name: p.name,
    standing: p.prediction?.category,
    score: p.prediction?.score,
    attendance_rate: p.attendance?.rate,
    consecutive_absences: p.attendance?.consecutive_absences,
  }));
  const standings = ["all", ...Array.from(new Set(rows.map((row) => row.standing).filter(Boolean)))];
  const filtered = standing === "all" ? rows : rows.filter((row) => String(row.standing || "") === standing);
  return (
    <div className="space-y-4">
      {err && <Notice title="Could not refresh report from API" body={`${err} Showing workspace totals until the request succeeds.`} tone="warn" />}
      <Metrics items={[
        { label: "Students", value: report.student_count ?? data.profiles?.length },
        { label: "High/Critical", value: report.high_critical },
        { label: "Avg attendance", value: report.avg_attendance != null ? `${report.avg_attendance}%` : "—" },
        { label: "Open cases", value: report.open_cases ?? data.cases?.length },
      ]} />
      <Metrics items={[
        { label: "Alerts", value: report.alerts ?? data.alerts?.length },
        { label: "Appointments", value: report.appointments ?? data.appointments?.length },
        { label: "Academic rows", value: report.academic_records ?? data.academic?.length },
        { label: "Outcomes", value: report.outcomes ?? data.outcomes?.length },
      ]} />
      <Card title="Risk bands"><Table rows={bandRows(report.bands)} empty="No predicted bands yet — bands come from enrolled student records." /></Card>
      <Card title="Student standing">
        <div className="mb-3 flex flex-wrap gap-2">
          <select className="rounded-2xl border px-4 py-2" value={standing} onChange={(e) => setStanding(e.target.value)}>
            {standings.map((value) => <option key={value} value={value}>{value === "all" ? "All standings" : value}</option>)}
          </select>
          <button
            type="button"
            className="co-btn"
            onClick={() => downloadCsv("classora-report.csv", filtered)}
            disabled={!filtered.length}
          >
            Download CSV
          </button>
        </div>
        <Table rows={filtered} empty="No student rows for this filter." />
      </Card>
      {module === "Ecosystem analytics" && (
        <>
          <Card title="Cases"><Table rows={data.cases} empty="No intervention cases." /></Card>
          <Card title="Outcomes"><Table rows={data.outcomes} empty="No outcomes recorded." /></Card>
          <Card title="Appointments"><Table rows={data.appointments} empty="No appointments." /></Card>
        </>
      )}
    </div>
  );
}

function HubOps({ module, data, profile, session, busy, run, onOpenMentorship }) {
  const settings = data.settings || {};

  if (module === "Reports" || module === "Ecosystem analytics") {
    return <ReportDesk module={module} data={data} />;
  }

  if (module === "Search") {
    return <DirectorySearch data={data} />;
  }

  if (module === "Import") {
    return <ImportDesk data={data} busy={busy} run={run} />;
  }

  if (module === "Health") {
    return <HealthDesk />;
  }

  if (module === "Monitoring") {
    return <MonitoringDesk data={data} busy={busy} run={run} />;
  }

  if (module === "Settings") {
    return (
      <SettingsDesk
        data={data}
        settings={settings}
        session={session}
        busy={busy}
        run={run}
      />
    );
  }

  const facultyCases = (data.cases || []).filter((row) => String(row.student_id) === String(profile?.student_id));
  return (
    <div className="space-y-4">
      <Metrics items={[
        { label: "Roster", value: data.profiles?.length },
        { label: "High/Critical", value: (data.profiles || []).filter((p) => ["High", "Critical"].includes(p.prediction?.category)).length },
        { label: "Open cases", value: (data.cases || []).filter((c) => String(c.status || "open").toLowerCase() === "open").length },
        { label: "Academic rows", value: data.academic?.length },
      ]} />
      <Card title="Assigned / enrolled students">
        <Table
          rows={(data.profiles || []).map((p) => ({
            Student: p.name,
            ID: p.student_id,
            Standing: p.prediction?.category,
            Attendance: p.attendance?.rate != null ? `${p.attendance.rate}%` : "—",
            Consecutive: p.attendance?.consecutive_absences,
            GPA: p.academic?.gpa,
          }))}
          empty="No students in this faculty view yet."
        />
      </Card>
      <Card title="Attendance intelligence">
        <Table
          rows={(data.profiles || []).map((p) => ({
            Student: p.name,
            Rate: p.attendance?.rate != null ? `${p.attendance.rate}%` : "—",
            Consecutive: p.attendance?.consecutive_absences,
            Chronic: p.attendance?.chronic,
          }))}
          empty="No attendance records for this roster."
        />
      </Card>
      <Card title={profile ? `Cases for ${profile.name}` : "Cases"}>
        <Table rows={facultyCases} empty="No cases for the selected student." />
      </Card>
      {profile && ["faculty", "mentor", "counsellor"].includes(session.user_role) && session.staff_data?.staff_id && (
        <Card title="Actions for selected student">
          <button
            type="button"
            disabled={busy}
            className="co-btn mr-2"
            onClick={() => run(async () => {
              await api.mentorshipAssign({ student_id: Number(profile.student_id) });
              onOpenMentorship?.();
            })}
          >
            Assign anonymous mentorship
          </button>
          <p className="mt-2 text-sm text-[#64748B]">Use Report Student to file a conduct report. Identities stay in that existing workflow.</p>
        </Card>
      )}
    </div>
  );
}

function DirectorySearch({ data }) {
  const [q, setQ] = useState("");
  const [rows, setRows] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const submit = async (event) => {
    event?.preventDefault?.();
    setBusy(true);
    setErr("");
    try {
      const res = await api.successSearch(q);
      setRows(res.results || []);
    } catch (error) {
      setErr(error.message);
    } finally {
      setBusy(false);
    }
  };
  const shown = rows || profileRows(data.profiles);
  return (
    <div className="space-y-4">
      <Card title="Search students">
        <form className="flex flex-wrap gap-2" onSubmit={submit}>
          <input
            className="min-w-[16rem] flex-1 rounded-2xl border px-4 py-2"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Name, student ID, or standing"
          />
          <button type="submit" disabled={busy} className="co-btn">{busy ? "Searching…" : "Find students"}</button>
        </form>
        {err && <p className="mt-2 text-sm text-red-600">{err}</p>}
        <p className="mt-2 text-sm text-[#64748B]">Results come from enrolled student records in this workspace, not a separate directory.</p>
      </Card>
      <Card title="Results">
        <Table rows={shown} empty="No matching students." />
      </Card>
    </div>
  );
}

function ImportDesk({ data, busy, run }) {
  const [kind, setKind] = useState("academic");
  const [file, setFile] = useState(null);
  return (
    <div className="space-y-4">
      <Card title="Import CSV">
        <p className="mb-3 text-sm text-[#64748B]">
          Academic columns: student_id, assessment, score, max_score, gpa, semester, backlog.
          LMS columns: student_id, event_type, course_code. Student IDs must already exist.
        </p>
        <div className="flex flex-wrap gap-2">
          <select className="rounded-2xl border px-4 py-2" value={kind} onChange={(e) => setKind(e.target.value)}>
            <option value="academic">Academic records</option>
            <option value="lms">LMS events</option>
          </select>
          <input type="file" accept=".csv,text/csv" onChange={(e) => setFile(e.target.files?.[0] || null)} />
          <button
            type="button"
            disabled={busy || !file}
            className="co-btn"
            onClick={() => run(() => api.successImport(file, kind))}
          >
            Upload CSV
          </button>
        </div>
      </Card>
      <Card title="Import jobs"><Table rows={data.import_jobs} empty="No import jobs yet." /></Card>
      <Card title="Academic records"><Table rows={data.academic} empty="No academic records imported yet." /></Card>
      <Card title="LMS events"><Table rows={data.lms} empty="No LMS events imported yet." /></Card>
    </div>
  );
}

function HealthDesk() {
  const [health, setHealth] = useState(null);
  const [err, setErr] = useState("");
  const refresh = () => {
    setErr("");
    api.health().then(setHealth).catch((error) => {
      setHealth(null);
      setErr(error.message);
    });
  };
  useEffect(() => {
    refresh();
  }, []);
  if (err) {
    return (
      <div className="space-y-3">
        <Notice title="Health check failed" body={err} tone="warn" />
        <button type="button" className="co-btn" onClick={refresh}>Retry</button>
      </div>
    );
  }
  if (!health) return <p className="text-sm text-[#64748B]">Checking API, database, and model status…</p>;
  const models = health.models || {};
  return (
    <div className="space-y-4">
      <Metrics items={[
        { label: "API", value: health.ok ? "ok" : "down" },
        { label: "Database", value: health.mode },
        { label: "Face models", value: health.face_models_ready ? "ready" : "missing" },
        { label: "Voice models", value: health.voice_models_ready ? "ready" : "missing" },
      ]} />
      <Metrics items={[
        { label: "Face weights", value: health.face_weights_loaded ? "loaded" : "idle" },
        { label: "Voice weights", value: health.voice_weights_loaded ? "loaded" : "idle" },
        { label: "Supabase", value: health.supabase ? "connected" : "local" },
      ]} />
      {!health.face_models_ready && <Notice title="FaceID unavailable" body="Face login and face attendance cannot run until face packages are installed." tone="warn" />}
      {!health.voice_models_ready && <Notice title="Voice unavailable" body="Voice attendance cannot run until voice packages are installed." tone="warn" />}
      <Card title="Installed packages">
        <Table rows={Object.entries(models).map(([name, ok]) => ({ Package: name, Status: ok ? "present" : "missing" }))} empty="No model inventory." />
      </Card>
      <button type="button" className="co-btn co-btn-secondary" onClick={refresh}>Refresh status</button>
    </div>
  );
}

function MonitoringDesk({ data, busy, run }) {
  const [health, setHealth] = useState(null);
  useEffect(() => {
    api.health().then(setHealth).catch(() => {});
  }, []);
  return (
    <div className="space-y-4">
      <Metrics items={[
        { label: "Live alerts", value: data.alerts?.length },
        { label: "Stored alerts", value: data.stored_alerts?.length },
        { label: "Database", value: health?.mode || "…" },
        { label: "Face", value: health ? (health.face_models_ready ? "ready" : "missing") : "…" },
      ]} />
      <Card title="Early-warning alerts">
        <Table rows={data.alerts} empty="No high-risk or consecutive-absence alerts." />
        {(data.alerts || []).length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2">
            {(data.alerts || []).slice(0, 8).map((row, i) => (
              <button
                key={`${row.student_id}-${row.title}-${i}`}
                type="button"
                disabled={busy}
                className="co-btn co-btn-secondary"
                onClick={() => run(() => api.resolveAlert({
                  student_id: row.student_id ? Number(row.student_id) : null,
                  title: row.title,
                  severity: row.severity,
                  source: row.source,
                }))}
              >
                Resolve — {row.student} / {row.title}
              </button>
            ))}
          </div>
        )}
      </Card>
      <Card title="Resolved / stored alerts"><Table rows={data.stored_alerts} empty="No stored alert history yet." /></Card>
    </div>
  );
}

function SettingsDesk({ data, settings, session, busy, run }) {
  const [form, setForm] = useState({
    institution_name: settings.institution_name || "",
    support_note: settings.support_note || "",
  });
  const [loadErr, setLoadErr] = useState("");
  const [dirty, setDirty] = useState(false);
  const dirtyRef = useRef(false);
  useEffect(() => {
    if (dirtyRef.current) return undefined;
    api.successSettings().then((res) => {
      if (dirtyRef.current) return;
      const next = res.settings || {};
      setForm({
        institution_name: next.institution_name || "",
        support_note: next.support_note || "",
      });
      setLoadErr("");
    }).catch((error) => {
      if (dirtyRef.current) return;
      setForm({
        institution_name: settings.institution_name || "",
        support_note: settings.support_note || "",
      });
      setLoadErr(error.message);
    });
    return undefined;
  }, [settings.institution_name, settings.support_note, dirty]);
  const admin = session.user_role === "administrator";
  return (
    <div className="space-y-4">
      <Card title="Institution">
        {loadErr && <Notice title="Could not load settings from API" body={loadErr} tone="warn" />}
        <label className="mb-2 block text-sm text-[#64748B]">Institution name</label>
        <input
          className="mb-3 w-full rounded-2xl border px-4 py-2"
          value={form.institution_name}
          disabled={!admin}
          onChange={(e) => { dirtyRef.current = true; setDirty(true); setForm({ ...form, institution_name: e.target.value }); }}
        />
        <label className="mb-2 block text-sm text-[#64748B]">Support note</label>
        <textarea
          className="mb-3 w-full rounded-2xl border p-3"
          rows={3}
          disabled={!admin}
          value={form.support_note}
          onChange={(e) => { dirtyRef.current = true; setDirty(true); setForm({ ...form, support_note: e.target.value }); }}
        />
        {admin ? (
          <button type="button" disabled={busy} className="co-btn" onClick={() => run(async () => {
            await api.saveSettings(form);
            dirtyRef.current = false;
            setDirty(false);
          })}>Save settings</button>
        ) : (
          <p className="text-sm text-[#64748B]">Only an administrator can change these settings.</p>
        )}
      </Card>
      {admin && (
        <>
          <Card title="Invite staff">
            <p className="mb-3 text-sm text-[#64748B]">Share the one-time code. The invited person activates it on the staff login screen. Codes expire after 7 days.</p>
            <AdminInvite busy={busy} run={run} />
          </Card>
          <Card title="Invitations"><Table rows={data.staff_invites} columns={["invited_name", "invited_username", "assigned_role", "expires_at", "used_at"]} empty="No staff invitations yet." /></Card>
        </>
      )}
    </div>
  );
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

function SupportForms({ session, data, busy, run }) {
  const [msg, setMsg] = useState("");
  const [q, setQ] = useState("");
  const [answer, setAnswer] = useState("");
  const inbox = data?.messages || [];
  const staff = session.user_role !== "student";
  return (
    <div className="space-y-4">
      {staff && (
        <Card title="Help requests">
          <Table rows={inbox} empty="No help requests yet." />
          {inbox.filter((row) => String(row.status || "") === "queued").map((row) => (
            <button
              key={row.id}
              disabled={busy}
              className="mr-2 mt-2 rounded-full border px-4 py-2 text-sm"
              onClick={() => run(() => api.ackHelp({ message_id: Number(row.id) }))}
            >
              Mark seen — #{row.id}
            </button>
          ))}
        </Card>
      )}
      {session.user_role === "student" && (
        <>
          <Card title="Ask for support">
            <textarea className="w-full rounded-2xl border border-[#E2E8F0] p-3" rows={3} value={msg} onChange={(e) => setMsg(e.target.value)} placeholder="I would like help with attendance / studies / a meeting." />
            <button disabled={busy} className="mt-2 rounded-full bg-[#2563EB] px-4 py-2 text-sm text-white" onClick={() => run(() => api.sendHelp({ message: msg.trim() || "Help request" }))}>Send help request</button>
          </Card>
          <Card title="Your requests"><Table rows={inbox} empty="You have not sent a help request yet." /></Card>
        </>
      )}
      <Card title="Ask the assistant">
        <input className="w-full rounded-2xl border border-[#E2E8F0] px-4 py-2" value={q} onChange={(e) => setQ(e.target.value)} placeholder="What is my attendance?" />
        <button disabled={busy} className="mt-2 rounded-full border border-[#E2E8F0] px-4 py-2 text-sm" onClick={async () => { const res = await api.askAssistant({ question: q }); setAnswer(res.answer); }}>Ask</button>
        {answer && <p className="mt-2 text-sm">{answer}</p>}
      </Card>
    </div>
  );
}

function normalizeMentorship(row) {
  if (!row || typeof row !== "object") return null;
  return {
    mentorship_id: row.mentorshipId || row.mentorship_id,
    student_alias: row.anonymousStudentId || row.student_alias,
    mentor_alias: row.anonymousMentorId || row.mentor_alias,
    status: row.statusLabel || row.status,
    status_code: row.status,
    started_at: row.startedAt || row.mentorshipStartDate || row.started_at,
    feedback_due_at: row.feedbackDueAt || row.feedback_due_at,
  };
}

function MentorshipDesk({ data, session, busy, run, profile }) {
  const [body, setBody] = useState("");
  const [title, setTitle] = useState("Check-in");
  const [thread, setThread] = useState([]);
  const [chatBusy, setChatBusy] = useState(false);
  const [chatError, setChatError] = useState("");
  const [live, setLive] = useState(false);
  const scroller = useRef(null);
  const raw = Array.isArray(data.mentorship) ? data.mentorship : data.mentorship?.open || [];
  const rows = raw.map(normalizeMentorship).filter(Boolean);
  const openRows = rows.filter((row) => !["COMPLETED", "SUSPENDED", "REJECTED"].includes(String(row.status_code || "").toUpperCase()));
  const first = openRows[0] || rows[0];
  const id = first?.mentorship_id;
  const chatClosed = ["COMPLETED", "SUSPENDED", "REJECTED"].includes(String(first?.status_code || "").toUpperCase());
  const admin = data.mentorship_admin;
  const metrics = admin?.metrics || {};
  const waiting = session.user_role === "student" && !rows.length
    && (data.appointments || []).some((row) => String(row.status || "").toLowerCase() === "requested");
  const youRole = session.user_role === "student" ? "student" : "mentor";
  const youAlias = session.user_role === "student" ? first?.student_alias : first?.mentor_alias;
  const otherAlias = session.user_role === "student" ? first?.mentor_alias : first?.student_alias;

  const applyThread = (next) => {
    const list = Array.isArray(next) ? next : [];
    setThread((prev) => {
      if (prev.length === list.length && prev.every((msg, i) => msg.id === list[i]?.id && msg.body === list[i]?.body)) {
        return prev;
      }
      return list;
    });
  };

  useEffect(() => {
    if (!id) {
      setThread([]);
      setLive(false);
      return undefined;
    }
    let cancelled = false;
    const pull = async () => {
      if (document.hidden) return;
      try {
        const res = await api.mentorshipMessages(id);
        if (cancelled) return;
        applyThread(Array.isArray(res) ? res : res?.messages || []);
        setLive(true);
        setChatError((err) => (err === "Could not load messages." ? "" : err));
      } catch (err) {
        if (!cancelled) setChatError(err.message || "Could not load messages.");
      }
    };
    pull();
    const timer = setInterval(pull, 1500);
    const onVis = () => { if (!document.hidden) pull(); };
    document.addEventListener("visibilitychange", onVis);
    return () => {
      cancelled = true;
      clearInterval(timer);
      document.removeEventListener("visibilitychange", onVis);
    };
  }, [id]);

  useEffect(() => {
    const node = scroller.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [thread]);

  const sendChat = async () => {
    const text = body.trim();
    if (!id || !text) {
      setChatError("Type a message first.");
      return;
    }
    setChatBusy(true);
    setChatError("");
    try {
      const res = await api.mentorshipMessage(id, { body: text });
      setBody("");
      applyThread(res?.messages);
    } catch (err) {
      setChatError(err.message || "Message did not send.");
    } finally {
      setChatBusy(false);
    }
  };
  return (
    <div className="space-y-4">
      {session.user_role === "student" && !rows.length && (
        <Notice
          title={waiting ? "Waiting for the counsellor" : "No private chat yet"}
          body={waiting
            ? "Your counsellor request is in. They must click Connect privately. After that, this page shows an alias chat (not their name)."
            : "Request a counsellor meeting under Interventions. This tab stays empty until they open the private chat."}
          tone="info"
        />
      )}
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
        <Card title="Private chat">
          <p className="mb-3 text-sm text-[#64748B]">
            You: {youAlias || "your alias"} · Other person: {otherAlias || "their alias"}. Do not type real names.
            {live ? " · Live — new messages appear here without refresh." : ""}
          </p>
          <div ref={scroller} className="mb-3 max-h-72 space-y-2 overflow-y-auto rounded-2xl border border-[#E2E8F0] bg-[#F8FAFC] p-3">
            {thread.length ? thread.map((msg, i) => {
              const mine = msg.sender_role === youRole;
              return (
                <div key={msg.id || i} className={`max-w-[85%] rounded-2xl px-3 py-2 text-sm ${mine ? "ml-auto bg-[#0F172A] text-white" : "bg-white text-[#0F172A]"}`}>
                  <p className={`mb-1 text-[10px] uppercase tracking-wide ${mine ? "text-slate-300" : "text-[#64748B]"}`}>
                    {mine ? "You" : (otherAlias || msg.sender_role)}
                  </p>
                  <p>{msg.body}</p>
                </div>
              );
            }) : (
              <p className="text-sm text-[#64748B]">No messages yet. Send the first one here.</p>
            )}
          </div>
          {chatError && <Notice title="Message did not send" body={chatError} tone="danger" />}
          {chatClosed ? (
            <Notice title="This chat is closed" body="No new messages can be sent. Identities stay hidden." tone="info" />
          ) : (
            <>
              <input
                className="mb-2 w-full rounded-2xl border px-4 py-2"
                value={body}
                onChange={(e) => setBody(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") sendChat(); }}
                placeholder="Message (no names)"
              />
              <button disabled={busy || chatBusy} className="mr-2 rounded-full bg-[#0F172A] px-4 py-2 text-sm text-white" onClick={sendChat}>
                {chatBusy ? "Sending…" : "Send message"}
              </button>
              <input className="mb-2 mt-3 w-full rounded-2xl border px-4 py-2" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Session title" />
              <button disabled={busy} className="mr-2 rounded-full border px-4 py-2 text-sm" onClick={() => run(() => api.mentorshipSession(id, { title, notes: body }))}>Log session</button>
              <button
                disabled={busy}
                className="rounded-full border border-red-200 px-4 py-2 text-sm text-red-700"
                onClick={() => {
                  if (!window.confirm("End this private chat? Messages stay saved. Names stay hidden.")) return;
                  run(() => api.mentorshipClose(id));
                }}
              >
                End private chat
              </button>
              {session.user_role === "student" && (
                <>
                  <button disabled={busy} className="mr-2 mt-2 rounded-full border px-4 py-2 text-sm" onClick={() => run(() => api.mentorshipFeedback(id, { answers: { helpful: "yes" } }))}>Submit feedback</button>
                  <button disabled={busy} className="mt-2 rounded-full border px-4 py-2 text-sm" onClick={() => run(() => api.mentorshipReassign(id))}>Request reassignment</button>
                </>
              )}
            </>
          )}
          {session.user_role === "administrator" && (
            <button disabled={busy} className="mt-2 rounded-full bg-red-600 px-4 py-2 text-sm text-white" onClick={() => run(() => api.mentorshipSuspend(id))}>Suspend</button>
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
  const [appealText, setAppealText] = useState("");
  const [appealReview, setAppealReview] = useState({ appeal_id: "", decision: "accept", notes: "Reviewed." });
  const firstId = data.complaints?.[0]?.complaint_id || data.complaints?.[0]?.id || "";
  const firstAppeal = data.appeals?.[0]?.id || "";
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
        <>
          <Card title="Execute moderation">
            <input className="mb-2 w-full rounded-2xl border px-4 py-2" placeholder="Complaint ID" value={decision.complaint_id || firstId} onChange={(e) => setDecision({ ...decision, complaint_id: e.target.value })} />
            <select className="mb-2 w-full rounded-2xl border px-4 py-2" value={decision.action} onChange={(e) => setDecision({ ...decision, action: e.target.value })}>
              {(meta.execute_actions || meta.actions || ["warning", "restrict", "ban"]).map((a) => <option key={a}>{a}</option>)}
            </select>
            <textarea className="mb-2 w-full rounded-2xl border p-3" rows={2} value={decision.notes} onChange={(e) => setDecision({ ...decision, notes: e.target.value })} />
            <button disabled={busy} className="mr-2 rounded-full border px-4 py-2 text-sm" onClick={() => run(() => api.openComplaint(decision.complaint_id || firstId))}>Open investigation</button>
            <button disabled={busy} className="co-btn" onClick={() => run(() => api.decideComplaint(decision.complaint_id || firstId, { action: decision.action, notes: decision.notes }))}>Record decision</button>
          </Card>
          <Card title="Review appeal">
            <input className="mb-2 w-full rounded-2xl border px-4 py-2" placeholder="Appeal ID" value={appealReview.appeal_id || firstAppeal} onChange={(e) => setAppealReview({ ...appealReview, appeal_id: e.target.value })} />
            <select className="mb-2 w-full rounded-2xl border px-4 py-2" value={appealReview.decision} onChange={(e) => setAppealReview({ ...appealReview, decision: e.target.value })}>
              <option value="accept">Accept / restore</option>
              <option value="reject">Reject</option>
              <option value="reduce">Reduce restriction</option>
              <option value="maintain">Maintain</option>
            </select>
            <textarea className="mb-2 w-full rounded-2xl border p-3" rows={2} value={appealReview.notes} onChange={(e) => setAppealReview({ ...appealReview, notes: e.target.value })} />
            <button disabled={busy} className="co-btn" onClick={() => run(() => api.reviewAppeal({ appeal_id: Number(appealReview.appeal_id || firstAppeal), decision: appealReview.decision, notes: appealReview.notes }))}>Record appeal decision</button>
          </Card>
        </>
      )}
      {session.user_role === "student" && (
        <Card title="Appeal">
          <p className="mb-2 text-sm text-[#64748B]">{data.account?.status ? `Account status: ${data.account.status}` : "No active restriction on this account."}</p>
          <textarea className="mb-2 w-full rounded-2xl border p-3" rows={3} value={appealText} onChange={(e) => setAppealText(e.target.value)} placeholder="Explain why this decision should be reviewed (at least 10 characters)." />
          <button disabled={busy} className="co-btn" onClick={() => run(() => api.submitAppeal({ reason: appealText.trim(), explanation: appealText.trim() }))}>Submit appeal</button>
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
