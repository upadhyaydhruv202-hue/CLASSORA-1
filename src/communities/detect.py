"""Duplicate / related community detection. Flags for admin review; never auto-deletes."""

from __future__ import annotations

import re

from src.communities import policy as P

NOISE = frozenset({
    "club", "community", "group", "lovers", "fans", "the", "a", "an", "of", "and",
    "team", "society", "association", "circle", "students", "student", "official",
})

SPECIALIZERS = frozenset({
    "analytics", "research", "workshop", "beginner", "advanced", "women",
    "indoor", "outdoor", "theory", "lab", "interview",
})

ALIASES = {
    "ai": "artificial intelligence",
    "ml": "machine learning",
    "cp": "competitive programming",
    "dsa": "data structures",
    "webdev": "web development",
    "appdev": "app development",
    "cyber": "cybersecurity",
    "cyber security": "cybersecurity",
    "football": "football",
    "soccer": "football",
    "garba": "garba",
    "navratri": "navratri",
}


def _expand(text):
    blob = f" {str(text or '').lower()} "
    for alias, canon in ALIASES.items():
        blob = re.sub(rf"\b{re.escape(alias)}\b", f" {canon} ", blob)
    return blob


def normalize_name(name):
    tokens = [tok for tok in re.findall(r"[a-z0-9]+", _expand(name)) if tok not in NOISE and len(tok) > 1]
    return " ".join(tokens), set(tokens)


def token_set(*parts):
    found = set()
    for part in parts:
        _, tokens = normalize_name(part)
        found |= tokens
    return found


def similarity(name, other_name, description="", other_description="", same_category=True):
    left, left_tokens = normalize_name(name)
    right, right_tokens = normalize_name(other_name)
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    if not left_tokens or not right_tokens:
        return 0.0
    overlap = left_tokens & right_tokens
    union = left_tokens | right_tokens
    score = len(overlap) / len(union)
    extra = (left_tokens - right_tokens) | (right_tokens - left_tokens)
    specialized = bool(extra & SPECIALIZERS)
    if left_tokens <= right_tokens or right_tokens <= left_tokens:
        score = 0.62 if specialized else max(score, 0.94)
    desc_left = token_set(description)
    desc_right = token_set(other_description)
    if desc_left and desc_right:
        score += 0.12 * (len(desc_left & desc_right) / len(desc_left | desc_right))
    if not same_category:
        score -= 0.12
    return max(0.0, min(1.0, round(score, 3)))


def classify_match(score, settings=None):
    cfg = P.normalize_settings(settings)
    if score >= cfg["near_duplicate"]:
        return "NEAR_DUPLICATE"
    if score >= cfg["potential_duplicate"]:
        return "POTENTIAL_DUPLICATE"
    return ""


def find_matches(name, category_code, description, communities, settings=None):
    matches = []
    for row in communities or []:
        if str(row.get("status") or "") not in P.VISIBLE_STATUSES:
            continue
        same = str(row.get("category_code") or row.get("categoryCode") or "").upper() == str(category_code or "").upper()
        score = similarity(
            name,
            row.get("name") or "",
            description=description,
            other_description=row.get("description") or "",
            same_category=same,
        )
        flag = classify_match(score, settings)
        if not flag:
            continue
        matches.append({
            "id": row.get("id"),
            "name": row.get("name"),
            "category": row.get("category_name") or row.get("category") or "",
            "categoryCode": row.get("category_code") or row.get("categoryCode") or "",
            "description": (row.get("description") or "")[:180],
            "score": score,
            "flag": flag,
            "slug": row.get("slug") or "",
        })
    matches.sort(key=lambda item: (-item["score"], item["name"] or ""))
    return matches[:8]
