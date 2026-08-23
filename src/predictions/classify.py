"""Content-based document classification and subject identification.

Filename is a weak hint only. Missing fields stay UNKNOWN. Nothing is fabricated.
"""

from __future__ import annotations

import re

from src.predictions import extract as X
from src.predictions import policy as P

SUBJECTS = (
    ("dbms", "DBMS", ("database", "normalization", "1nf", "2nf", "3nf", "bcnf", "sql", "er model", "transaction", "concurrency", "indexing", "relational algebra", "acid")),
    ("os", "OS", ("operating system", "process scheduling", "deadlock", "paging", "virtual memory", "semaphore", "cpu scheduling", "file system")),
    ("dsa", "DSA", ("data structure", "linked list", "binary tree", "graph traversal", "sorting", "stack and queue", "complexity", "recursion")),
    ("java", "Java", ("java", "jvm", "servlet", "spring boot", "inheritance in java", "exception handling")),
    ("cn", "CN", ("computer network", "osi model", "tcp", "udp", "ip addressing", "routing", "congestion")),
    ("se", "SE", ("software engineering", "sdlc", "agile", "requirement engineering", "uml")),
    ("python", "Python", ("python", "django", "pandas", "numpy")),
    ("ml", "ML", ("machine learning", "supervised", "unsupervised", "regression", "classification", "neural")),
    ("ai", "AI", ("artificial intelligence", "search algorithm", "knowledge representation")),
    ("web", "Web", ("html", "css", "javascript", "react", "rest api")),
    ("coa", "COA", ("computer organization", "pipeline", "cache memory", "instruction cycle")),
    ("toc", "TOC", ("theory of computation", "finite automata", "regular expression", "turing")),
    ("compiler", "Compiler", ("compiler design", "lexical analysis", "parsing", "intermediate code")),
    ("security", "Security", ("cybersecurity", "cryptography", "authentication", "firewall")),
)

TOPIC_ALIASES = {
    "NORMALIZATION": (
        "normalization", "normalisation", "1nf", "2nf", "3nf", "bcnf", "4nf",
        "functional dependency", "functional dependencies", "normal form", "normal forms",
    ),
    "TRANSACTIONS": (
        "transaction", "transactions", "acid", "concurrency control", "serializability",
        "conflict serializable", "two phase locking", "2pl",
    ),
    "INDEXING": ("indexing", "index", "b+ tree", "b tree", "hash index"),
    "ER_MODEL": ("er model", "e-r model", "entity relationship", "er diagram"),
    "RELATIONAL_ALGEBRA": ("relational algebra", "selection", "projection", "join operation"),
    "SQL": ("sql", "select query", "joins", "nested query", "aggregate function"),
    "DEADLOCK": ("deadlock", "deadlock prevention", "deadlock avoidance", "banker"),
    "SCHEDULING": ("cpu scheduling", "fcfs", "sjf", "round robin", "priority scheduling"),
    "PAGING": ("paging", "page replacement", "virtual memory", "thrashing", "segmentation"),
    "PROCESS": ("process", "thread", "pcb", "context switch", "multithreading"),
    "LINKED_LIST": ("linked list", "singly linked", "doubly linked", "circular list"),
    "TREES": ("binary tree", "bst", "avl", "heap", "tree traversal"),
    "GRAPHS": ("graph", "bfs", "dfs", "shortest path", "dijkstra", "spanning tree"),
    "SORTING": ("sorting", "quick sort", "merge sort", "heap sort", "bubble sort"),
    "OOP": ("inheritance", "polymorphism", "encapsulation", "abstraction", "oops", "oop"),
    "NETWORKS": ("osi", "tcp", "udp", "ip address", "routing", "congestion control"),
}

TYPE_HINTS = {
    "PYQ": ("previous year", "pyq", "end semester exam", "university question paper", "q1.", "q2.", "answer any"),
    "NOTES": ("lecture notes", "unit-1", "unit 1", "handwritten", "class notes", "module 1"),
    "ASSIGNMENT": ("assignment", "submit on", "due date", "homework"),
    "PRACTICAL": ("practical", "lab experiment", "viva", "write a program", "lab manual"),
    "SYLLABUS": ("syllabus", "course outcomes", "teaching scheme", "credit", "unit wise"),
    "QUESTION_BANK": ("question bank", "important questions", "expected questions"),
    "EXAM_SCHEDULE": ("exam schedule", "examination schedule", "examination time", "time table", "timetable", "examination date", "exam date", "seat number"),
    "ACADEMIC_CALENDAR": ("academic calendar", "term start", "diwali vacation", "even semester"),
    "INTERNSHIP": ("internship", "stipend", "intern role", "duration of internship"),
    "JOB": ("job description", "we are hiring", "responsibilities", "job title", "full-time"),
    "HACKATHON": ("hackathon", "judging criteria", "prototype round", "final pitch", "problem statement"),
    "INTERVIEW": ("interview experience", "interviewer asked", "hr round", "technical round"),
    "PLACEMENT": ("campus placement", "on-campus", "off-campus drive", "package"),
    "RESUME": ("education", "projects", "skills", "objective", "curriculum vitae"),
}

TYPE_LABELS = {
    "PYQ": "Previous year questions",
    "NOTES": "Notes",
    "ASSIGNMENT": "Assignment",
    "PRACTICAL": "Practical",
    "SYLLABUS": "Syllabus",
    "QUESTION_BANK": "Question bank",
    "EXAM_SCHEDULE": "Exam schedule",
    "ACADEMIC_CALENDAR": "Academic calendar",
    "INTERNSHIP": "Internship",
    "JOB": "Job description",
    "HACKATHON": "Hackathon",
    "INTERVIEW": "Interview experience",
    "PLACEMENT": "Placement experience",
    "RESUME": "Resume / profile",
    "OTHER": "Other",
    "UNKNOWN": "Unknown",
}


def _score_hints(blob, hints):
    return sum(1 for hint in hints if hint in blob)


def identify_subject(text, filename=""):
    blob = f"{text or ''}\n{filename or ''}".lower()
    best = ("UNKNOWN", 0)
    for key, label, hints in SUBJECTS:
        score = (3 if re.search(rf"\b{re.escape(key)}\b", blob) else 0) + _score_hints(blob, hints)
        if label.lower() in blob:
            score += 2
        if score > best[1]:
            best = (label, score)
    if best[1] < 2:
        return "UNKNOWN", 0
    return best[0], best[1]


def identify_topics(text):
    blob = str(text or "").lower()
    found = []
    for topic, aliases in TOPIC_ALIASES.items():
        hits = [alias for alias in aliases if alias in blob]
        if hits:
            found.append({"topic": topic, "aliases": hits, "label": topic.replace("_", " ").title()})
    return found


def topic_key_for_question(text):
    blob = str(text or "").lower()
    best = ("", 0)
    for topic, aliases in TOPIC_ALIASES.items():
        hits = sum(1 for alias in aliases if alias in blob)
        if hits > best[1]:
            best = (topic, hits)
    return best[0] if best[1] else ""


def classify_type(text, filename="", user_type=""):
    override = P.normalize_type(user_type) if user_type else ""
    if override and override not in {"UNKNOWN", "OTHER"}:
        return override, "USER", 1.0
    blob = str(text or "").lower()
    name = str(filename or "").lower()
    scores = {}
    for code, hints in TYPE_HINTS.items():
        scores[code] = _score_hints(blob, hints)
        scores[code] += 0.4 * _score_hints(name, hints)
    best_code = max(scores, key=scores.get)
    best_score = scores[best_code]
    second = sorted(scores.values(), reverse=True)[1] if len(scores) > 1 else 0
    if best_score < 1:
        return "UNKNOWN", "CONTENT", 0.0
    unique = (best_score - second) >= 0.6
    if best_score < 1.5 and not unique:
        return "UNKNOWN", "CONTENT", 0.3
    confidence = min(1.0, 0.35 + 0.15 * best_score)
    return best_code, "CONTENT", confidence


def classify_document(text, filename="", user_type="", user_subject=""):
    doc_type, type_source, type_conf = classify_type(text, filename, user_type)
    subject = str(user_subject or "").strip().upper()
    subject_source = "USER" if subject and subject != "UNKNOWN" else ""
    subject_conf = 1.0 if subject_source == "USER" else 0.0
    if not subject_source:
        subject, subject_hits = identify_subject(text, filename)
        subject_source = "CONTENT" if subject != "UNKNOWN" else "UNKNOWN"
        subject_conf = min(1.0, subject_hits / 6) if subject != "UNKNOWN" else 0.0
    years = X.parse_years(f"{filename or ''} {text or ''}"[:4000])
    year = years[0] if years else None
    if len(years) > 1:
        # Prefer a year that also appears near the filename or first heading.
        head = f"{filename or ''} {(text or '').splitlines()[0] if text else ''}"
        head_years = X.parse_years(head)
        if head_years:
            year = head_years[0]
    semester = X.parse_semester(f"{filename or ''} {text or ''}"[:2000]) or "UNKNOWN"
    domain = P.domain_for_type(doc_type)
    return {
        "documentType": doc_type,
        "typeSource": type_source,
        "typeConfidence": round(type_conf, 3),
        "subject": subject if subject else "UNKNOWN",
        "subjectSource": subject_source or "UNKNOWN",
        "subjectConfidence": round(subject_conf, 3),
        "year": year,
        "semester": semester if semester else "UNKNOWN",
        "academicYear": str(year) if year else "UNKNOWN",
        "department": "UNKNOWN",
        "course": "UNKNOWN",
        "domain": domain,
        "topics": identify_topics(text),
    }


def nearby_subject(text, span):
    window = X.context_window(text, span, radius=90).lower()
    subject, hits = identify_subject(window, "")
    if hits >= 1 and subject != "UNKNOWN":
        return subject
    return ""
