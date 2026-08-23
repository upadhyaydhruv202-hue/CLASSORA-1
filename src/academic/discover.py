"""Controlled discovery of public academic resource URLs from registered sources."""

from __future__ import annotations

import logging
import re
import time
from html import unescape
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urljoin, urlparse, urlunparse
from urllib.request import Request, urlopen

from src.academic import service as academic

log = logging.getLogger("classora.academic")

ALLOWED_HOSTS = {
    "thebrainspot.org",
    "www.thebrainspot.org",
    "ldrp.bhavsarneev.de",
    "www.ldrp.bhavsarneev.de",
    "collegpt.com",
    "www.collegpt.com",
}

# Individual resource URLs may legitimately live on these hosts when linked from a source page.
EXTERNAL_RESOURCE_HOSTS = {
    "drive.google.com",
    "docs.google.com",
    "www.drive.google.com",
    "www.docs.google.com",
}

BRAINSPOT_SKIP = {
    "course", "dashboard", "contact-u", "about-us", "contact", "login",
    "register", "author", "tag", "category", "shop", "cart", "content",
    "2nd-year", "3rd-year", "1st-year", "4th-year", "information-technology",
    "home", "blog",
}

# Semesters published on the LDRP study-material index itself.
LDRP_SUBJECT_SEMESTER = {
    "civil": 1, "es": 1, "engineering graphics": 1, "fop": 1, "mathematics 1": 1, "physics": 1,
    "bcps": 2, "beee": 2, "fme": 2, "mathematics 2": 2, "oopc": 2,
    "dbms": 3, "dsa": 3, "digital electronics": 3, "discrete mathematics": 3, "it workshop": 3,
    "coa": 4, "oopj": 4, "os": 4, "operating systems": 4, "operating system": 4,
    "psnm": 4, "principles of management": 4, "pom": 4, "java": 4,
    "ajp": 5, "advanced java": 5, "computer networks": 5, "daa": 5, "map": 5,
    "optimization techniques": 5, "software engineering": 5, "theory of computation": 5, "toc": 5,
    "android programming": 6, "artificial intelligence": 6, "ai": 6, "ios": 6, "ml": 6,
    "python programming": 6, "python": 6, "soft computing": 6,
    "blockchain": 7, "cd": 7, "cs": 7, "cloud computing": 7, "ds": 7, "hpc": 7,
    "all subject": 7,
}

SUBJECT_ALIASES = {
    "os": ("Operating Systems", "OS"),
    "operating system": ("Operating Systems", "OS"),
    "operating systems": ("Operating Systems", "OS"),
    "dbms": ("DBMS", "DBMS"),
    "database management system": ("DBMS", "DBMS"),
    "database management systems": ("DBMS", "DBMS"),
    "dsa": ("DSA", "DSA"),
    "data structures": ("DSA", "DSA"),
    "coa": ("COA", "COA"),
    "oopj": ("OOPJ", "OOPJ"),
    "java": ("Java", "JAVA"),
    "oopc": ("OOPC", "OOPC"),
    "daa": ("DAA", "DAA"),
    "foa": ("DAA", "DAA"),
    "computer networks": ("Computer Networks", "CN"),
    "dcn": ("Computer Networks", "CN"),
    "software engineering": ("Software Engineering", "SE"),
    "se": ("Software Engineering", "SE"),
    "ai": ("Artificial Intelligence", "AI"),
    "artificial intelligence": ("Artificial Intelligence", "AI"),
    "ml": ("ML", "ML"),
    "python": ("Python", "PYTHON"),
    "python programming": ("Python", "PYTHON"),
    "theory of computation": ("Theory of Computation", "TOC"),
    "flat-toc": ("Theory of Computation", "TOC"),
    "toc": ("Theory of Computation", "TOC"),
    "digital electronics": ("Digital Electronics", "DE"),
    "de": ("Digital Electronics", "DE"),
    "discrete mathematics": ("Discrete Mathematics", "DM"),
    "dm": ("Discrete Mathematics", "DM"),
    "psnm": ("PSNM", "PSNM"),
    "pom": ("Principles of Management", "POM"),
    "principles of management": ("Principles of Management", "POM"),
    "ajava": ("Advanced Java", "AJP"),
    "ajp": ("Advanced Java", "AJP"),
    "advanced java": ("Advanced Java", "AJP"),
    "is": ("Information Security", "IS"),
    "ap": ("Android Programming", "AP"),
    "android programming": ("Android Programming", "AP"),
    "sc": ("Soft Computing", "SC"),
    "soft computing": ("Soft Computing", "SC"),
    "soa": ("SOA", "SOA"),
    "dc": ("Distributed Computing", "DC"),
    "maths-1": ("Mathematics 1", "MATH1"),
    "mathematics 1": ("Mathematics 1", "MATH1"),
    "maths-2": ("Mathematics 2", "MATH2"),
    "mathematics 2": ("Mathematics 2", "MATH2"),
    "fme": ("FME", "FME"),
    "fop": ("FOP", "FOP"),
    "civil": ("Civil", "CIVIL"),
    "beee": ("BEEE", "BEEE"),
    "iict": ("IICT", "IICT"),
    "es": ("ES", "ES"),
    "it workshop": ("IT Workshop", "ITW"),
    "optimization techniques": ("Optimization Techniques", "OT"),
    "map": ("MAP", "MAP"),
    "ios": ("IOS", "IOS"),
    "blockchain": ("Blockchain", "BC"),
    "cloud computing": ("Cloud Computing", "CC"),
    "hpc": ("HPC", "HPC"),
    "cd": ("Compiler Design", "CD"),
    "cs": ("Cyber Security", "CS"),
    "ds": ("Data Science", "DS"),
}


class _LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self._href = ""
        self._text = []
        self.title = ""
        self._in_title = False
        self._in_h1 = False
        self.h1 = ""

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a" and attrs.get("href"):
            self._href = attrs["href"]
            self._text = []
        elif tag == "title":
            self._in_title = True
        elif tag == "h1":
            self._in_h1 = True

    def handle_endtag(self, tag):
        if tag == "a" and self._href:
            self.links.append((self._href, " ".join(self._text).strip()))
            self._href = ""
            self._text = []
        elif tag == "title":
            self._in_title = False
        elif tag == "h1":
            self._in_h1 = False

    def handle_data(self, data):
        text = re.sub(r"\s+", " ", data or "").strip()
        if not text:
            return
        if self._href:
            self._text.append(text)
        if self._in_title:
            self.title += text
        if self._in_h1:
            self.h1 += text


def host_allowed(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host in ALLOWED_HOSTS


def resource_url_allowed(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host in ALLOWED_HOSTS or host in EXTERNAL_RESOURCE_HOSTS


def fetch_html(url: str, timeout=15) -> tuple[str | None, str | None]:
    cleaned, err = academic.normalize_url(url)
    if err or not cleaned or not host_allowed(cleaned):
        return None, err or "URL is outside the approved source domains."
    req = Request(cleaned, headers={"User-Agent": "CLASSORA-AcademicCatalog/1.0 (student resource directory)"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read(2_000_000)
            charset = resp.headers.get_content_charset() or "utf-8"
            return raw.decode(charset, errors="replace"), None
    except HTTPError as exc:
        return None, f"HTTP {exc.code}"
    except URLError as exc:
        return None, str(exc.reason or exc)
    except Exception as exc:
        return None, str(exc)


def parse_page(html: str, base_url: str):
    parser = _LinkParser()
    try:
        parser.feed(html or "")
    except Exception:
        pass
    links = []
    for href, text in parser.links:
        absolute = urljoin(base_url, href)
        if absolute.lower().startswith(("javascript:", "data:", "file:", "mailto:", "tel:")):
            continue
        links.append({"url": absolute, "text": text})
    heading = (parser.h1 or parser.title or "").split("–")[0].split("-")[0].strip()
    return heading, links


def strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def classify_type(title: str, url: str = "") -> str:
    blob = f"{title} {url}".lower()
    if any(token in blob for token in ("pyq", "previous year", "prev year", "end sem paper", "mid sem paper")):
        return "PYQ"
    if "question bank" in blob or "important question" in blob:
        return "QUESTION_BANK"
    if "assignment" in blob:
        return "ASSIGNMENT"
    if any(token in blob for token in ("practical", "lab manual", "lab-")):
        return "PRACTICAL"
    if "syllabus" in blob:
        return "SYLLABUS"
    if any(token in blob for token in ("notes", "lecture", "chapter", "unit ", "material")):
        return "NOTES"
    if urlparse(url).path.lower().endswith(".pdf"):
        return "NOTES"
    if "drive.google.com" in blob or "docs.google.com" in blob:
        return "NOTES"
    return "OTHER"


def normalize_subject(name: str, slug: str = ""):
    for key in (slug.lower().strip("/"), re.sub(r"\s+", " ", name or "").strip().lower()):
        if key in SUBJECT_ALIASES:
            return SUBJECT_ALIASES[key]
    title = re.sub(r"\s+", " ", name or slug.replace("-", " ")).strip() or "Academic Resource"
    return title[:80], (slug or title).upper()[:12]


def map_semester(subject_name: str, year_id: str | None):
    key = re.sub(r"\s+", " ", subject_name or "").strip().lower()
    sem_n = LDRP_SUBJECT_SEMESTER.get(key)
    if not sem_n:
        return None
    semester_id = f"SEM_{sem_n}"
    if year_id and academic.SEMESTER_YEAR.get(semester_id) != year_id:
        return None
    return semester_id


def _pdf_title(text: str, url: str) -> str:
    if text and text.lower() not in {"download", "view", "open", "pdf", "link", "click here", "download material"}:
        return text.strip()[:200]
    name = urlparse(url).path.rsplit("/", 1)[-1]
    name = re.sub(r"\.pdf$", "", name, flags=re.I)
    name = re.sub(r"[-_]+", " ", name).strip()
    return name or "Academic PDF"


def _clean_resource_url(url: str) -> str | None:
    cleaned, err = academic.normalize_url(url)
    if err or not cleaned or not resource_url_allowed(cleaned):
        return None
    # Drop fragments; keep query params (Drive/docs need them).
    parsed = urlparse(cleaned)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", parsed.query, ""))


def _resource_format_for(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    path = urlparse(url).path.lower()
    if path.endswith(".pdf") or "drive.google.com/file" in url.lower():
        return "PDF"
    if "docs.google.com" in host:
        return "DOCUMENT"
    return academic.infer_format(url)


def _extract_named_file_links(html: str, base_url: str):
    """Pair nearby headings with Drive/docs/PDF download links on LDRP chapter pages."""
    found = []
    pattern = re.compile(
        r"<h3[^>]*>(.*?)</h3>.*?<a[^>]+href=[\"']([^\"']+)[\"'][^>]*>\s*(?:Download(?:\s+Material)?|View|Open)?",
        re.I | re.S,
    )
    for title_html, href in pattern.findall(html or ""):
        title = strip_html(title_html)
        absolute = urljoin(base_url, unescape(href.replace("&amp;", "&")))
        cleaned = _clean_resource_url(absolute)
        if not cleaned:
            continue
        if not any(token in cleaned.lower() for token in (".pdf", "drive.google.com", "docs.google.com")):
            continue
        found.append({"title": title or _pdf_title("", cleaned), "url": cleaned})
    if found:
        return found
    # Fallback: any allowed file link on the page.
    _, links = parse_page(html, base_url)
    for row in links:
        cleaned = _clean_resource_url(row["url"])
        if not cleaned:
            continue
        if not any(token in cleaned.lower() for token in (".pdf", "drive.google.com", "docs.google.com")):
            continue
        found.append({"title": _pdf_title(row["text"], cleaned), "url": cleaned})
    return found


def _parse_ldrp_index(html: str, base_url: str):
    """Extract subject cards: name, semester number, subject page URL."""
    cards = []
    # Card blocks contain an h3 subject name, a Sem N label, and a view_material link.
    blocks = re.split(r"<h3[^>]*>", html or "", flags=re.I)
    for block in blocks[1:]:
        name_html, _, rest = block.partition("</h3>")
        name = strip_html(name_html)
        if not name:
            continue
        href_match = re.search(
            r'href=["\']([^"\']*view_material\.php\?[^"\']*subject_id=\d+[^"\']*)["\']',
            rest,
            re.I,
        )
        if not href_match:
            continue
        url = urljoin(base_url, unescape(href_match.group(1).replace("&amp;", "&")))
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        if "subject_id" not in qs:
            continue
        # Prefer curated map; HTML filter chips ("Sem 1 Sem 2 ...") are noisy.
        mapped = LDRP_SUBJECT_SEMESTER.get(name.lower())
        sem_n = mapped
        if not sem_n:
            # Badge-like "Sem N" immediately after the title, not the global filter row.
            window = rest[:500]
            sem_match = re.search(r">\s*Sem(?:ester)?\s*([1-8])\s*<", window, re.I)
            if not sem_match:
                sem_match = re.search(r"\bSem(?:ester)?\s*([1-8])\b\s*(?:View|Explore)?", window, re.I)
            sem_n = int(sem_match.group(1)) if sem_match else None
        cards.append({"name": name, "semester": sem_n, "url": url})
    # Deduplicate by subject_id.
    seen = set()
    out = []
    for card in cards:
        sid = parse_qs(urlparse(card["url"]).query).get("subject_id", [""])[0]
        if sid in seen:
            continue
        seen.add(sid)
        out.append(card)
    return out


class BrainSpotAdapter:
    code_prefix = "brainspot"

    def discover(self, source: dict, pause=0.25):
        start = source.get("website_url") or ""
        year_id = None
        if "2nd-year" in start:
            year_id = "YEAR_2"
        elif "3rd-year" in start:
            year_id = "YEAR_3"
        elif "information-technology" in start:
            year_id = "YEAR_1"
        pages = 0
        discovered = []
        html, err = fetch_html(start)
        pages += 1
        if err:
            return {"ok": False, "error": err, "pages": pages, "resources": []}
        heading, links = parse_page(html, start)
        subject_pages = []
        for item in links:
            parsed = urlparse(item["url"])
            host = (parsed.hostname or "").replace("www.", "")
            if host != "thebrainspot.org":
                continue
            slug = parsed.path.strip("/").split("/")[0].lower()
            if not slug or slug in BRAINSPOT_SKIP:
                continue
            if parsed.path.strip("/").count("/") > 0:
                continue
            subject_pages.append((item["url"].rstrip("/") + "/", slug, item["text"]))
        seen_subjects = set()
        for url, slug, label in subject_pages:
            if url in seen_subjects:
                continue
            seen_subjects.add(url)
            time.sleep(pause)
            page_html, page_err = fetch_html(url)
            pages += 1
            if page_err or not page_html:
                log.info("Brain Spot subject failed %s %s", url, page_err)
                continue
            page_heading, page_links = parse_page(page_html, url)
            subject_name, subject_code = normalize_subject(page_heading or label or slug, slug)
            semester_id = map_semester(subject_name, year_id) or map_semester(subject_code, year_id)
            pdfs = []
            for row in page_links:
                cleaned = _clean_resource_url(row["url"])
                if cleaned and urlparse(cleaned).path.lower().endswith(".pdf") and host_allowed(cleaned):
                    pdfs.append({"url": cleaned, "text": row["text"]})
            if pdfs:
                for row in pdfs:
                    title = _pdf_title(row["text"], row["url"])
                    discovered.append({
                        "title": title,
                        "description": f"{subject_name} material from The Brain Spot.",
                        "year_id": year_id,
                        "semester_id": semester_id,
                        "subject_name": subject_name,
                        "subject_code": subject_code,
                        "type_code": classify_type(title, row["url"]),
                        "original_url": row["url"],
                        "resource_format": "PDF",
                        "status": "AUTO_DISCOVERED" if semester_id else "NEEDS_REVIEW",
                    })
            else:
                discovered.append({
                    "title": f"{subject_name} resources",
                    "description": f"Subject page on The Brain Spot for {subject_name}.",
                    "year_id": year_id,
                    "semester_id": semester_id,
                    "subject_name": subject_name,
                    "subject_code": subject_code,
                    "type_code": "OTHER",
                    "original_url": url,
                    "resource_format": "WEBPAGE",
                    "status": "NEEDS_REVIEW",
                })
        return {"ok": True, "error": "", "pages": pages, "resources": discovered, "heading": heading}


class LdrpAdapter:
    code_prefix = "ldrp"

    def discover(self, source: dict, pause=0.25):
        start = source.get("website_url") or "https://ldrp.bhavsarneev.de/index.php"
        pages = 0
        discovered = []
        html, err = fetch_html(start)
        pages += 1
        if err:
            return {"ok": False, "error": err, "pages": pages, "resources": []}
        cards = _parse_ldrp_index(html, start)
        if not cards:
            return {
                "ok": False,
                "error": "LDRP index did not expose subject cards with view_material links.",
                "pages": pages,
                "resources": [],
            }
        seen_files = set()
        for card in cards:
            subject_name, subject_code = normalize_subject(card["name"])
            sem_n = card.get("semester") or LDRP_SUBJECT_SEMESTER.get(subject_name.lower())
            semester_id = f"SEM_{sem_n}" if sem_n else None
            year_id = academic.SEMESTER_YEAR.get(semester_id) if semester_id else None
            time.sleep(pause)
            page_html, page_err = fetch_html(card["url"])
            pages += 1
            if page_err or not page_html:
                log.info("LDRP subject failed %s %s", card["url"], page_err)
                continue
            _heading, page_links = parse_page(page_html, card["url"])
            chapter_links = []
            for item in page_links:
                if not host_allowed(item["url"]):
                    continue
                qs = parse_qs(urlparse(item["url"]).query)
                if "chapter_id" in qs and "subject_id" in qs:
                    chapter_links.append(item)
            # Deduplicate chapters.
            chapter_seen = set()
            chapters = []
            for item in chapter_links:
                cid = parse_qs(urlparse(item["url"]).query).get("chapter_id", [""])[0]
                if cid in chapter_seen:
                    continue
                chapter_seen.add(cid)
                chapters.append(item)
            if not chapters:
                discovered.append({
                    "title": f"{subject_name} study material",
                    "description": f"LDRP subject page for {subject_name}.",
                    "year_id": year_id,
                    "semester_id": semester_id,
                    "subject_name": subject_name,
                    "subject_code": subject_code,
                    "type_code": "NOTES",
                    "original_url": card["url"],
                    "resource_format": "WEBPAGE",
                    "status": "AUTO_DISCOVERED" if semester_id else "NEEDS_REVIEW",
                })
                continue
            # Bound crawl depth: enough chapters for notes/PYQ without hammering the host.
            for chapter in chapters[:8]:
                time.sleep(pause)
                chapter_html, chapter_err = fetch_html(chapter["url"])
                pages += 1
                if chapter_err or not chapter_html:
                    log.info("LDRP chapter failed %s %s", chapter["url"], chapter_err)
                    continue
                chapter_type = classify_type(chapter["text"] or "", chapter["url"])
                files = _extract_named_file_links(chapter_html, chapter["url"])
                if not files:
                    discovered.append({
                        "title": strip_html(chapter["text"]) or f"{subject_name} chapter",
                        "description": f"{subject_name} chapter on LDRP Study Material.",
                        "year_id": year_id,
                        "semester_id": semester_id,
                        "subject_name": subject_name,
                        "subject_code": subject_code,
                        "type_code": chapter_type,
                        "original_url": chapter["url"],
                        "resource_format": "WEBPAGE",
                        "status": "AUTO_DISCOVERED" if semester_id else "NEEDS_REVIEW",
                    })
                    continue
                for file_row in files:
                    if file_row["url"] in seen_files:
                        continue
                    seen_files.add(file_row["url"])
                    title = file_row["title"]
                    type_code = classify_type(f"{title} {chapter['text']}", file_row["url"])
                    if type_code == "OTHER":
                        type_code = chapter_type if chapter_type != "OTHER" else "NOTES"
                    discovered.append({
                        "title": title,
                        "description": f"{subject_name} material from LDRP Study Material.",
                        "year_id": year_id,
                        "semester_id": semester_id,
                        "subject_name": subject_name,
                        "subject_code": subject_code,
                        "type_code": type_code,
                        "original_url": file_row["url"],
                        "resource_format": _resource_format_for(file_row["url"]),
                        "status": "AUTO_DISCOVERED" if semester_id else "NEEDS_REVIEW",
                    })
        return {"ok": True, "error": "", "pages": pages, "resources": discovered}


class CollegptAdapter:
    code_prefix = "collegpt"

    def discover(self, source: dict, pause=0.35):
        start = source.get("website_url") or "https://www.collegpt.com/courses"
        pages = 0
        html, err = fetch_html(start)
        pages += 1
        if err:
            return {"ok": False, "error": err, "pages": pages, "resources": []}
        heading, links = parse_page(html, start)
        courses = []
        for item in links:
            if not host_allowed(item["url"]):
                continue
            path = urlparse(item["url"]).path.lower()
            if "/course" in path and item["url"].rstrip("/") != start.rstrip("/"):
                courses.append(item)
        if not courses:
            return {
                "ok": False,
                "error": "ColleGPT course links were not exposed in the public HTML (page may be client-rendered). Use manual import.",
                "pages": pages,
                "resources": [],
            }
        discovered = []
        seen = set()
        for item in courses[:30]:
            if item["url"] in seen:
                continue
            seen.add(item["url"])
            title = item["text"] or heading or "ColleGPT course"
            discovered.append({
                "title": title,
                "description": "Public ColleGPT course page.",
                "year_id": None,
                "semester_id": None,
                "subject_name": title,
                "subject_code": "",
                "type_code": "OTHER",
                "original_url": item["url"],
                "resource_format": "WEBPAGE",
                "status": "NEEDS_REVIEW",
            })
        return {"ok": True, "error": "", "pages": pages, "resources": discovered}


ADAPTERS = {
    "brainspot_it": BrainSpotAdapter(),
    "brainspot_y2": BrainSpotAdapter(),
    "brainspot_y3": BrainSpotAdapter(),
    "ldrp_study": LdrpAdapter(),
    "collegpt": CollegptAdapter(),
}


def adapter_for(source: dict):
    code = str(source.get("code") or "")
    if code in ADAPTERS:
        return ADAPTERS[code]
    host = (urlparse(source.get("website_url") or "").hostname or "").replace("www.", "")
    if host == "thebrainspot.org":
        return BrainSpotAdapter()
    if host == "ldrp.bhavsarneev.de":
        return LdrpAdapter()
    if host == "collegpt.com":
        return CollegptAdapter()
    return None
