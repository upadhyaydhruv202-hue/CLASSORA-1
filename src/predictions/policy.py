"""Prediction policy: modes, weights, confidence, disclaimers, document types.

Predictions are pattern-based planning aids. They are never guarantees.
"""

from __future__ import annotations

INSTITUTION_ID = "default"
ANALYSIS_VERSION = "predict-intel-v1.0"

STATUSES = ("UPLOADED", "PROCESSING", "EXTRACTING", "ANALYZING", "INDEXING", "READY", "FAILED", "DELETED")
READY_STATUS = "READY"
FAILED_STATUS = "FAILED"

DOCUMENT_TYPES = (
    "PYQ",
    "NOTES",
    "ASSIGNMENT",
    "PRACTICAL",
    "SYLLABUS",
    "QUESTION_BANK",
    "EXAM_SCHEDULE",
    "ACADEMIC_CALENDAR",
    "INTERNSHIP",
    "JOB",
    "HACKATHON",
    "INTERVIEW",
    "PLACEMENT",
    "RESUME",
    "OTHER",
    "UNKNOWN",
)

ACADEMIC_TYPES = frozenset({
    "PYQ", "NOTES", "ASSIGNMENT", "PRACTICAL", "SYLLABUS", "QUESTION_BANK",
    "EXAM_SCHEDULE", "ACADEMIC_CALENDAR",
})
CAREER_TYPES = frozenset({
    "INTERNSHIP", "JOB", "HACKATHON", "INTERVIEW", "PLACEMENT", "RESUME",
})
INSTITUTIONAL_TYPES = frozenset({"EXAM_SCHEDULE", "ACADEMIC_CALENDAR"})

DOMAINS = ("ACADEMIC", "CAREER", "INSTITUTIONAL")
VISIBILITIES = ("PRIVATE", "INSTITUTION")

SOURCE_RELIABILITY = ("HIGH", "MEDIUM", "LOWER")
RELIABILITY_RANK = {"HIGH": 3, "MEDIUM": 2, "LOWER": 1}

CONFIDENCE_LEVELS = ("VERY_LOW", "LOW", "MODERATE", "HIGH", "VERY_HIGH")
PRIORITIES = ("EXCLUDED", "LOWER", "LOW", "MEDIUM", "HIGH", "VERY_HIGH")

KINDS = ("PREDICTED", "OBSERVED", "OFFICIAL", "GENERATED", "RECOMMENDED", "ESTIMATED")
DATE_STATUSES = ("OFFICIAL", "PREDICTED", "ESTIMATED", "INSUFFICIENT", "SUPERSEDED")

MODES = (
    "GENERAL",
    "STUDENT",
    "EXAM",
    "PASS_FOCUSED",
    "HIGH_SCORE",
    "HACKATHON",
    "INTERNSHIP",
    "PLACEMENT",
    "INTERVIEW",
    "CAREER",
)

ALLOWED_EXTENSIONS = frozenset({".txt", ".md", ".csv", ".json", ".pdf", ".docx"})
REJECTED_EXTENSIONS = frozenset({
    ".exe", ".bat", ".cmd", ".ps1", ".js", ".mjs", ".html", ".htm", ".php",
    ".py", ".sh", ".dll", ".so", ".bin", ".com", ".scr", ".vbs",
})
IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp", ".tif", ".tiff", ".bmp"})

MAX_UPLOAD_BYTES = 2_000_000
MAX_TEXT_CHARS = 200_000
SNIPPET_CHARS = 220

DEFAULT_WEIGHTS = {
    "frequency": 0.28,
    "recency": 0.12,
    "syllabus": 0.18,
    "notes": 0.12,
    "assignment": 0.12,
    "practical": 0.08,
    "marks": 0.10,
}

DEFAULT_SETTINGS = {
    "enabled": True,
    "current_academic_year": "2026",
    "min_pyq_years": 2,
    "min_schedule_years": 2,
    "min_career_docs": 5,
    "min_stipend_samples": 5,
    "min_hackathon_docs": 3,
    "similarity_threshold": 0.48,
    "weights": dict(DEFAULT_WEIGHTS),
    "max_upload_bytes": MAX_UPLOAD_BYTES,
    "max_text_chars": MAX_TEXT_CHARS,
}

DISCLAIMER = (
    "This is a pattern-based prediction and does not guarantee examination appearance, "
    "selection, stipend, or any outcome. Official notices override historical estimates."
)

PASS_DISCLAIMER = (
    "This is a risk-based study strategy and does not guarantee passing. "
    "Do not ignore the rest of the current syllabus."
)

DATE_DISCLAIMER = (
    "This is not an official examination schedule. Official university or college notices override this estimate."
)

STIPEND_DISCLAIMER = (
    "Observed stipend figures come only from uploaded records. They do not guarantee any offer amount."
)

CAREER_DISCLAIMER = (
    "Selection processes vary by organization. Company-specific evidence is separated from general industry patterns."
)

HACKATHON_DISCLAIMER = (
    "Hackathon rounds and judging criteria are taken only from the uploaded materials. They are not universal."
)

DECISION_DISCLAIMER = (
    "CLASSORA provides information, patterns, and recommendations. The final decision belongs to the student."
)

INSUFFICIENT_PYQ = "Insufficient historical data for reliable repetition analysis."
INSUFFICIENT_DATES = "Historical data is insufficient for meaningful exam-date pattern prediction."
INSUFFICIENT_CAREER = "Insufficient uploaded career records for a reliable pattern."
INSUFFICIENT_STIPEND = "Insufficient numeric stipend records. No range is estimated."
INSUFFICIENT_GENERIC = "Insufficient data."

INJECTION_MARKERS = (
    "ignore all previous instructions",
    "ignore previous instructions",
    "disregard previous",
    "reveal the database",
    "you are now",
    "system prompt",
    "override system",
    "jailbreak",
)

RELIABILITY_BY_TYPE = {
    "SYLLABUS": "HIGH",
    "EXAM_SCHEDULE": "HIGH",
    "ACADEMIC_CALENDAR": "HIGH",
    "PYQ": "MEDIUM",
    "NOTES": "MEDIUM",
    "ASSIGNMENT": "MEDIUM",
    "PRACTICAL": "MEDIUM",
    "QUESTION_BANK": "MEDIUM",
    "JOB": "MEDIUM",
    "INTERNSHIP": "MEDIUM",
    "HACKATHON": "MEDIUM",
    "RESUME": "MEDIUM",
    "INTERVIEW": "LOWER",
    "PLACEMENT": "LOWER",
    "OTHER": "LOWER",
    "UNKNOWN": "LOWER",
}


def normalize_settings(raw=None):
    cfg = {
        "enabled": True,
        "current_academic_year": "2026",
        "min_pyq_years": 2,
        "min_schedule_years": 2,
        "min_career_docs": 5,
        "min_stipend_samples": 5,
        "min_hackathon_docs": 3,
        "similarity_threshold": 0.48,
        "weights": dict(DEFAULT_WEIGHTS),
        "max_upload_bytes": MAX_UPLOAD_BYTES,
        "max_text_chars": MAX_TEXT_CHARS,
    }
    if isinstance(raw, dict):
        for key, value in raw.items():
            if key == "weights" and isinstance(value, dict):
                weights = dict(DEFAULT_WEIGHTS)
                for wkey, wval in value.items():
                    if wkey in weights:
                        try:
                            weights[wkey] = max(0.0, float(wval))
                        except (TypeError, ValueError):
                            continue
                total = sum(weights.values()) or 1.0
                cfg["weights"] = {k: v / total for k, v in weights.items()}
                continue
            if key not in cfg or value is None or value == "":
                continue
            if isinstance(cfg[key], bool):
                cfg[key] = bool(value)
            elif isinstance(cfg[key], int):
                try:
                    cfg[key] = max(1, int(value))
                except (TypeError, ValueError):
                    continue
            elif isinstance(cfg[key], float):
                try:
                    cfg[key] = float(value)
                except (TypeError, ValueError):
                    continue
            else:
                cfg[key] = str(value)
    cfg["min_pyq_years"] = max(2, int(cfg["min_pyq_years"]))
    cfg["min_schedule_years"] = max(2, int(cfg["min_schedule_years"]))
    cfg["similarity_threshold"] = min(0.95, max(0.2, float(cfg["similarity_threshold"])))
    return cfg


def normalize_type(value):
    text = str(value or "").strip().upper().replace(" ", "_").replace("-", "_")
    aliases = {
        "PREVIOUS_YEAR_QUESTION": "PYQ",
        "PREVIOUS_YEAR_QUESTIONS": "PYQ",
        "QUESTIONPAPER": "PYQ",
        "QUESTION_PAPER": "PYQ",
        "NOTE": "NOTES",
        "STUDY_MATERIAL": "NOTES",
        "LAB": "PRACTICAL",
        "LAB_MANUAL": "PRACTICAL",
        "CALENDAR": "ACADEMIC_CALENDAR",
        "SCHEDULE": "EXAM_SCHEDULE",
        "TIMETABLE": "EXAM_SCHEDULE",
        "TIME_TABLE": "EXAM_SCHEDULE",
        "JD": "JOB",
        "JOB_DESCRIPTION": "JOB",
        "INTERNSHIP_DESCRIPTION": "INTERNSHIP",
        "INTERVIEW_EXPERIENCE": "INTERVIEW",
        "PLACEMENT_EXPERIENCE": "PLACEMENT",
        "CV": "RESUME",
        "CURRICULUM_VITAE": "RESUME",
    }
    text = aliases.get(text, text)
    if text in DOCUMENT_TYPES:
        return text
    return "UNKNOWN"


def normalize_mode(value):
    text = str(value or "GENERAL").strip().upper().replace(" ", "_").replace("-", "_")
    aliases = {
        "PASS": "PASS_FOCUSED",
        "JUST_PASS": "PASS_FOCUSED",
        "MINIMUM": "PASS_FOCUSED",
        "HIGH_MARKS": "HIGH_SCORE",
        "TOPPER": "HIGH_SCORE",
        "CAREER_EXPLORATION": "CAREER",
        "PLACEMENTS": "PLACEMENT",
        "INTERNSHIPS": "INTERNSHIP",
        "HACKATHONS": "HACKATHON",
    }
    text = aliases.get(text, text)
    return text if text in MODES else "GENERAL"


def normalize_domain(value):
    text = str(value or "").strip().upper()
    if text in DOMAINS:
        return text
    return ""


def domain_for_type(doc_type):
    code = normalize_type(doc_type)
    if code in INSTITUTIONAL_TYPES:
        return "INSTITUTIONAL"
    if code in CAREER_TYPES:
        return "CAREER"
    if code in ACADEMIC_TYPES:
        return "ACADEMIC"
    return "ACADEMIC"


def reliability_for(doc_type, official=False, user_rank=""):
    if official:
        return "HIGH"
    rank = str(user_rank or "").strip().upper()
    if rank in RELIABILITY_RANK:
        return rank
    return RELIABILITY_BY_TYPE.get(normalize_type(doc_type), "LOWER")


def confidence_label(score, cap=None):
    try:
        value = float(score)
    except (TypeError, ValueError):
        value = 0.0
    if value >= 0.88:
        label = "VERY_HIGH"
    elif value >= 0.72:
        label = "HIGH"
    elif value >= 0.52:
        label = "MODERATE"
    elif value >= 0.32:
        label = "LOW"
    else:
        label = "VERY_LOW"
    if cap and cap in CONFIDENCE_LEVELS:
        if CONFIDENCE_LEVELS.index(label) > CONFIDENCE_LEVELS.index(cap):
            return cap
    return label


def priority_label(score, excluded=False):
    if excluded:
        return "EXCLUDED"
    try:
        value = float(score)
    except (TypeError, ValueError):
        value = 0.0
    if value >= 0.80:
        return "VERY_HIGH"
    if value >= 0.65:
        return "HIGH"
    if value >= 0.45:
        return "MEDIUM"
    if value >= 0.25:
        return "LOW"
    return "LOWER"


def looks_like_injection(text):
    blob = str(text or "").lower()
    return any(marker in blob for marker in INJECTION_MARKERS)
