import { useEffect, useState } from "react";
import { api } from "./api";
import CameraCapture from "./CameraCapture";
import { EmptyState, Field, Notice } from "./ui";

const DEVICE_KEY = "classora_att_device";

function formatWhen(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString(undefined, { year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export default function SecureAttendance({ session }) {
  const role = session?.user_role;
  if (role === "student") return <StudentVerify />;
  if (role === "teacher" || role === "administrator") return <FacultySecure role={role} />;
  return <EmptyState title="Secure attendance is available to faculty and students." />;
}

function FacultySecure({ role }) {
  const [subjects, setSubjects] = useState([]);
  const [subjectId, setSubjectId] = useState("");
  const [lecture, setLecture] = useState("");
  const [duration, setDuration] = useState(15);
  const [photos, setPhotos] = useState([]);
  const [uploadFiles, setUploadFiles] = useState([]);
  const [current, setCurrent] = useState(null);
  const [sessions, setSessions] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [settings, setSettings] = useState(null);

  const load = async (sessionId) => {
    try {
      const subjectPromise = role === "teacher" ? api.teacherSubjects() : api.teacherSubjects().catch(() => []);
      const [subs, list] = await Promise.all([subjectPromise, api.attendanceSessions()]);
      setSubjects(subs || []);
      if (!subjectId && subs?.[0]) setSubjectId(String(subs[0].subject_id));
      setSessions(list.sessions || []);
      const id = sessionId || current?.id;
      if (id) {
        const one = await api.attendanceSession(id);
        setCurrent(one.session);
      }
      if (role === "administrator" || role === "teacher") {
        const cfg = await api.attendanceSettings().catch(() => null);
        setSettings(cfg);
      }
    } catch (err) {
      setError(err.message || "Attendance could not be loaded.");
    }
  };

  useEffect(() => {
    load();
  }, []);

  const run = async (fn, ok) => {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await fn();
      setNotice(ok || "Saved.");
      return result;
    } catch (err) {
      setError(err.message || "That action could not be completed.");
      return null;
    } finally {
      setBusy(false);
    }
  };

  const files = photos.length ? photos : uploadFiles;
  const counts = current?.counts || {};

  return (
    <div className="space-y-4">
      <div>
        <p className="co-section-kicker">Secure attendance</p>
        <h2 className="text-xl font-semibold">AI identifies. Verification confirms.</h2>
        <p className="text-sm text-[#64748B]">Face recognition alone does not mark a student present. The existing quick-save attendance tab is unchanged.</p>
      </div>
      {error && <Notice title="Attendance" body={error} tone="danger" />}
      {notice && <Notice title="Update" body={notice} tone="ok" />}

      <div className="co-card space-y-3">
        <h3 className="font-semibold">Start attendance</h3>
        <div className="co-anomaly-filters">
          <Field label="Subject">
            <select className="co-input" value={subjectId} onChange={(e) => setSubjectId(e.target.value)}>
              {subjects.map((sub) => (
                <option key={sub.subject_id} value={sub.subject_id}>{sub.subject_code} — {sub.name} ({sub.section})</option>
              ))}
            </select>
          </Field>
          <Field label="Lecture"><input className="co-input" value={lecture} onChange={(e) => setLecture(e.target.value)} placeholder="Lecture 4" /></Field>
          <Field label="Duration (minutes)"><input className="co-input" type="number" min={1} max={180} value={duration} onChange={(e) => setDuration(Number(e.target.value))} /></Field>
        </div>
        <button type="button" className="co-btn" disabled={busy || !subjectId} onClick={async () => {
          const result = await run(() => api.createAttendanceSession({
            subjectId: Number(subjectId),
            lecture,
            durationMinutes: duration,
          }), "Session started. Capture classroom photos next.");
          if (result?.session) {
            setCurrent(result.session);
            load(result.session.id);
          }
        }}>Start secure session</button>
      </div>

      {current && (
        <div className="co-card space-y-3">
          <h3 className="font-semibold">Active session · {current.subjectCode} {current.lecture}</h3>
          <p className="text-sm text-[#64748B]">{current.status} · expires {formatWhen(current.expiresAt)} · mode {current.verificationMode}</p>
          <div className="co-chips co-anomaly-chips">
            <div><em>Total</em><strong>{counts.total ?? "—"}</strong></div>
            <div><em>Matched</em><strong>{counts.matched ?? "—"}</strong></div>
            <div><em>Pending</em><strong>{counts.pending ?? "—"}</strong></div>
            <div><em>Present</em><strong>{counts.present ?? "—"}</strong></div>
            <div><em>Unknown</em><strong>{counts.unknown ?? "—"}</strong></div>
            <div><em>Review</em><strong>{counts.review ?? "—"}</strong></div>
          </div>
          <CameraCapture
            gallery
            mirrorPreview={false}
            maxSide={960}
            captureLabel="Capture classroom photo"
            label="Point the camera at the class"
            hint="Capture one or two photos, then analyze. Face match only creates a verification request."
            onFiles={setPhotos}
          />
          <Field label="Or upload classroom photos (if camera is unavailable)">
            <input className="co-input" type="file" accept="image/jpeg,image/png,image/webp" multiple onChange={(e) => setUploadFiles([...e.target.files])} />
          </Field>
          <div className="flex flex-wrap gap-2">
            <button type="button" className="co-btn" disabled={busy || !files.length} onClick={async () => {
              const result = await run(() => api.analyzeAttendanceSession(current.id, files), "Analysis stored. Matched students must verify.");
              if (result?.session) setCurrent(result.session);
            }}>{busy ? "Analyzing…" : "Analyze"}</button>
            <button type="button" className="co-btn co-btn-secondary" disabled={busy} onClick={() => load(current.id)}>Refresh monitor</button>
            <button type="button" className="co-btn co-btn-secondary" disabled={busy} onClick={async () => {
              const result = await run(() => api.completeAttendanceSession(current.id), "Session completed. Unverified students were not marked present.");
              if (result?.session) setCurrent(result.session);
            }}>Complete session</button>
          </div>
          <div className="overflow-x-auto">
            <table className="co-table">
              <thead><tr><th>Student</th><th>Face</th><th>Verification</th><th>Attendance</th><th></th></tr></thead>
              <tbody>
                {(current.students || []).map((row) => (
                  <tr key={row.studentId}>
                    <td>{row.name} · {row.studentId}</td>
                    <td>{row.faceStatus || "—"}{row.confidence != null ? ` (${Math.round(row.confidence * 100)}%)` : ""}</td>
                    <td>{row.verificationMethod || row.status}</td>
                    <td>{row.status}</td>
                    <td>
                      <button type="button" className="co-btn co-btn-tertiary" disabled={busy} onClick={() => {
                        const reason = window.prompt("Reason for this correction");
                        const decision = window.prompt("Decision: PRESENT, ABSENT, or REJECT", "PRESENT");
                        if (reason && decision) run(() => api.correctAttendance(current.id, { studentId: row.studentId, decision, reason }).then(async () => {
                          const one = await api.attendanceSession(current.id);
                          setCurrent(one.session);
                        }), "Correction saved.");
                      }}>Correct</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div className="co-card">
        <h3 className="mb-3 font-semibold">Recent secure sessions</h3>
        {!(sessions || []).length && <EmptyState title="No secure sessions yet." />}
        {(sessions || []).map((row) => (
          <button key={row.id} type="button" className="mb-2 block text-left text-sm" onClick={() => load(row.id)}>
            <strong>{row.subjectCode}</strong> · {row.status} · {formatWhen(row.startedAt)} · present {row.counts?.present ?? 0}
          </button>
        ))}
      </div>

      {settings?.email && settings.email.enabled && !settings.email.configured && (
        <Notice title="Email verification" body={settings.email.message} tone="warn" />
      )}
    </div>
  );
}

function StudentVerify() {
  const [pending, setPending] = useState([]);
  const [history, setHistory] = useState([]);
  const [selected, setSelected] = useState(null);
  const [token, setToken] = useState("");
  const [code, setCode] = useState("");
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = async () => {
    try {
      const [p, h] = await Promise.all([api.attendancePending(), api.attendanceHistory()]);
      setPending(p.pending || []);
      setHistory(h.history || []);
    } catch (err) {
      setError(err.message || "Could not load attendance verification.");
    }
  };

  useEffect(() => {
    load();
  }, []);

  const device = () => localStorage.getItem(DEVICE_KEY) || "";

  const ensureDevice = async () => {
    const existing = device();
    const issued = await api.registerAttendanceDevice({ deviceToken: existing });
    if (issued.deviceToken) localStorage.setItem(DEVICE_KEY, issued.deviceToken);
    return issued.deviceToken || existing;
  };

  const run = async (fn) => {
    setBusy(true);
    setError("");
    try {
      return await fn();
    } catch (err) {
      setError(err.message || "Attendance verification could not be completed. Please try again.");
      return null;
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      <div>
        <p className="co-section-kicker">Attendance verification</p>
        <h2 className="text-xl font-semibold">Confirm you are present</h2>
        <p className="text-sm text-[#64748B]">A face match only starts verification. You must confirm from this signed-in device.</p>
      </div>
      {error && <Notice title="Verification" body={error} tone="danger" />}
      {result?.status === "PRESENT" && (
        <Notice title="Attendance verified" body={`${result.subjectName || "Class"} · ${result.verification} · ${formatWhen(result.verifiedAt)}`} tone="ok" />
      )}

      {!(pending || []).length && !selected && <EmptyState title="No attendance verification waiting." body="When faculty recognizes your face in class, a request will appear here." />}
      {(pending || []).map((row) => (
        <div key={row.id} className="co-card space-y-2">
          <strong>{row.subjectName || row.subjectCode}</strong>
          <p className="text-sm text-[#64748B]">Faculty {row.facultyName || "—"} · {formatWhen(row.startedAt)} · {row.status}</p>
          <button type="button" className="co-btn" onClick={() => { setSelected(row); setResult(null); setToken(""); setCode(""); }}>Verify now</button>
        </div>
      ))}

      {selected && (
        <div className="co-card space-y-3">
          <h3 className="font-semibold">{selected.subjectName || selected.subjectCode}</h3>
          <p className="text-sm text-[#64748B]">Faculty {selected.facultyName} · expires {formatWhen(selected.expiresAt)}</p>
          <p className="text-sm">Status: waiting for verification</p>
          <div className="flex flex-wrap gap-2">
            <button type="button" className="co-btn co-btn-secondary" disabled={busy} onClick={async () => {
              const issued = await run(() => api.issueAttendanceQr({ sessionId: selected.id }));
              if (issued?.token) setToken(issued.token);
            }}>Get short-lived QR token</button>
            <button type="button" className="co-btn co-btn-secondary" disabled={busy} onClick={async () => {
              const issued = await run(() => api.issueAttendanceCode({ sessionId: selected.id }));
              if (issued?.code) setCode(issued.code);
            }}>Get one-time code</button>
          </div>
          {token && <p className="break-all font-mono text-sm" aria-label="Verification token">{token}</p>}
          {code && <p className="font-mono text-lg" aria-label="One-time code">{code}</p>}
          <Field label="Or paste a token">
            <input className="co-input" value={token} onChange={(e) => setToken(e.target.value)} />
          </Field>
          <Field label="Or enter the one-time code">
            <input className="co-input" value={code} onChange={(e) => setCode(e.target.value)} />
          </Field>
          <button type="button" className="co-btn" disabled={busy} onClick={async () => {
            const deviceToken = await ensureDevice();
            const confirmed = await run(() => api.confirmAttendanceVerification({
              sessionId: selected.id,
              token,
              code,
              deviceToken,
            }));
            if (confirmed?.ok) {
              setResult(confirmed);
              setSelected(null);
              load();
            }
          }}>Confirm presence</button>
        </div>
      )}

      <div className="co-card">
        <h3 className="mb-3 font-semibold">My attendance history</h3>
        {!(history || []).length && <EmptyState title="Verified sessions will appear here." />}
        {(history || []).map((row, index) => (
          <p key={`${row.startedAt}-${index}`} className="mb-2 text-sm">
            <strong>{row.subjectCode}</strong> · {row.status} · {row.verificationMethod || row.source || "—"} · {formatWhen(row.verifiedAt || row.startedAt)}
          </p>
        ))}
      </div>
    </div>
  );
}
