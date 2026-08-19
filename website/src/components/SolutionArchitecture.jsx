import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  Activity,
  AudioLines,
  Camera,
  Check,
  ClipboardCheck,
  HeartHandshake,
  Mic,
  ScanFace,
  ShieldCheck,
  Sparkles,
  Square,
  UserPlus,
  Zap,
} from "lucide-react";

const IN_PATHS = [
  { id: "sol-in-face", feat: "face", d: "M 250 95 C 360 95, 425 240, 500 240" },
  { id: "sol-in-voice", feat: "voice", d: "M 250 240 C 375 240, 430 240, 500 240" },
  { id: "sol-in-enroll", feat: "enroll", d: "M 250 385 C 360 385, 425 240, 500 240" },
];
const OUT_PATHS = [
  { id: "sol-out-attend", feat: "attend", pair: "face", d: "M 500 240 C 575 240, 640 95, 750 95" },
  { id: "sol-out-counsel", feat: "counsel", pair: "voice", d: "M 500 240 C 570 240, 630 240, 750 240" },
  { id: "sol-out-cases", feat: "cases", pair: "enroll", d: "M 500 240 C 575 240, 640 385, 750 385" },
];

const DUST = [
  { t: "12%", l: "8%", d: "0s" },
  { t: "22%", l: "91%", d: "0.4s" },
  { t: "68%", l: "6%", d: "0.8s" },
  { t: "78%", l: "94%", d: "1.1s" },
  { t: "8%", l: "48%", d: "1.5s" },
  { t: "88%", l: "52%", d: "1.9s" },
];

const CORE = {
  ready: { kicker: "02 — Intelligence", title: "CLASSORA AI", sub: "Ready" },
  face: { kicker: "FACE PIPELINE", title: "ACTIVE", sub: "Processing" },
  voice: { kicker: "VOICE PIPELINE", title: "READY", sub: "Standing by" },
  voiceListen: { kicker: "VOICE PIPELINE", title: "LISTENING", sub: "Signal in" },
  voiceRecv: { kicker: "VOICE SIGNAL", title: "RECEIVED", sub: "Analyzing" },
  enroll: { kicker: "IDENTITY LAYER", title: "ACTIVE", sub: "Analyzing" },
  attend: { kicker: "HUMAN REVIEW", title: "AWAITING", sub: "Decision" },
  attendOk: { kicker: "ATTENDANCE", title: "VERIFIED", sub: "Human confirmed" },
  counsel: { kicker: "HUMAN REVIEW", title: "AWAITING", sub: "Decision" },
  cases: { kicker: "RISK INTELLIGENCE", title: "READY", sub: "Awaiting decision" },
  risk: { kicker: "RISK INTELLIGENCE", title: "ANALYZING", sub: "Human review" },
  core: { kicker: "02 — Intelligence", title: "CLASSORA AI", sub: "Ready" },
};

const PLANS = [
  { id: "academic", label: "Academic support" },
  { id: "counsel", label: "Counselling follow-up" },
  { id: "attend", label: "Attendance monitoring" },
];

function speechCtor() {
  if (typeof window === "undefined") return null;
  return window.SpeechRecognition || window.webkitSpeechRecognition || null;
}

function pathActive(feat, path) {
  if (!feat || feat === "core") return false;
  if (feat === "risk") return path.feat === "enroll" || path.pair === "enroll" || path.feat === "cases";
  return feat === path.feat || feat === path.pair;
}

function coreKey({ feat, listening, voiceRecv, attendanceConfirmed }) {
  if (listening === "voice") return "voiceListen";
  if (listening === "review") return "counsel";
  if (attendanceConfirmed && (feat === "attend" || feat === "face")) return "attendOk";
  if (voiceRecv && (feat === "voice" || feat === "counsel")) return "voiceRecv";
  return CORE[feat] ? feat : "ready";
}

export default function SolutionArchitecture() {
  const wrap = useRef(null);
  const recRef = useRef(null);
  const demoRef = useRef(null);
  const attendRef = useRef(null);
  const ignoreEnd = useRef(false);
  const session = useRef(null);

  const [feat, setFeat] = useState(null);
  const [reduce, setReduce] = useState(false);
  const [coarse, setCoarse] = useState(false);
  const [listening, setListening] = useState(null);
  const [voiceTranscript, setVoiceTranscript] = useState("");
  const [voiceError, setVoiceError] = useState("");
  const [reviewTranscript, setReviewTranscript] = useState("");
  const [reviewReady, setReviewReady] = useState(false);
  const [reviewError, setReviewError] = useState("");
  const [attendPhase, setAttendPhase] = useState("idle");
  const [enrollOpen, setEnrollOpen] = useState(false);
  const [enrollDraft, setEnrollDraft] = useState({ name: "", id: "" });
  const [planOpen, setPlanOpen] = useState(false);
  const [planChoice, setPlanChoice] = useState("");
  const [planHeld, setPlanHeld] = useState(false);

  const attendanceConfirmed = attendPhase === "confirmed";
  const voiceRecv = Boolean(voiceTranscript);
  const status = CORE[coreKey({ feat, listening, voiceRecv, attendanceConfirmed })];

  const stopRec = () => {
    ignoreEnd.current = true;
    session.current = null;
    try {
      recRef.current?.abort();
    } catch {
      /* already stopped */
    }
    try {
      recRef.current?.stop();
    } catch {
      /* already stopped */
    }
    recRef.current = null;
    if (demoRef.current) {
      clearTimeout(demoRef.current);
      demoRef.current = null;
    }
  };

  useEffect(() => {
    setReduce(window.matchMedia("(prefers-reduced-motion: reduce)").matches);
    setCoarse(window.matchMedia("(pointer: coarse)").matches);
    return () => {
      stopRec();
      if (attendRef.current) clearTimeout(attendRef.current);
    };
  }, []);

  const failMic = (target, message = "Microphone unavailable") => {
    stopRec();
    setListening(null);
    if (target === "voice") setVoiceError(message);
    else setReviewError(message);
  };

  const listen = (target) => {
    stopRec();
    ignoreEnd.current = false;
    session.current = target;
    setListening(target);
    setFeat(target === "voice" ? "voice" : "counsel");
    if (target === "voice") {
      setVoiceError("");
      setVoiceTranscript("");
    } else {
      setReviewError("");
      setReviewTranscript("");
      setReviewReady(false);
    }

    const Ctor = speechCtor();
    if (!Ctor) {
      failMic(target);
      return;
    }

    const rec = new Ctor();
    rec.lang = "en-IN";
    rec.interimResults = true;
    rec.continuous = true;
    rec.maxAlternatives = 1;

    rec.onresult = (e) => {
      if (session.current !== target) return;
      let text = "";
      for (let i = 0; i < e.results.length; i++) text += e.results[i][0].transcript;
      const trimmed = text.trim();
      if (target === "voice") setVoiceTranscript(trimmed);
      else setReviewTranscript(trimmed);
    };

    rec.onerror = (e) => {
      const err = e?.error || "";
      if (err === "aborted" || err === "cancelled") return;
      if (err === "no-speech") return;
      failMic(target);
    };

    rec.onend = () => {
      recRef.current = null;
      if (ignoreEnd.current || session.current !== target) return;
      setListening((cur) => (cur === target ? null : cur));
    };

    recRef.current = rec;
    try {
      rec.start();
    } catch {
      failMic(target);
    }
  };

  const stopListen = (target) => {
    stopRec();
    setListening(null);
    if (target === "voice" && !voiceTranscript) setVoiceError("");
    if (target === "review" && !reviewTranscript) setReviewError("");
  };

  const onMove = (e) => {
    if (reduce || coarse || !wrap.current) return;
    const r = wrap.current.getBoundingClientRect();
    const x = ((e.clientX - r.left) / r.width - 0.5) * 2;
    const y = ((e.clientY - r.top) / r.height - 0.5) * 2;
    wrap.current.style.setProperty("--px", x.toFixed(3));
    wrap.current.style.setProperty("--py", y.toFixed(3));
  };

  const onLeave = () => {
    if (!wrap.current) return;
    wrap.current.style.setProperty("--px", "0");
    wrap.current.style.setProperty("--py", "0");
  };

  const activate = (next) => {
    setFeat(next);
    if (next !== "enroll") setEnrollOpen(false);
    if (next !== "cases") setPlanOpen(false);
  };

  const confirmAttendance = () => {
    activate("attend");
    if (attendPhase === "confirmed" || attendPhase === "confirming") return;
    setAttendPhase("confirming");
    attendRef.current = setTimeout(() => setAttendPhase("confirmed"), 420);
  };

  const liveMsg = listening === "voice"
    ? "Listening for classroom voice."
    : listening === "review"
      ? "Listening for counsellor review."
      : voiceError || reviewError || (attendanceConfirmed ? "Attendance verified." : "");

  return (
    <motion.div
      ref={wrap}
      initial={{ opacity: 0, y: 20 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.15 }}
      onMouseMove={onMove}
      onMouseLeave={onLeave}
      data-feat={feat || undefined}
      className="sol-pipe relative mt-12 overflow-x-hidden rounded-[28px] border border-[#d7e0ee] bg-white px-4 py-8 sm:px-6 md:px-8 md:py-12"
    >
      <div className="pointer-events-none absolute inset-0 z-0 grid-tech opacity-70" />
      <div className="pointer-events-none absolute left-1/2 top-[42%] z-0 h-[320px] w-[320px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-[radial-gradient(circle,rgba(37,99,235,0.09),transparent_68%)]" />
      <div className="sr-only" aria-live="polite">
        {liveMsg}
      </div>

      {!reduce &&
        DUST.map((p, i) => (
          <span key={i} className="sol-dust" style={{ top: p.t, left: p.l, animationDelay: p.d }} aria-hidden />
        ))}

      <p className="relative z-[1] mb-8 text-center text-[11px] font-bold uppercase tracking-[0.2em] text-[#2563EB]">
        Classroom Data → Classora AI → Human Action
      </p>

      <div className="sol-stage relative z-[2] mx-auto max-w-6xl">
        <svg
          className="pointer-events-none absolute inset-0 z-0 hidden h-full w-full md:block"
          viewBox="0 0 1000 520"
          preserveAspectRatio="none"
          fill="none"
          aria-hidden
        >
          {IN_PATHS.map((p) => (
            <path
              key={p.id}
              id={p.id}
              d={p.d}
              className={`sol-path sol-path-in sol-feat-${p.feat} ${pathActive(feat, p) ? "is-on" : ""}`}
            />
          ))}
          {OUT_PATHS.map((p) => (
            <path
              key={p.id}
              id={p.id}
              d={p.d}
              className={`sol-path sol-path-out sol-feat-${p.pair} ${pathActive(feat, p) ? "is-on" : ""}`}
            />
          ))}
          {!reduce &&
            [...IN_PATHS, ...OUT_PATHS].map((p, i) => {
              const on = pathActive(feat, p);
              return (
                <circle key={`${p.id}-dot`} r={on ? 3.6 : 2.8} className={`sol-dot ${on ? "is-on" : ""}`}>
                  <animateMotion dur={on ? "1.8s" : "6s"} begin={`${i * 0.22}s`} repeatCount="indefinite">
                    <mpath href={`#${p.id}`} />
                  </animateMotion>
                </circle>
              );
            })}
        </svg>

        <div className="sol-grid relative z-[2] grid grid-cols-1 items-center gap-3 md:grid-cols-[minmax(0,1fr)_minmax(210px,0.9fr)_minmax(0,1fr)] md:min-h-[460px] md:gap-4 lg:min-h-[500px]">
          <CapturePanel
            feat={feat}
            activate={activate}
            reduce={reduce}
            coarse={coarse}
            listening={listening === "voice"}
            transcript={voiceTranscript}
            error={voiceError}
            enrollOpen={enrollOpen}
            enrollDraft={enrollDraft}
            setEnrollDraft={setEnrollDraft}
            onOpenEnroll={() => {
              activate("enroll");
              setEnrollOpen(true);
            }}
            onCloseEnroll={() => setEnrollOpen(false)}
            onListen={() => listen("voice")}
            onStop={() => stopListen("voice")}
          />

          <MobileRail reduce={reduce} feat={feat} id="sol-mv-1" />

          <IntelligenceCore feat={feat} status={status} activate={activate} voiceRecv={voiceRecv} />

          <MobileRail reduce={reduce} feat={feat} id="sol-mv-2" />

          <ActionPanel
            feat={feat}
            activate={activate}
            reduce={reduce}
            coarse={coarse}
            listening={listening === "review"}
            transcript={reviewTranscript}
            error={reviewError}
            reviewReady={reviewReady}
            attendPhase={attendPhase}
            planOpen={planOpen}
            planChoice={planChoice}
            planHeld={planHeld}
            setPlanChoice={setPlanChoice}
            onConfirmAttend={confirmAttendance}
            onOpenPlan={() => {
              activate("cases");
              setPlanOpen(true);
            }}
            onClosePlan={() => setPlanOpen(false)}
            onHoldPlan={() => {
              if (!planChoice) return;
              setPlanHeld(true);
              setPlanOpen(false);
            }}
            onListen={() => listen("review")}
            onStop={() => stopListen("review")}
            onUseReview={() => {
              if (!reviewTranscript) return;
              stopListen("review");
              setReviewReady(true);
              activate("counsel");
            }}
            onCancelReview={() => {
              stopListen("review");
              setReviewTranscript("");
              setReviewReady(false);
              setReviewError("");
            }}
          />
        </div>
      </div>

      <div className="relative z-[2] mx-auto mt-10 flex max-w-xl items-start gap-3 rounded-2xl border border-[#d7e0ee] bg-[#F6F8FC] px-4 py-3.5 sm:px-5">
        <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-white text-[#2563EB] shadow-[0_6px_16px_rgba(11,31,74,0.06)]">
          <ShieldCheck className="h-4 w-4" aria-hidden />
        </span>
        <div>
          <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-[#2563EB]">Human-in-the-loop</p>
          <p className="mt-1 text-[13px] leading-6 text-[#5b6b82]">
            AI surfaces insights. Authorized humans make the final decision.
          </p>
        </div>
      </div>
    </motion.div>
  );
}

function useCardTilt(reduce, coarse) {
  const ref = useRef(null);
  const move = (e) => {
    if (reduce || coarse || !ref.current) return;
    const r = ref.current.getBoundingClientRect();
    const x = ((e.clientX - r.left) / r.width - 0.5) * 2;
    const y = ((e.clientY - r.top) / r.height - 0.5) * 2;
    ref.current.style.setProperty("--rx", `${(-y * 3).toFixed(2)}deg`);
    ref.current.style.setProperty("--ry", `${(x * 3).toFixed(2)}deg`);
  };
  const leave = () => {
    if (!ref.current) return;
    ref.current.style.setProperty("--rx", "0deg");
    ref.current.style.setProperty("--ry", "0deg");
  };
  return { ref, move, leave };
}

function CapturePanel({
  feat,
  activate,
  reduce,
  coarse,
  listening,
  transcript,
  error,
  enrollOpen,
  enrollDraft,
  setEnrollDraft,
  onOpenEnroll,
  onCloseEnroll,
  onListen,
  onStop,
}) {
  const tilt = useCardTilt(reduce, coarse);
  const voiceOn = feat === "voice" || listening;
  return (
    <article
      ref={tilt.ref}
      onMouseMove={tilt.move}
      onMouseLeave={tilt.leave}
      className={`sol-card sol-card-in ${feat === "face" || feat === "voice" || feat === "enroll" ? "is-hot" : ""}`}
    >
      <div className="sol-card-body">
        <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-[#2563EB]">01 — Capture</p>
        <h3 className="mt-1.5 text-[17px] font-semibold tracking-[-0.02em] text-[#0B1F4A]">Classroom Intelligence</h3>

        <div className="mt-4 space-y-2.5">
          <MiniFeature
            active={feat === "face"}
            icon={Camera}
            kicker="Face Capture"
            title="Face Presence"
            body="Real-time classroom presence signals."
            status="Standby"
            activeStatus="Live"
            onActivate={() => activate("face")}
          />
          <MiniFeature
            active={voiceOn}
            icon={Mic}
            kicker="Voice Capture"
            title="Voice Presence"
            body="Capture classroom voice/activity signals."
            status="Idle"
            activeStatus={listening ? "Listening" : "Ready"}
            onActivate={() => activate("voice")}
          >
            <Waveform live={listening} />
            {listening ? <p className="mt-2 text-[11px] font-semibold text-[#0B1F4A]">Listening…</p> : null}
            {transcript ? (
              <blockquote className="sol-quote mt-2">“{transcript}”</blockquote>
            ) : null}
            {transcript && !listening ? (
              <p className="mt-1.5 text-[11px] font-semibold text-[#2563EB]">Voice signal received</p>
            ) : null}
            {error ? <p className="mt-1.5 text-[11px] text-[#5b6b82]">{error}</p> : null}
            <div className="mt-2 flex flex-wrap gap-2">
              {listening ? (
                <button type="button" className="sol-mic-btn" aria-pressed="true" aria-label="Stop listening" onClick={onStop}>
                  <Square size={10} /> Stop Listening
                </button>
              ) : (
                <button type="button" className="sol-mic-btn" aria-pressed="false" aria-label="Listen" onClick={onListen}>
                  <Mic size={11} /> Listen
                </button>
              )}
            </div>
          </MiniFeature>
          <MiniFeature
            active={feat === "enroll"}
            icon={UserPlus}
            kicker="Enrollment"
            title="Student Enrollment"
            body="Secure student identity registration."
            status="Secure"
            activeStatus="Linked"
            onActivate={onOpenEnroll}
            onHover={() => activate("enroll")}
          >
            {enrollOpen ? (
              <div className="sol-pop mt-2" onClick={(e) => e.stopPropagation()}>
                <p className="text-[11px] font-bold uppercase tracking-[0.12em] text-[#2563EB]">Student Enrollment</p>
                <label className="mt-2 block text-[10px] font-semibold text-[#5b6b82]">
                  Display name
                  <input
                    className="sol-input"
                    value={enrollDraft.name}
                    onChange={(e) => setEnrollDraft((d) => ({ ...d, name: e.target.value }))}
                    placeholder="Optional demo name"
                  />
                </label>
                <label className="mt-2 block text-[10px] font-semibold text-[#5b6b82]">
                  Student ID
                  <input
                    className="sol-input"
                    value={enrollDraft.id}
                    onChange={(e) => setEnrollDraft((d) => ({ ...d, id: e.target.value }))}
                    placeholder="Optional demo ID"
                  />
                </label>
                <p className="mt-2 text-[10px] leading-4 text-[#5b6b82]">Demo only — not saved to Classora.</p>
                <button type="button" className="sol-mic-btn mt-2" onClick={onCloseEnroll}>
                  Close
                </button>
              </div>
            ) : null}
          </MiniFeature>
        </div>
      </div>
    </article>
  );
}

function ActionPanel({
  feat,
  activate,
  reduce,
  coarse,
  listening,
  transcript,
  error,
  reviewReady,
  attendPhase,
  planOpen,
  planChoice,
  planHeld,
  setPlanChoice,
  onConfirmAttend,
  onOpenPlan,
  onClosePlan,
  onHoldPlan,
  onListen,
  onStop,
  onUseReview,
  onCancelReview,
}) {
  const tilt = useCardTilt(reduce, coarse);
  const attendOn = feat === "attend" || feat === "face" || attendPhase !== "idle";
  const attendStatus = attendPhase === "confirmed" ? "Confirmed ✓" : attendPhase === "confirming" ? "Confirming…" : "Confirm";
  return (
    <article
      ref={tilt.ref}
      onMouseMove={tilt.move}
      onMouseLeave={tilt.leave}
      className={`sol-card sol-card-out ${feat === "attend" || feat === "counsel" || feat === "cases" || feat === "risk" ? "is-hot" : ""}`}
    >
      <div className="sol-card-body">
        <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-[#2563EB]">03 — Human Action</p>
        <h3 className="mt-1.5 text-[17px] font-semibold tracking-[-0.02em] text-[#0B1F4A]">Trusted Intervention</h3>

        <div className="mt-4 space-y-2.5">
          <MiniFeature
            active={attendOn}
            icon={ClipboardCheck}
            kicker="Attendance"
            title="Confirm Attendance"
            body="Review and confirm detected presence."
            status="Review"
            activeStatus={attendStatus}
            onActivate={onConfirmAttend}
            onHover={() => activate("attend")}
          />
          <MiniFeature
            active={feat === "counsel" || feat === "voice" || listening || reviewReady}
            icon={HeartHandshake}
            kicker="Counsellor"
            title="Counsellor Review"
            body="Review AI-generated student insights."
            status="Human"
            activeStatus={reviewReady ? "Review ready" : listening ? "Listening" : "Voice review"}
            onActivate={() => activate("counsel")}
          >
            <Waveform live={listening} />
            {listening ? <p className="mt-2 text-[11px] font-semibold text-[#0B1F4A]">Listening for counsellor review…</p> : null}
            {transcript ? (
              <div className="mt-2">
                <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-[#2563EB]">Voice Review</p>
                <blockquote className="sol-quote mt-1">“{transcript}”</blockquote>
              </div>
            ) : null}
            {reviewReady ? <p className="mt-1.5 text-[11px] font-semibold text-[#2563EB]">Review ready</p> : null}
            {error ? <p className="mt-1.5 text-[11px] text-[#5b6b82]">{error}</p> : null}
            <div className="mt-2 flex flex-wrap gap-2">
              {listening ? (
                <button type="button" className="sol-mic-btn" aria-pressed="true" aria-label="Stop recording" onClick={onStop}>
                  <Square size={10} /> Stop recording
                </button>
              ) : (
                <button type="button" className="sol-mic-btn" aria-label="Add review by voice" onClick={onListen}>
                  <Mic size={11} /> Add review by voice
                </button>
              )}
              {transcript && !listening ? (
                <>
                  <button type="button" className="sol-mic-btn" onClick={onCancelReview}>
                    Cancel
                  </button>
                  <button type="button" className="sol-mic-btn sol-mic-btn-solid" onClick={onUseReview}>
                    <Check size={11} /> Use Review
                  </button>
                </>
              ) : null}
            </div>
            <p className="mt-2 text-[10px] font-semibold uppercase tracking-[0.12em] text-[#5b6b82]">
              Review → Confirm → Save
            </p>
          </MiniFeature>
          <MiniFeature
            active={feat === "cases" || feat === "enroll" || feat === "risk" || planHeld}
            icon={Zap}
            kicker="Intervention"
            title="Cases & Plans"
            body="Create appropriate support plans."
            status="Queued"
            activeStatus={planHeld ? "Held" : "Human only"}
            onActivate={onOpenPlan}
            onHover={() => activate("cases")}
          >
            {planOpen ? (
              <div className="sol-pop mt-2" onClick={(e) => e.stopPropagation()}>
                <p className="text-[11px] font-bold uppercase tracking-[0.12em] text-[#2563EB]">Support Plan</p>
                <div className="mt-2 space-y-1.5">
                  {PLANS.map((p) => (
                    <label key={p.id} className="flex items-center gap-2 text-[12px] text-[#0B1F4A]">
                      <input
                        type="radio"
                        name="sol-plan"
                        checked={planChoice === p.id}
                        onChange={() => setPlanChoice(p.id)}
                      />
                      {p.label}
                    </label>
                  ))}
                </div>
                <p className="mt-2 text-[10px] leading-4 text-[#5b6b82]">Demo only — no case is created automatically.</p>
                <div className="mt-2 flex flex-wrap gap-2">
                  <button type="button" className="sol-mic-btn" onClick={onClosePlan}>
                    Cancel
                  </button>
                  <button type="button" className="sol-mic-btn sol-mic-btn-solid" disabled={!planChoice} onClick={onHoldPlan}>
                    Hold for review
                  </button>
                </div>
              </div>
            ) : null}
            {planHeld && !planOpen ? (
              <p className="mt-2 text-[11px] leading-4 text-[#0B1F4A]">Support plan held for human confirmation. Not saved as an intervention.</p>
            ) : null}
          </MiniFeature>
        </div>
        <p className="mt-4 flex items-center gap-1.5 text-[11px] font-semibold text-[#0B1F4A]/75">
          <Sparkles size={12} className="text-[#2563EB]" aria-hidden />
          AI recommends · Humans decide
        </p>
      </div>
    </article>
  );
}

function MiniFeature({ active, icon: Icon, kicker, title, body, status, activeStatus, onHover, onActivate, children }) {
  const highlight = onHover || onActivate;
  const onKey = (e) => {
    if (e.key !== "Enter" && e.key !== " ") return;
    if (e.target !== e.currentTarget) return;
    e.preventDefault();
    onActivate?.();
  };
  const onClick = (e) => {
    if (e.target.closest("button, input, label, textarea, a")) return;
    onActivate?.();
  };
  return (
    <div
      role="button"
      tabIndex={0}
      onMouseEnter={highlight}
      onFocus={highlight}
      onClick={onClick}
      onKeyDown={onKey}
      className={`sol-mini ${active ? "is-on" : ""}`}
    >
      <span className="sol-mini-ico" aria-hidden>
        <Icon size={15} strokeWidth={2.1} />
      </span>
      <span className="min-w-0 flex-1 text-left">
        <span className="flex items-center justify-between gap-2">
          <span className="text-[9px] font-bold uppercase tracking-[0.14em] text-[#2563EB]">{kicker}</span>
          <span className={`sol-status ${active ? "is-on" : ""}`}>
            <i />
            {active ? activeStatus : status}
          </span>
        </span>
        <span className="mt-0.5 block text-[13px] font-semibold text-[#0B1F4A]">{title}</span>
        <span className="mt-0.5 block text-[11px] leading-4 text-[#5b6b82]">{body}</span>
        {children}
      </span>
    </div>
  );
}

function Waveform({ live }) {
  return (
    <svg viewBox="0 0 84 22" className={`sol-wave mt-2 ${live ? "is-live" : ""}`} aria-hidden>
      {Array.from({ length: 11 }, (_, i) => (
        <rect key={i} x={i * 7.6 + 1} y="10" width="3.2" height="2" rx="1.4" />
      ))}
    </svg>
  );
}

function IntelligenceCore({ feat, status, activate, voiceRecv }) {
  const hot = Boolean(feat);
  return (
    <div className="sol-core-wrap relative z-[2] mx-auto flex flex-col items-center py-6 lg:mb-4 lg:py-4">
      <div className="sol-chips">
        <button
          type="button"
          className={`sol-chip sol-chip-face ${feat === "face" || feat === "attend" ? "is-on" : ""}`}
          aria-pressed={feat === "face" || feat === "attend"}
          onClick={() => activate("face")}
        >
          <ScanFace size={12} aria-hidden /> Face Pipeline
        </button>
        <button
          type="button"
          className={`sol-chip sol-chip-voice ${feat === "voice" || feat === "counsel" || voiceRecv ? "is-on" : ""}`}
          aria-pressed={feat === "voice" || feat === "counsel"}
          onClick={() => activate("voice")}
        >
          <AudioLines size={12} aria-hidden /> Voice Pipeline
        </button>
        <button
          type="button"
          className={`sol-chip sol-chip-risk ${feat === "enroll" || feat === "cases" || feat === "risk" ? "is-on" : ""}`}
          aria-pressed={feat === "risk" || feat === "cases"}
          onClick={() => activate("risk")}
        >
          <Activity size={12} aria-hidden /> Risk Intelligence
        </button>
      </div>

      <button
        type="button"
        aria-describedby="classora-ai-tip"
        onMouseEnter={() => activate("core")}
        onFocus={() => activate("core")}
        onClick={() => activate("core")}
        className={`sol-core-rig ${hot ? "is-hot" : ""}`}
      >
        <span className="sol-core-shadow" aria-hidden />
        <span className="sol-glass sol-glass-a" aria-hidden />
        <span className="sol-glass sol-glass-b" aria-hidden />
        <span className="sol-glass sol-glass-c" aria-hidden />
        <span className="sol-ring sol-ring-a" aria-hidden />
        <span className="sol-ring sol-ring-b" aria-hidden />
        <span className="sol-orbit" aria-hidden>
          <i />
          <i />
          <i />
          <i />
        </span>
        <span className="sol-sphere">
          <span className="sol-sphere-sheen" aria-hidden />
          <AnimatePresence mode="wait">
            <motion.span
              key={status.title + status.kicker}
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -4 }}
              transition={{ duration: 0.22 }}
              className="relative z-[1] flex flex-col items-center px-2 text-center"
            >
              <span className="text-[8px] font-bold uppercase tracking-[0.14em] text-cyan-200">{status.kicker}</span>
              <span className="mt-0.5 text-[13px] font-semibold tracking-[-0.03em] text-white sm:text-[14px]">
                {status.title}
              </span>
              <span className="mt-0.5 text-[9px] font-medium uppercase tracking-[0.12em] text-blue-100/80">
                {status.sub}
              </span>
            </motion.span>
          </AnimatePresence>
        </span>
      </button>

      <span
        id="classora-ai-tip"
        role="tooltip"
        className={`pointer-events-none absolute left-1/2 z-[4] w-[min(240px,78vw)] -translate-x-1/2 rounded-xl border border-[#d7e0ee] bg-white px-3 py-2 text-left text-[11px] leading-4 text-[#5b6b82] shadow-[0_16px_32px_rgba(11,31,74,0.12)] transition-opacity duration-200 lg:top-[calc(100%-2px)] ${
          feat === "core" ? "opacity-100" : "opacity-0"
        }`}
      >
        AI analyzes signals and surfaces explainable risk insights.
      </span>
    </div>
  );
}

function MobileRail({ reduce, feat, id }) {
  const on = Boolean(feat);
  return (
    <svg className="pointer-events-none mx-auto h-12 w-8 md:hidden" viewBox="0 0 32 48" fill="none" aria-hidden>
      <path id={id} d="M16 4 C 16 16, 16 32, 16 44" className={`sol-path ${on ? "is-on" : ""}`} />
      {!reduce && (
        <circle r="2.6" className={`sol-dot ${on ? "is-on" : ""}`}>
          <animateMotion dur={on ? "1.6s" : "4s"} repeatCount="indefinite">
            <mpath href={`#${id}`} />
          </animateMotion>
        </circle>
      )}
    </svg>
  );
}
