"""Text extraction, hashing, and structured item mining. No LLM. No OCR."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from datetime import date, datetime

from src.predictions import policy as P

QUESTION_START = re.compile(
    r"^\s*(?:q(?:uestion)?\s*\d+|q\d+|\d{1,2}[\).\:]|\[\s*\d+\s*\]|\(\s*\d+\s*\))\s*[-.:)]*\s*",
    re.I,
)
MARKS_RE = re.compile(r"\[\s*(\d{1,2})\s*(?:marks?|m)?\s*\]|\((\d{1,2})\s*marks?\)", re.I)
YEAR_RE = re.compile(r"\b(20\d{2})\b")
SEM_RE = re.compile(r"\b(?:sem(?:ester)?|sem)\s*[-_ ]?([1-8])\b", re.I)
INR_RE = re.compile(
    r"(?:₹|rs\.?|inr)\s*([0-9]{1,3}(?:,[0-9]{3})+|[0-9]{4,7})(?:\s*(?:-|to|–)\s*(?:₹|rs\.?|inr)?\s*([0-9]{1,3}(?:,[0-9]{3})+|[0-9]{4,7}))?",
    re.I,
)
PLAIN_STIPEND_RE = re.compile(
    r"\b([0-9]{4,6})\s*(?:-|to|–)\s*([0-9]{4,6})\s*(?:/?\s*month|pm|per month)\b",
    re.I,
)
SINGLE_STIPEND_RE = re.compile(
    r"\b([0-9]{4,6})\s*(?:/?\s*month|pm|per month)\b",
    re.I,
)

MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10,
    "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}

DATE_PATTERNS = (
    re.compile(r"\b(\d{1,2})\s+([A-Za-z]{3,9})\s+(\d{4})\b"),
    re.compile(r"\b([A-Za-z]{3,9})\s+(\d{1,2}),?\s+(\d{4})\b"),
    re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b"),
    re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b"),
)

STOP = frozenset({
    "a", "an", "the", "and", "or", "of", "to", "in", "on", "for", "with", "its",
    "is", "are", "was", "were", "be", "by", "as", "at", "from", "this", "that",
    "these", "those", "explain", "describe", "discuss", "define", "write",
    "short", "long", "note", "notes", "question", "briefly", "what", "why",
    "how", "give", "state", "list", "compare", "difference", "between",
    "following", "any", "two", "three", "four", "marks", "unit", "chapter",
    "answer", "detail", "details", "using", "example", "examples", "also",
    "their", "them", "into", "over", "under", "your", "you",
})

SKILLS = (
    ("python", "Python"),
    ("java", "Java"),
    ("javascript", "JavaScript"),
    ("typescript", "TypeScript"),
    ("c++", "C++"),
    ("c#", "C#"),
    ("sql", "SQL"),
    ("mysql", "MySQL"),
    ("postgresql", "PostgreSQL"),
    ("mongodb", "MongoDB"),
    ("react", "React"),
    ("angular", "Angular"),
    ("vue", "Vue"),
    ("node", "Node.js"),
    ("express", "Express"),
    ("rest api", "REST API"),
    ("restful", "REST API"),
    ("django", "Django"),
    ("flask", "Flask"),
    ("fastapi", "FastAPI"),
    ("spring", "Spring"),
    ("git", "Git"),
    ("github", "Git"),
    ("dsa", "DSA"),
    ("data structures", "DSA"),
    ("algorithms", "DSA"),
    ("oops", "OOP"),
    ("oop", "OOP"),
    ("object oriented", "OOP"),
    ("html", "HTML"),
    ("css", "CSS"),
    ("linux", "Linux"),
    ("aws", "AWS"),
    ("azure", "Azure"),
    ("gcp", "GCP"),
    ("docker", "Docker"),
    ("kubernetes", "Kubernetes"),
    ("machine learning", "Machine Learning"),
    ("deep learning", "Deep Learning"),
    ("nlp", "NLP"),
    ("tensorflow", "TensorFlow"),
    ("pytorch", "PyTorch"),
    ("excel", "Excel"),
    ("power bi", "Power BI"),
    ("tableau", "Tableau"),
    ("communication", "Communication"),
    ("system design", "System Design"),
    ("os", "Operating Systems"),
    ("dbms", "DBMS"),
    ("computer networks", "Computer Networks"),
    ("cn", "Computer Networks"),
    ("cybersecurity", "Cybersecurity"),
    ("ui/ux", "UI/UX"),
    ("figma", "Figma"),
    ("android", "Android"),
    ("kotlin", "Kotlin"),
    ("swift", "Swift"),
    ("golang", "Go"),
    ("rust", "Rust"),
    ("hadoop", "Hadoop"),
    ("spark", "Spark"),
    ("kafka", "Kafka"),
    ("redis", "Redis"),
    ("graphql", "GraphQL"),
)

ROUNDS = (
    ("aptitude", "Aptitude"),
    ("online assessment", "Aptitude"),
    ("coding", "Coding"),
    ("dsa round", "Coding"),
    ("technical interview", "Technical interview"),
    ("technical round", "Technical interview"),
    ("machine coding", "Machine coding"),
    ("system design", "System/design discussion"),
    ("hr", "HR"),
    ("behavioral", "HR"),
    ("managerial", "Managerial round"),
    ("project discussion", "Project discussion"),
    ("group discussion", "Group discussion"),
)

HACKATHON_STAGES = (
    ("registration", "Registration"),
    ("abstract submission", "Abstract submission"),
    ("idea screening", "Idea screening"),
    ("prototype", "Prototype round"),
    ("technical evaluation", "Technical evaluation"),
    ("presentation", "Presentation"),
    ("demo", "Demo"),
    ("judging", "Judging"),
    ("final pitch", "Final pitch"),
    ("pitch", "Final pitch"),
)

HACKATHON_FACTORS = (
    ("innovation", "Innovation"),
    ("technical feasibility", "Technical feasibility"),
    ("impact", "Impact"),
    ("scalability", "Scalability"),
    ("ui/ux", "UI/UX"),
    ("prototype quality", "Prototype quality"),
    ("presentation", "Presentation"),
    ("problem understanding", "Problem understanding"),
    ("implementation", "Implementation"),
    ("business potential", "Business potential"),
    ("social impact", "Social impact"),
    ("architecture", "Technical architecture"),
)

ELIGIBILITY = (
    ("cgpa", "CGPA"),
    ("gpa", "CGPA"),
    ("percentage", "Percentage"),
    ("backlog", "Backlogs"),
    ("b.tech", "Degree"),
    ("btech", "Degree"),
    ("be ", "Degree"),
    ("mca", "Degree"),
    ("semester", "Semester"),
    ("remote", "Work mode"),
    ("hybrid", "Work mode"),
    ("onsite", "Work mode"),
    ("wfh", "Work mode"),
)

CAREER_PATHS = (
    (("python", "sql", "machine learning", "pandas", "statistics"), "Data Science"),
    (("python", "tensorflow", "pytorch", "machine learning", "nlp"), "AI/ML"),
    (("react", "javascript", "html", "css", "node"), "UI/UX"),
    (("react", "javascript", "java", "python", "dsa", "git"), "Software Development"),
    (("aws", "docker", "kubernetes", "linux", "ci"), "DevOps"),
    (("aws", "azure", "gcp", "cloud"), "Cloud"),
    (("cybersecurity", "network", "linux"), "Cybersecurity"),
    (("product", "communication", "figma"), "Product"),
    (("research", "paper", "publication"), "Research"),
)


def sha256_text(text):
    return hashlib.sha256(str(text or "").encode("utf-8", errors="ignore")).hexdigest()


def capabilities():
    pdf = False
    docx = False
    try:
        import pypdf  # noqa: F401
        pdf = True
    except Exception:
        pdf = False
    try:
        import docx  # noqa: F401
        docx = True
    except Exception:
        docx = False
    return {
        "pdf": pdf,
        "docx": docx,
        "xlsx": False,
        "ocr": False,
        "llm": False,
        "embeddings": False,
        "urlFetch": False,
        "allowedExtensions": sorted(P.ALLOWED_EXTENSIONS),
    }


def clean_text(text, limit=None):
    raw = str(text or "").replace("\x00", " ")
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")
    raw = re.sub(r"[ \t]+", " ", raw)
    raw = re.sub(r"\n{3,}", "\n\n", raw).strip()
    cap = int(limit or P.MAX_TEXT_CHARS)
    if len(raw) > cap:
        raw = raw[:cap]
    return raw


def tokens(text):
    words = re.findall(r"[a-z0-9+#]+", str(text or "").lower().replace("c++", "cplusplus"))
    return [w for w in words if w not in STOP and len(w) > 1]


def token_set(text):
    return set(tokens(text))


def jaccard(a, b):
    left, right = set(a), set(b)
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _month(name):
    return MONTHS.get(str(name or "").strip().lower())


def _safe_date(year, month, day):
    try:
        return date(int(year), int(month), int(day))
    except (TypeError, ValueError):
        return None


def parse_dates(text):
    found = []
    blob = str(text or "")
    seen = set()
    for match in DATE_PATTERNS[0].finditer(blob):
        month = _month(match.group(2))
        item = _safe_date(match.group(3), month, match.group(1))
        if item and item.isoformat() not in seen:
            seen.add(item.isoformat())
            found.append({"date": item.isoformat(), "year": item.year, "span": match.span(), "raw": match.group(0)})
    for match in DATE_PATTERNS[1].finditer(blob):
        month = _month(match.group(1))
        item = _safe_date(match.group(3), month, match.group(2))
        if item and item.isoformat() not in seen:
            seen.add(item.isoformat())
            found.append({"date": item.isoformat(), "year": item.year, "span": match.span(), "raw": match.group(0)})
    for match in DATE_PATTERNS[2].finditer(blob):
        item = _safe_date(match.group(1), match.group(2), match.group(3))
        if item and item.isoformat() not in seen:
            seen.add(item.isoformat())
            found.append({"date": item.isoformat(), "year": item.year, "span": match.span(), "raw": match.group(0)})
    for match in DATE_PATTERNS[3].finditer(blob):
        day, month, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
        if day > 12:
            item = _safe_date(year, month, day)
        elif month > 12:
            item = _safe_date(year, day, month)
        else:
            item = _safe_date(year, month, day)  # day-first (common on Indian academic notices)
        if item and item.isoformat() not in seen:
            seen.add(item.isoformat())
            found.append({"date": item.isoformat(), "year": item.year, "span": match.span(), "raw": match.group(0)})
    return found


def parse_years(text):
    years = []
    for match in YEAR_RE.finditer(str(text or "")):
        year = int(match.group(1))
        if 2000 <= year <= 2100 and year not in years:
            years.append(year)
    return years


def parse_semester(text):
    match = SEM_RE.search(str(text or ""))
    if not match:
        return ""
    return f"SEM_{match.group(1)}"


def _parse_amount(raw):
    try:
        return int(str(raw).replace(",", ""))
    except (TypeError, ValueError):
        return None


def parse_stipends(text):
    amounts = []
    blob = str(text or "")
    for match in INR_RE.finditer(blob):
        low = _parse_amount(match.group(1))
        high = _parse_amount(match.group(2)) if match.group(2) else low
        if low:
            amounts.append(low)
        if high and high != low:
            amounts.append(high)
    for match in PLAIN_STIPEND_RE.finditer(blob):
        low = _parse_amount(match.group(1))
        high = _parse_amount(match.group(2))
        if low:
            amounts.append(low)
        if high:
            amounts.append(high)
    if not amounts:
        for match in SINGLE_STIPEND_RE.finditer(blob):
            value = _parse_amount(match.group(1))
            if value:
                amounts.append(value)
    return [n for n in amounts if 1000 <= n <= 500000]


def extract_labeled(text, pairs):
    blob = str(text or "").lower()
    found = []
    seen = set()
    for needle, label in pairs:
        if needle in blob and label not in seen:
            seen.add(label)
            found.append(label)
    return found


def extract_skills(text):
    return extract_labeled(text, SKILLS)


def extract_rounds(text):
    return extract_labeled(text, ROUNDS)


def extract_hackathon_stages(text):
    return extract_labeled(text, HACKATHON_STAGES)


def extract_hackathon_factors(text):
    return extract_labeled(text, HACKATHON_FACTORS)


def extract_eligibility(text):
    return extract_labeled(text, ELIGIBILITY)


def question_type(text, marks=None):
    blob = str(text or "").lower()
    if any(w in blob for w in ("program", "code", "implement", "write a function", "algorithm to")):
        return "PROGRAMMING"
    if any(w in blob for w in ("calculate", "compute", "find the", "numerical", "derive")):
        return "NUMERICAL"
    if any(w in blob for w in ("draw", "er diagram", "flowchart", "architecture")):
        return "DIAGRAM"
    if marks is not None and marks <= 4:
        return "SHORT"
    if marks is not None and marks >= 8:
        return "LONG"
    if any(w in blob for w in ("short note", "briefly")):
        return "SHORT"
    return "THEORETICAL"


def extract_questions(text):
    lines = [ln.strip() for ln in str(text or "").splitlines() if ln.strip()]
    questions = []
    buffer = []
    for line in lines:
        if QUESTION_START.match(line) or (buffer and MARKS_RE.search(line) and len(line) < 80):
            if buffer:
                questions.append(" ".join(buffer))
                buffer = []
            cleaned = QUESTION_START.sub("", line).strip()
            if cleaned:
                buffer.append(cleaned)
            continue
        if buffer:
            if len(line) > 220 and not QUESTION_START.match(line):
                questions.append(" ".join(buffer))
                buffer = []
                continue
            buffer.append(line)
            if len(" ".join(buffer)) > 400:
                questions.append(" ".join(buffer))
                buffer = []
    if buffer:
        questions.append(" ".join(buffer))
    if not questions:
        for line in lines:
            low = line.lower()
            if any(k in low for k in ("explain", "describe", "define", "discuss", "write", "what is", "differentiate")):
                if 12 <= len(line) <= 400:
                    questions.append(QUESTION_START.sub("", line).strip())
    out = []
    seen = set()
    for raw in questions:
        text_q = re.sub(r"\s+", " ", raw).strip(" -.:")
        if len(text_q) < 8:
            continue
        key = text_q.lower()
        if key in seen:
            continue
        seen.add(key)
        marks_match = MARKS_RE.search(text_q)
        marks = None
        if marks_match:
            marks = int(marks_match.group(1) or marks_match.group(2))
        out.append({
            "raw": text_q[:500],
            "marks": marks,
            "questionType": question_type(text_q, marks),
        })
    return out[:80]


def _pdf_text(data):
    try:
        from pypdf import PdfReader
    except Exception:
        return "", "PDF extraction is not available on this server. Paste the text or upload a .txt file."
    try:
        reader = PdfReader(io.BytesIO(data))
        parts = []
        for page in reader.pages[:40]:
            parts.append(page.extract_text() or "")
        text = clean_text("\n".join(parts))
        if not text:
            return "", "The PDF contained no extractable text. Scanned pages need OCR, which CLASSORA does not run."
        return text, ""
    except Exception:
        return "", "The PDF could not be read. The file may be corrupted or encrypted."


def _docx_text(data):
    try:
        from docx import Document
    except Exception:
        return "", "DOCX extraction is not available on this server. Paste the text or upload a .txt file."
    try:
        doc = Document(io.BytesIO(data))
        text = clean_text("\n".join(p.text for p in doc.paragraphs))
        if not text:
            return "", "The Word document contained no extractable text."
        return text, ""
    except Exception:
        return "", "The Word document could not be read."


def _csv_text(data):
    try:
        body = data.decode("utf-8-sig", errors="replace")
        reader = csv.reader(io.StringIO(body))
        rows = [" ".join(cell.strip() for cell in row if str(cell).strip()) for row in reader]
        return clean_text("\n".join(r for r in rows if r)), ""
    except Exception:
        return "", "The CSV file could not be read."


def extract_file(filename, data, content_type=""):
    name = str(filename or "upload").strip() or "upload"
    ext = ""
    if "." in name:
        ext = "." + name.rsplit(".", 1)[-1].lower()
    payload = data or b""
    if ext in P.REJECTED_EXTENSIONS:
        return "", f"File type {ext or 'unknown'} is not allowed."
    if ext in P.IMAGE_EXTENSIONS:
        return "", "Image OCR is not available. Paste the text or upload a text/PDF file."
    if ext and ext not in P.ALLOWED_EXTENSIONS:
        return "", f"Unsupported file type {ext}. Use TXT, CSV, MD, JSON, PDF, or DOCX."
    if ext in {".txt", ".md", ".json"} or (not ext and content_type.startswith("text/")):
        if ext == ".json":
            try:
                parsed = json.loads(payload.decode("utf-8", errors="replace"))
                return clean_text(json.dumps(parsed, ensure_ascii=False, indent=2) if not isinstance(parsed, str) else parsed), ""
            except Exception:
                return clean_text(payload.decode("utf-8", errors="replace")), ""
        return clean_text(payload.decode("utf-8", errors="replace")), ""
    if ext == ".csv":
        return _csv_text(payload)
    if ext == ".pdf":
        return _pdf_text(payload)
    if ext == ".docx":
        return _docx_text(payload)
    return "", "Unsupported file type."


def validate_upload(filename, size, content_type="", max_bytes=None):
    name = str(filename or "").strip()
    ext = ("." + name.rsplit(".", 1)[-1].lower()) if "." in name else ""
    limit = int(max_bytes or P.MAX_UPLOAD_BYTES)
    if size is not None and int(size) > limit:
        return f"File is too large. Maximum size is {limit // 1000} KB."
    if ext in P.REJECTED_EXTENSIONS:
        return "This file type is not allowed."
    if ext in P.IMAGE_EXTENSIONS:
        return "Image OCR is not available. Paste the text or upload a text/PDF file."
    if ext and ext not in P.ALLOWED_EXTENSIONS:
        return f"Unsupported file type {ext}."
    return ""


def context_window(text, span, radius=70):
    start, end = span
    lo = max(0, start - radius)
    hi = min(len(text), end + radius)
    return re.sub(r"\s+", " ", text[lo:hi]).strip()
