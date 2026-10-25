"""Deterministic topic handling: the non-AI fallback for every AI call (REQUIREMENTS §9, NFR-3)."""

from __future__ import annotations

import re

from app.domain.catalog import (
    COURSE_ALIASES,
    COURSES,
    DEPARTMENT_SUBJECT,
    DEPARTMENTS,
    GENERAL_SUBJECT,
    KEYWORD_COURSE,
    KEYWORD_SUBJECT,
    Course,
    course_by_number,
)
from app.domain.types import Topic

MAX_KEYWORDS = 10
ICEBREAKER_MAX = 140

_STOPWORDS = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "at",
        "be",
        "but",
        "by",
        "for",
        "from",
        "have",
        "help",
        "hw",
        "i",
        "im",
        "in",
        "is",
        "it",
        "its",
        "me",
        "my",
        "need",
        "of",
        "on",
        "or",
        "so",
        "studying",
        "study",
        "the",
        "this",
        "to",
        "today",
        "with",
        "working",
        "dying",
        "on",
        "exam",
        "prep",
        "review",
        "homework",
    ]
)

# "ch 320m", "CH320M", "c s 314", "cs314", "phy 303k". Department first, then a 3-digit number
# with an optional letter. Longer department spellings are tried first.
_DEPT_PATTERN = "|".join(
    sorted((re.escape(d).replace(r"\ ", r"\s?") for d in DEPARTMENTS), key=len, reverse=True)
)
_COURSE_RE = re.compile(rf"\b({_DEPT_PATTERN})\s*(\d{{3}}[a-z]?)\b", re.IGNORECASE)
_NUMBER_RE = re.compile(r"\b(\d{3}[a-z]?)\b", re.IGNORECASE)
_WORD_RE = re.compile(r"[a-z][a-z0-9]+")


def cache_key(text: str) -> str:
    """Lowercased, whitespace-collapsed: the `topic_cache.text_key`."""
    return " ".join(text.lower().split())


def label_for(course: Course | None, subject: str) -> str:
    if course is not None:
        return f"{course.code} · {course.title}"
    return subject.title() if subject != GENERAL_SUBJECT else "General study"


def keywords_of(text: str) -> tuple[str, ...]:
    seen: dict[str, None] = {}
    for word in _WORD_RE.findall(text.lower()):
        if word not in _STOPWORDS and len(word) >= 3 and not word.isdigit():
            seen.setdefault(word, None)
    return tuple(seen)[:MAX_KEYWORDS]


def _course_from_code(text: str) -> tuple[str | None, Course | None]:
    """Returns (normalized code, catalog course) for the first course code in the text."""
    m = _COURSE_RE.search(text)
    if not m:
        return None, None
    dept = DEPARTMENTS[re.sub(r"\s+", " ", m.group(1).lower())]
    code = f"{dept} {m.group(2).upper()}"
    return code, COURSES.get(code)


def normalize_fallback(text: str) -> Topic:
    """Free text → {course_code, subject, keywords, label} without any network call."""
    key = cache_key(text)
    keywords = keywords_of(key)

    code, course = _course_from_code(key)
    if code is None:
        for phrase in sorted(COURSE_ALIASES, key=len, reverse=True):
            if re.search(rf"\b{re.escape(phrase)}\b", key):
                course = COURSES[COURSE_ALIASES[phrase]]
                code = course.code
                break
    if code is None:
        for word in keywords:
            if word in KEYWORD_COURSE:
                course = COURSES[KEYWORD_COURSE[word]]
                code = course.code
                break
    if code is None:
        for number in _NUMBER_RE.findall(key):
            found = course_by_number(number)
            if found is not None:
                course, code = found, found.code
                break

    if course is not None:
        subject = course.subject
    elif code is not None:
        subject = DEPARTMENT_SUBJECT[code.rsplit(" ", 1)[0]]
    else:
        subject = next(
            (KEYWORD_SUBJECT[w] for w in keywords if w in KEYWORD_SUBJECT), GENERAL_SUBJECT
        )

    label = label_for(course, subject) if course is not None or code is None else code
    return Topic(course_code=code, subject=subject, keywords=keywords, label=label)


def keyword_overlap(a: tuple[str, ...], b: tuple[str, ...]) -> int:
    """Jaccard similarity of two keyword sets, scaled to 0-100 (the FR-30 fallback score)."""
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0
    return round(100 * len(sa & sb) / len(sa | sb))


def icebreaker_fallback(a: Topic, b: Topic) -> str:
    """The template icebreaker (REQUIREMENTS §9), using the most specific shared label."""
    label = a.label if a.course_code and a.course_code == b.course_code else a.subject
    text = f"You're both studying {label}. Start by comparing where you're stuck."
    if len(text) <= ICEBREAKER_MAX:
        return text
    return "You're studying the same thing. Start by comparing where you're stuck."


def card_key_for(subject: str) -> str:
    """Card image key: one pre-generated image per subject, plus `generic` (REQUIREMENTS §9)."""
    known = set(DEPARTMENT_SUBJECT.values())
    return subject.replace(" ", "-") if subject in known else "generic"
