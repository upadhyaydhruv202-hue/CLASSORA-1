"""Statistical prediction engine. Frequency, recency, overlap, dates, career patterns.

The LLM is not used. Evidence must come from supplied documents. Insufficient
data returns an explicit insufficient status instead of a fabricated ranking.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from statistics import median

from src.predictions import classify as C
from src.predictions import extract as X
from src.predictions import policy as P

GENERIC_WORDS = X.STOP | {"database", "system", "management", "computer", "software", "data"}


def _now():
    return datetime.now(timezone.utc)


def _iso(value=None):
    if value is None:
        return _now().isoformat()
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _int(value, default=None):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _date(value):
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    text = str(value or "")[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def pretty_topic(key, fallback=""):
    if fallback:
        return fallback
    return str(key or "").replace("_", " ").title() or "Unknown topic"


def route_query(question):
    q = str(question or "").strip()
    low = q.lower()
    subject, hits = C.identify_subject(q, "")
    if hits < 1:
        subject = ""
    days = None
    match = re.search(r"\b(\d{1,3})\s*-?\s*day", low)
    if match:
        days = int(match.group(1))
    hours = None
    hmatch = re.search(r"\b(\d{1,2})\s*(?:hours?|hrs?)\b", low)
    if hmatch:
        hours = int(hmatch.group(1))
    mode = "GENERAL"
    intent = "ACADEMIC_PRIORITY"
    if any(w in low for w in ("just pass", "minimum", "only pass", "survive")):
        intent, mode = "PASS_FOCUSED", "PASS_FOCUSED"
    elif any(w in low for w in ("high marks", "high score", "topper", "full marks")):
        intent, mode = "HIGH_SCORE", "HIGH_SCORE"
    elif any(w in low for w in ("when", "exam date", "exam window", "likely to happen", "can my")) and any(
        w in low for w in ("exam", "paper", "schedule", "date")
    ):
        intent = "EXAM_DATE"
    elif any(w in low for w in ("important question", "most important", "which questions", "repeated")):
        intent = "IMPORTANT_QUESTIONS"
    elif any(w in low for w in ("study today", "study first", "prepare first", "what should i study", "start with")):
        intent = "STUDY_FIRST"
    elif any(w in low for w in ("study plan", "preparation plan", "10-day", "make me a")):
        intent = "STUDY_PLAN"
    elif "stipend" in low or "salary" in low:
        intent, mode = "STIPEND", "INTERNSHIP"
    elif any(w in low for w in ("missing", "job requires", "resume", "match")):
        intent, mode = "JOB_MATCH", "PLACEMENT"
    elif any(w in low for w in ("interview", "rounds are common", "this company")):
        intent, mode = "INTERVIEW_ROUNDS", "INTERVIEW"
    elif any(w in low for w in ("hackathon", "final round", "judg")):
        intent, mode = "HACKATHON", "HACKATHON"
    elif any(w in low for w in ("internship", "intern skills")):
        intent, mode = "INTERNSHIP", "INTERNSHIP"
    elif any(w in low for w in ("career path", "what should i become", "which field")):
        intent, mode = "CAREER_PATH", "CAREER"
    elif any(w in low for w in ("skill", "technologies")):
        intent, mode = "SKILL_DEMAND", "PLACEMENT"
    company = ""
    cmatch = re.search(r"\b(?:for|at|company)\s+([A-Z][A-Za-z0-9.&-]{2,})\b", q)
    if cmatch:
        company = cmatch.group(1)
    return {
        "intent": intent,
        "subject": subject if subject != "UNKNOWN" else "",
        "mode": mode,
        "days": days,
        "hours": hours,
        "company": company,
        "question": q,
    }


def confidence_from(*, years=0, docs=0, agreement=0.0, official=False, quality=0.6):
    if official:
        return "HIGH"
    if years < 2 and docs < 2:
        return "VERY_LOW"
    score = 0.0
    score += min(0.35, 0.12 * max(years, 0))
    score += min(0.25, 0.05 * max(docs, 0))
    score += min(0.25, _float(agreement))
    score += min(0.15, _float(quality) * 0.15)
    cap = None
    if years < 2:
        cap = "LOW"
    elif years == 2:
        cap = "MODERATE"
    elif docs < 3:
        cap = "MODERATE"
    return P.confidence_label(score, cap)


def _same_subject(left, right):
    a = str(left or "").strip().upper()
    b = str(right or "").strip().upper()
    if not a or not b or a == "UNKNOWN" or b == "UNKNOWN":
        return True
    return a == b


def visible_docs(docs, subject=""):
    rows = []
    for doc in docs or []:
        if str(doc.get("status") or "") != P.READY_STATUS:
            continue
        if subject and not _same_subject(doc.get("subject"), subject):
            # Institutional calendars may still apply when the subject is unknown on the doc.
            if P.normalize_type(doc.get("document_type") or doc.get("documentType")) not in P.INSTITUTIONAL_TYPES:
                if str(doc.get("subject") or "UNKNOWN").upper() not in {"", "UNKNOWN"}:
                    continue
        rows.append(doc)
    return rows


def corpus_topics(docs, types):
    wanted = {P.normalize_type(t) for t in types}
    found = set()
    for doc in docs or []:
        dtype = P.normalize_type(doc.get("document_type") or doc.get("documentType"))
        if dtype not in wanted:
            continue
        text = doc.get("extracted_text") or doc.get("extractedText") or ""
        for item in C.identify_topics(text):
            found.add(item["topic"])
    return found


def pyq_years(docs, subject=""):
    years = set()
    for doc in visible_docs(docs, subject):
        dtype = P.normalize_type(doc.get("document_type") or doc.get("documentType"))
        if dtype not in {"PYQ", "QUESTION_BANK"}:
            continue
        year = _int(doc.get("year"))
        if year:
            years.add(year)
    return years


def _cluster_unmapped(questions, threshold):
    clusters = []
    for item in questions:
        words = [w for w in X.tokens(item.get("raw")) if w not in GENERIC_WORDS]
        if len(words) < 2:
            clusters.append({"key": item.get("raw", "")[:80], "label": item.get("raw", "")[:120], "items": [item], "mapped": False})
            continue
        placed = False
        for cluster in clusters:
            if cluster.get("mapped"):
                continue
            other = [w for w in X.tokens(cluster["items"][0].get("raw")) if w not in GENERIC_WORDS]
            overlap = set(words) & set(other)
            if len(overlap) < 2:
                continue
            if X.jaccard(words, other) >= threshold:
                cluster["items"].append(item)
                placed = True
                break
        if not placed:
            clusters.append({"key": " ".join(sorted(words)[:6]), "label": item.get("raw", "")[:120], "items": [item], "mapped": False})
    return clusters


def cluster_questions(items, threshold=0.48):
    mapped = defaultdict(list)
    unmapped = []
    for item in items or []:
        key = item.get("topicKey") or C.topic_key_for_question(item.get("raw") or item.get("normalized_text") or "")
        if key:
            mapped[key].append({**item, "topicKey": key})
        else:
            unmapped.append(item)
    clusters = []
    for key, rows in mapped.items():
        clusters.append({
            "key": key,
            "label": pretty_topic(key, rows[0].get("label")),
            "items": rows,
            "mapped": True,
        })
    clusters.extend(_cluster_unmapped(unmapped, threshold))
    return clusters


def _recency(years, all_years):
    if not years or not all_years:
        return 0.0
    latest = max(all_years)
    newest = max(years)
    gap = latest - newest
    return max(0.0, 1.0 - 0.35 * gap)


def _marks_norm(items):
    marks = [row.get("marks") for row in items if row.get("marks")]
    if not marks:
        return 0.4
    return min(1.0, (sum(marks) / len(marks)) / 12.0)


def score_cluster(cluster, meta, weights):
    years = sorted({_int(row.get("year")) for row in cluster["items"] if _int(row.get("year"))})
    all_years = meta.get("pyq_years") or set()
    freq = (len(years) / len(all_years)) if all_years else 0.0
    recency = _recency(years, all_years)
    key = cluster.get("key")
    in_syllabus = key in meta.get("syllabus_topics", set()) if key else False
    in_notes = key in meta.get("notes_topics", set()) if key else False
    in_assign = key in meta.get("assignment_topics", set()) if key else False
    in_prac = key in meta.get("practical_topics", set()) if key else False
    has_syllabus = bool(meta.get("has_syllabus"))
    excluded = bool(has_syllabus and cluster.get("mapped") and not in_syllabus)
    breakdown = {
        "frequency": round(freq, 3),
        "recency": round(recency, 3),
        "syllabus": 1.0 if in_syllabus else 0.0,
        "notes": 1.0 if in_notes else 0.0,
        "assignment": 1.0 if in_assign else 0.0,
        "practical": 1.0 if in_prac else 0.0,
        "marks": round(_marks_norm(cluster["items"]), 3),
    }
    score = 0.0
    for name, weight in (weights or P.DEFAULT_WEIGHTS).items():
        score += float(weight) * float(breakdown.get(name, 0.0))
    if excluded:
        score *= 0.15
    return {
        "score": round(min(1.0, score), 4),
        "breakdown": breakdown,
        "years": years,
        "frequencyLabel": f"{len(years)} / {len(all_years)} years" if all_years else "0 / 0 years",
        "syllabus": in_syllabus if has_syllabus else None,
        "notes": in_notes if meta.get("has_notes") else None,
        "assignment": in_assign if meta.get("has_assignment") else None,
        "practical": in_prac if meta.get("has_practical") else None,
        "excluded": excluded,
        "appearances": len(cluster["items"]),
    }


def _evidence(cluster, limit=6):
    rows = []
    seen = set()
    for item in cluster.get("items") or []:
        doc_id = item.get("documentId") or item.get("document_id")
        key = (doc_id, item.get("raw", "")[:80])
        if key in seen:
            continue
        seen.add(key)
        rows.append({
            "documentId": doc_id,
            "title": item.get("title") or "",
            "year": item.get("year"),
            "snippet": (item.get("raw") or "")[:P.SNIPPET_CHARS],
            "kind": "OBSERVED",
        })
        if len(rows) >= limit:
            break
    return rows


def _why(scored, mode):
    parts = []
    years = scored["years"]
    if years:
        parts.append(f"Appeared in {scored['frequencyLabel']} of analyzed PYQs ({', '.join(str(y) for y in years)}).")
    if scored["syllabus"] is True:
        parts.append("Present in the current syllabus.")
    elif scored["excluded"]:
        parts.append("Not found in the current syllabus, so historical frequency is down-ranked.")
    if scored["notes"] is True:
        parts.append("Present in current notes.")
    if scored["assignment"] is True:
        parts.append("Present in current assignment material.")
    if scored["practical"] is True:
        parts.append("Present in practical material.")
    if mode == "PASS_FOCUSED":
        parts.append("Selected as a high-return topic for a minimum-viable plan.")
    if mode == "HIGH_SCORE":
        parts.append("Kept for breadth and application-level coverage.")
    if not parts:
        parts.append("Selected from the uploaded study materials only.")
    return " ".join(parts)


def _action(label, mode):
    base = f"Prepare definitions, core variations, and one worked example for {label}."
    if mode == "PASS_FOCUSED":
        return f"Cover the fundamentals of {label} first. This does not replace the full syllabus."
    if mode == "HIGH_SCORE":
        return f"Prepare {label} in depth, including application/problem questions where they appear in the source papers."
    return base


def rank_topics(clusters, meta, settings, mode="GENERAL"):
    weights = (settings or {}).get("weights") or P.DEFAULT_WEIGHTS
    ranked = []
    for cluster in clusters:
        scored = score_cluster(cluster, meta, weights)
        priority = P.priority_label(scored["score"], excluded=scored["excluded"])
        confidence = confidence_from(
            years=len(scored["years"]),
            docs=scored["appearances"],
            agreement=scored["breakdown"]["frequency"],
            quality=0.7 if cluster.get("mapped") else 0.45,
        )
        if scored["excluded"]:
            confidence = P.confidence_label(0.4, "LOW")
        ranked.append({
            "topic": cluster["label"],
            "topicKey": cluster["key"],
            "kind": "PREDICTED",
            "priority": priority,
            "confidence": confidence,
            "score": scored["score"],
            "scoreBreakdown": scored["breakdown"],
            "historicalFrequency": scored["frequencyLabel"],
            "yearsAppeared": scored["years"],
            "latestOccurrence": max(scored["years"]) if scored["years"] else None,
            "currentRelevance": {
                "syllabus": scored["syllabus"],
                "notes": scored["notes"],
                "assignment": "HIGH" if scored["assignment"] else ("NONE" if scored["assignment"] is False else None),
                "practical": scored["practical"],
            },
            "excluded": scored["excluded"],
            "why": _why(scored, mode),
            "recommendedAction": _action(cluster["label"], mode),
            "disclaimer": P.DISCLAIMER,
            "evidence": _evidence(cluster),
            "evidenceCount": len(_evidence(cluster, limit=20)),
        })
    ranked.sort(key=lambda row: (row["excluded"], -row["score"], row["topic"]))
    if mode == "PASS_FOCUSED":
        ranked = [row for row in ranked if row["priority"] in {"VERY_HIGH", "HIGH"} and not row["excluded"]]
    return ranked


def build_meta(docs, subject=""):
    rows = visible_docs(docs, subject)
    types = {P.normalize_type(d.get("document_type") or d.get("documentType")) for d in rows}
    return {
        "pyq_years": pyq_years(rows, subject),
        "syllabus_topics": corpus_topics(rows, ("SYLLABUS",)),
        "notes_topics": corpus_topics(rows, ("NOTES",)),
        "assignment_topics": corpus_topics(rows, ("ASSIGNMENT",)),
        "practical_topics": corpus_topics(rows, ("PRACTICAL",)),
        "has_syllabus": "SYLLABUS" in types,
        "has_notes": "NOTES" in types,
        "has_assignment": "ASSIGNMENT" in types,
        "has_practical": "PRACTICAL" in types,
        "types": types,
        "docs": len(rows),
    }


def collect_questions(docs, subject=""):
    items = []
    for doc in visible_docs(docs, subject):
        dtype = P.normalize_type(doc.get("document_type") or doc.get("documentType"))
        if dtype not in {"PYQ", "QUESTION_BANK"}:
            continue
        text = doc.get("extracted_text") or ""
        year = _int(doc.get("year"))
        for q in X.extract_questions(text):
            items.append({
                **q,
                "documentId": doc.get("id"),
                "title": doc.get("title") or doc.get("filename") or "Document",
                "year": year,
                "topicKey": C.topic_key_for_question(q["raw"]),
            })
    return items


def academic_analysis(docs, settings, subject="", mode="GENERAL"):
    cfg = P.normalize_settings(settings)
    mode = P.normalize_mode(mode)
    rows = visible_docs(docs, subject)
    meta = build_meta(rows, subject)
    pyq_docs = [d for d in rows if P.normalize_type(d.get("document_type") or d.get("documentType")) in {"PYQ", "QUESTION_BANK"}]
    years = meta["pyq_years"]
    analyzed_until = _iso()
    data_period = f"{min(years)}–{max(years)}" if years else ""
    if len(years) < cfg["min_pyq_years"]:
        return {
            "kind": "ACADEMIC",
            "subject": subject or "UNKNOWN",
            "status": "INSUFFICIENT",
            "insufficientReason": P.INSUFFICIENT_PYQ,
            "analyzedUntil": analyzed_until,
            "dataPeriod": data_period,
            "disclaimer": P.DISCLAIMER,
            "mode": mode,
            "questions": [],
            "topics": [],
            "studyPriorities": [],
            "pyqYears": sorted(years),
            "documentCount": len(pyq_docs),
            "weights": cfg["weights"],
        }
    clusters = cluster_questions(collect_questions(rows, subject), cfg["similarity_threshold"])
    ranked = rank_topics(clusters, meta, cfg, mode)
    return {
        "kind": "ACADEMIC",
        "subject": subject or "UNKNOWN",
        "status": "READY",
        "insufficientReason": "",
        "analyzedUntil": analyzed_until,
        "dataPeriod": data_period,
        "disclaimer": P.DISCLAIMER if mode != "PASS_FOCUSED" else f"{P.DISCLAIMER} {P.PASS_DISCLAIMER}",
        "mode": mode,
        "questions": [row for row in ranked if not row["excluded"]][:20],
        "topics": ranked[:20],
        "studyPriorities": [row for row in ranked if not row["excluded"]][:12],
        "pyqYears": sorted(years),
        "documentCount": len(pyq_docs),
        "weights": cfg["weights"],
        "decisionNote": P.DECISION_DISCLAIMER,
    }


def _associate_date(doc, parsed):
    text = doc.get("extracted_text") or ""
    nearby = C.nearby_subject(text, parsed["span"]) or ""
    if not nearby:
        fallback = str(doc.get("subject") or "")
        nearby = "" if fallback in {"", "UNKNOWN"} else fallback
    return {
        "date": parsed["date"],
        "year": parsed["year"],
        "raw": parsed["raw"],
        "subject": nearby,
        "documentId": doc.get("id"),
        "title": doc.get("title") or doc.get("filename") or "Schedule",
        "official": bool(doc.get("official")),
        "reliability": doc.get("source_reliability") or doc.get("sourceReliability") or "MEDIUM",
    }


def collect_dates(docs, subject=""):
    items = []
    for doc in docs or []:
        if str(doc.get("status") or "") != P.READY_STATUS:
            continue
        dtype = P.normalize_type(doc.get("document_type") or doc.get("documentType"))
        if dtype not in {"EXAM_SCHEDULE", "ACADEMIC_CALENDAR"} and not doc.get("official"):
            continue
        for parsed in X.parse_dates(doc.get("extracted_text") or ""):
            row = _associate_date(doc, parsed)
            if subject and row["subject"] and not _same_subject(row["subject"], subject):
                continue
            items.append(row)
    return items


def _shift_to_year(iso_date, year):
    dt = _date(iso_date)
    if not dt:
        return None
    try:
        return date(int(year), dt.month, dt.day)
    except ValueError:
        return date(int(year), dt.month, min(dt.day, 28))


def exam_date_prediction(docs, settings, subject="", target_year=None):
    cfg = P.normalize_settings(settings)
    items = collect_dates(docs, subject)
    official = [row for row in items if row.get("official") or row.get("reliability") == "HIGH"]
    current_year = _int(target_year) or _int(cfg.get("current_academic_year")) or _now().year
    official_current = []
    for row in official:
        dt = _date(row["date"])
        if dt and dt.year == current_year:
            official_current.append(row)
    historical = []
    years = set()
    for row in items:
        dt = _date(row["date"])
        if not dt:
            continue
        if dt.year == current_year and (row.get("official") or row.get("reliability") == "HIGH"):
            continue
        historical.append(row)
        years.add(dt.year)
    analyzed_until = _iso()
    if official_current:
        dates = sorted({row["date"] for row in official_current})
        return {
            "kind": "EXAM_DATE",
            "status": "OFFICIAL",
            "subject": subject or "UNKNOWN",
            "official": {
                "dates": dates,
                "windowStart": dates[0],
                "windowEnd": dates[-1],
                "source": official_current[0]["title"],
            },
            "predicted": None,
            "superseded": True,
            "confidence": "HIGH",
            "historical": historical,
            "yearsAnalyzed": sorted(years),
            "why": "An official schedule is available and overrides historical window estimates.",
            "disclaimer": P.DATE_DISCLAIMER,
            "analyzedUntil": analyzed_until,
            "evidence": [
                {"documentId": row["documentId"], "title": row["title"], "snippet": row["raw"], "year": row["year"], "kind": "OFFICIAL"}
                for row in official_current[:8]
            ],
        }
    if len(years) < cfg["min_schedule_years"]:
        return {
            "kind": "EXAM_DATE",
            "status": "INSUFFICIENT",
            "subject": subject or "UNKNOWN",
            "official": None,
            "predicted": None,
            "superseded": False,
            "confidence": "VERY_LOW",
            "historical": historical,
            "yearsAnalyzed": sorted(years),
            "why": P.INSUFFICIENT_DATES,
            "disclaimer": P.DATE_DISCLAIMER,
            "analyzedUntil": analyzed_until,
            "insufficientReason": P.INSUFFICIENT_DATES,
            "evidence": [
                {"documentId": row["documentId"], "title": row["title"], "snippet": row["raw"], "year": row["year"], "kind": "OBSERVED"}
                for row in historical[:8]
            ],
        }
    doys = []
    shifted = []
    for row in historical:
        dt = _date(row["date"])
        if not dt:
            continue
        doys.append(dt.timetuple().tm_yday)
        shifted.append(_shift_to_year(row["date"], current_year))
    mid = int(median(doys))
    spread = max(3, int(max(doys) - min(doys)) // 2 or 3)
    center = date(current_year, 1, 1) + timedelta(days=mid - 1)
    window_start = center - timedelta(days=spread)
    window_end = center + timedelta(days=spread)
    likely_start = center - timedelta(days=min(2, spread))
    likely_end = center + timedelta(days=min(2, spread))
    agreement = 1.0 - min(0.6, (max(doys) - min(doys)) / 40.0)
    return {
        "kind": "EXAM_DATE",
        "status": "PREDICTED",
        "subject": subject or "UNKNOWN",
        "official": None,
        "predicted": {
            "windowStart": window_start.isoformat(),
            "windowEnd": window_end.isoformat(),
            "mostLikelyStart": likely_start.isoformat(),
            "mostLikelyEnd": likely_end.isoformat(),
            "mostLikely": center.isoformat(),
        },
        "superseded": False,
        "confidence": confidence_from(years=len(years), docs=len(historical), agreement=agreement, quality=0.6),
        "historical": historical,
        "yearsAnalyzed": sorted(years),
        "why": (
            f"The previous {len(years)} analyzed academic schedules show a similar semester-end examination pattern "
            f"({', '.join(str(y) for y in sorted(years))})."
        ),
        "disclaimer": P.DATE_DISCLAIMER,
        "analyzedUntil": analyzed_until,
        "evidence": [
            {"documentId": row["documentId"], "title": row["title"], "snippet": f"{row['raw']} ({row['date']})", "year": row["year"], "kind": "OBSERVED"}
            for row in historical[:10]
        ],
    }


def _percentile(values, pct):
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    idx = int(round((len(ordered) - 1) * pct))
    return ordered[max(0, min(len(ordered) - 1, idx))]


def career_analysis(docs, settings, mode="GENERAL"):
    cfg = P.normalize_settings(settings)
    rows = [d for d in (docs or []) if str(d.get("status")) == P.READY_STATUS]
    career_docs = [
        d for d in rows
        if P.normalize_type(d.get("document_type") or d.get("documentType")) in P.CAREER_TYPES
        or P.domain_for_type(d.get("document_type") or d.get("documentType")) == "CAREER"
    ]
    analyzed_until = _iso()
    if len(career_docs) < cfg["min_career_docs"] and mode not in {"HACKATHON", "INTERNSHIP", "PLACEMENT", "INTERVIEW", "CAREER"}:
        # Still compute from whatever exists, but mark insufficient when below threshold.
        pass
    skills = Counter()
    rounds = Counter()
    stages = Counter()
    factors = Counter()
    eligibility = Counter()
    stipends = []
    evidence = defaultdict(list)
    for doc in career_docs:
        text = doc.get("extracted_text") or ""
        title = doc.get("title") or doc.get("filename") or "Career document"
        for skill in X.extract_skills(text):
            skills[skill] += 1
            if len(evidence[f"skill:{skill}"]) < 3:
                evidence[f"skill:{skill}"].append({"documentId": doc.get("id"), "title": title, "snippet": skill, "kind": "OBSERVED"})
        for item in X.extract_rounds(text):
            rounds[item] += 1
        for item in X.extract_hackathon_stages(text):
            stages[item] += 1
        for item in X.extract_hackathon_factors(text):
            factors[item] += 1
        for item in X.extract_eligibility(text):
            eligibility[item] += 1
        for amount in X.parse_stipends(text):
            stipends.append(amount)
            if len(evidence["stipend"]) < 8:
                evidence["stipend"].append({"documentId": doc.get("id"), "title": title, "snippet": f"₹{amount}", "kind": "OBSERVED"})
    n = len(career_docs)
    insufficient = n < cfg["min_career_docs"]
    skill_rows = []
    for name, count in skills.most_common(15):
        skill_rows.append({
            "label": name,
            "kind": "OBSERVED",
            "count": count,
            "share": round(count / n, 3) if n else 0,
            "confidence": confidence_from(docs=n, years=0, agreement=count / n if n else 0, quality=0.7),
            "evidence": evidence.get(f"skill:{name}", []),
            "disclaimer": P.CAREER_DISCLAIMER,
        })
    stipend = {
        "status": "INSUFFICIENT",
        "observedRange": None,
        "typicalRange": None,
        "n": len(stipends),
        "disclaimer": P.STIPEND_DISCLAIMER,
        "insufficientReason": P.INSUFFICIENT_STIPEND,
        "evidence": evidence.get("stipend", []),
    }
    if len(stipends) >= cfg["min_stipend_samples"]:
        stipend = {
            "status": "ESTIMATED",
            "observedRange": {"min": min(stipends), "max": max(stipends)},
            "typicalRange": {"min": _percentile(stipends, 0.25), "max": _percentile(stipends, 0.75)},
            "n": len(stipends),
            "disclaimer": P.STIPEND_DISCLAIMER,
            "insufficientReason": "",
            "confidence": confidence_from(docs=len(stipends), agreement=0.5, quality=0.55),
            "evidence": evidence.get("stipend", []),
        }
    hackathon_docs = [
        d for d in career_docs
        if P.normalize_type(d.get("document_type") or d.get("documentType")) == "HACKATHON"
    ]
    return {
        "kind": "CAREER",
        "status": "INSUFFICIENT" if insufficient and not skill_rows else "READY",
        "insufficientReason": P.INSUFFICIENT_CAREER if insufficient and not skill_rows else "",
        "documentCount": n,
        "analyzedUntil": analyzed_until,
        "disclaimer": P.CAREER_DISCLAIMER,
        "skills": skill_rows,
        "rounds": [{"label": k, "count": v, "kind": "OBSERVED", "pattern": "GENERAL_INDUSTRY"} for k, v in rounds.most_common(10)],
        "eligibility": [{"label": k, "count": v, "kind": "OBSERVED"} for k, v in eligibility.most_common(10)],
        "stipend": stipend,
        "hackathon": {
            "status": "INSUFFICIENT" if len(hackathon_docs) < cfg["min_hackathon_docs"] and not stages and not factors else "READY",
            "documentCount": len(hackathon_docs),
            "stages": [{"label": k, "count": v, "kind": "OBSERVED"} for k, v in stages.most_common()],
            "factors": [{"label": k, "count": v, "kind": "OBSERVED"} for k, v in factors.most_common()],
            "disclaimer": P.HACKATHON_DISCLAIMER,
            "note": "These factors appear in the uploaded hackathon materials. They are not universal judging criteria.",
        },
        "decisionNote": P.DECISION_DISCLAIMER,
    }


def job_match(resume_text, job_text):
    have = set(X.extract_skills(resume_text))
    need = set(X.extract_skills(job_text))
    if not need and not have:
        return {
            "status": "INSUFFICIENT",
            "insufficientReason": "Upload or paste a job description and a resume/profile with identifiable skills.",
            "matching": [],
            "missing": [],
            "extra": [],
            "recommendedAction": "Add a job description and a resume so matching can use observed skills only.",
            "disclaimer": P.CAREER_DISCLAIMER,
            "kind": "OBSERVED",
        }
    matching = sorted(need & have)
    missing = sorted(need - have)
    extra = sorted(have - need)
    action = "No missing required skills were detected in the uploaded texts."
    if missing:
        action = f"Prioritize {', '.join(missing[:4])} preparation using the job description as the source of required skills."
    return {
        "status": "READY",
        "matching": matching,
        "missing": missing,
        "extra": extra,
        "recommendedAction": action,
        "disclaimer": P.CAREER_DISCLAIMER,
        "kind": "OBSERVED",
        "requiredSource": "JOB_DESCRIPTION",
        "profileSource": "RESUME_OR_PROFILE",
    }


def career_paths(skill_labels):
    have = {str(s).lower() for s in (skill_labels or [])}
    rows = []
    for needles, label in X.CAREER_PATHS:
        overlap = [n for n in needles if n in have or any(n in h for h in have)]
        if not overlap:
            continue
        rows.append({
            "path": label,
            "kind": "RECOMMENDED",
            "matchingSignals": overlap,
            "why": f"Your uploaded profile/skills overlap {label} signals: {', '.join(overlap)}.",
            "disclaimer": "This is one possible pathway from current skills, not a decision about your future.",
        })
    return rows


def study_plan(topics, days=7, hours=3, subjects=None, mode="GENERAL", profile=None):
    days = max(1, min(60, _int(days, 7)))
    hours = max(1, min(12, _int(hours, 3)))
    mode = P.normalize_mode(mode)
    pool = [row for row in (topics or []) if not row.get("excluded")]
    if mode == "PASS_FOCUSED":
        pool = [row for row in pool if row.get("priority") in {"VERY_HIGH", "HIGH"}]
    if not pool:
        return {
            "status": "INSUFFICIENT",
            "insufficientReason": "No ranked topics are available to plan from.",
            "days": [],
            "disclaimer": P.DISCLAIMER,
            "editable": True,
        }
    weak = {str(x).strip().upper() for x in (profile or {}).get("weakAreas") or []}
    strong = {str(x).strip().upper() for x in (profile or {}).get("strongAreas") or []}
    ordered = list(pool)
    if weak or strong:
        def _bias(row):
            key = str(row.get("topic") or "").upper()
            bump = 0
            if any(w and w in key for w in weak):
                bump -= 2
            if any(s and s in key for s in strong):
                bump += 1
            return (bump, -_float(row.get("score")))
        ordered.sort(key=_bias)
    subject_list = [s for s in (subjects or []) if s]
    days_out = []
    for i in range(days):
        topic = ordered[i % len(ordered)]
        subject = subject_list[i % len(subject_list)] if subject_list else topic.get("subject") or ""
        days_out.append({
            "day": i + 1,
            "subject": subject,
            "topic": topic.get("topic"),
            "hours": hours,
            "priority": topic.get("priority"),
            "kind": "RECOMMENDED",
            "focus": topic.get("recommendedAction"),
            "why": topic.get("why"),
        })
    return {
        "status": "READY",
        "days": days_out,
        "mode": mode,
        "editable": True,
        "disclaimer": P.DISCLAIMER if mode != "PASS_FOCUSED" else f"{P.DISCLAIMER} {P.PASS_DISCLAIMER}",
        "note": "You can change this plan. It is a recommendation, not a required timetable.",
    }


def readiness(topics, profile=None):
    rows = [t for t in (topics or []) if not t.get("excluded")]
    if not rows:
        return {
            "status": "INSUFFICIENT",
            "label": "UNKNOWN",
            "why": "No ranked topics are available.",
            "disclaimer": P.DISCLAIMER,
        }
    high = sum(1 for t in rows if t.get("priority") in {"VERY_HIGH", "HIGH"})
    share = high / len(rows)
    attendance = _float((profile or {}).get("attendanceRate"), None) if profile else None
    label = "BUILDING"
    if share >= 0.45:
        label = "FOCUSED"
    if share >= 0.65:
        label = "BROAD"
    why = f"{high} of {len(rows)} ranked topics are high or very high priority from the uploaded corpus."
    if attendance is not None:
        why += f" Recorded attendance for personalization is {attendance:.0f}% (not a prediction of marks)."
    return {
        "status": "READY",
        "label": label,
        "highPriorityShare": round(share, 3),
        "why": why,
        "disclaimer": P.DISCLAIMER,
        "kind": "ESTIMATED",
    }


def today_focus(topics, exam_date=None, unfinished=None):
    rows = [t for t in (topics or []) if not t.get("excluded")]
    if not rows:
        return {
            "status": "INSUFFICIENT",
            "items": [],
            "why": "No ranked topics are available.",
            "disclaimer": P.DISCLAIMER,
        }
    skip = {str(x).strip().upper() for x in (unfinished or [])}
    chosen = [t for t in rows if str(t.get("topic") or "").upper() not in skip][:3] or rows[:3]
    why = "Today's list uses predicted priority from historical PYQs and current study material."
    if exam_date and exam_date.get("predicted"):
        why += f" Estimated exam window: {exam_date['predicted'].get('windowStart')} to {exam_date['predicted'].get('windowEnd')}."
    if exam_date and exam_date.get("official"):
        why += " Official schedule is available and should drive the calendar."
    return {
        "status": "READY",
        "items": chosen,
        "why": why,
        "disclaimer": P.DISCLAIMER,
        "kind": "RECOMMENDED",
    }


def hackathon_prep(career):
    hack = (career or {}).get("hackathon") or {}
    questions = [
        "How does the prototype address the stated problem?",
        "What is technically feasible in the remaining time?",
        "What impact evidence can you show from the uploaded problem context?",
        "How would the design scale if the user base grew?",
        "What would you change after evaluator feedback?",
    ]
    return {
        "status": hack.get("status") or "INSUFFICIENT",
        "stages": hack.get("stages") or [],
        "factors": hack.get("factors") or [],
        "checklists": {
            "demo": ["Run the happy path", "Prepare one fallback screenshot", "Name the stack actually used"],
            "presentation": ["Problem", "Approach", "Demo", "Impact", "Next steps"],
            "qa": questions,
        },
        "questionLabel": "Potential questions",
        "disclaimer": P.HACKATHON_DISCLAIMER,
        "note": "Generated questions are potential prompts, not questions judges will definitely ask.",
    }
