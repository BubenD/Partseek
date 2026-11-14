"""Part-number matching rules.

Exact mode: the P/N must stand on its own, so "ABC-123" matches "ABC-123",
"(ABC-123)" and "ABC-123." but not "XABC-1234" or "ABC-123-01" (a joiner such
as - . / _ followed by a letter/digit continues the part number).
Partial mode: the P/N may appear anywhere, including inside a longer string.
Every match reports whether it was exact, so partial results can be labelled.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

SEPARATOR_CHARS = " \t\r\n-./_"
_SEP_RE = r"[\s\-./_]*"
# Unicode letter or digit (\w without the underscore)
_ALNUM = r"[^\W_]"
_JOINERS = "-./_"
_BOUNDARY_BEFORE = rf"(?<!{_ALNUM})(?<!{_ALNUM}[\-./_])"
_BOUNDARY_AFTER = rf"(?!{_ALNUM})(?![\-./_]{_ALNUM})"


def _glued_before(text: str, i: int) -> bool:
    if i > 0 and text[i - 1].isalnum():
        return True
    return i > 1 and text[i - 1] in _JOINERS and text[i - 2].isalnum()


def _glued_after(text: str, i: int) -> bool:
    if i < len(text) and text[i].isalnum():
        return True
    return i + 1 < len(text) and text[i] in _JOINERS and text[i + 1].isalnum()


@dataclass(frozen=True)
class MatchOptions:
    partial: bool = False
    case_sensitive: bool = False
    ignore_separators: bool = False


@dataclass(frozen=True)
class Match:
    start: int
    end: int
    text: str
    exact: bool


def split_terms(text: str) -> list[str]:
    """Split the P/N entry into unique terms; several P/Ns are separated by ';'."""
    terms: list[str] = []
    for term in re.split(r"[;\n]", text):
        term = term.strip()
        if term and term not in terms:
            terms.append(term)
    return terms


class Matcher:
    def __init__(self, terms: list[str], options: MatchOptions):
        self.options = options
        bodies = {self._body(t) for t in terms}
        bodies.discard("")
        if not bodies:
            raise ValueError("Enter a part number to search for.")
        self.terms = list(terms)
        # Longest first so "ABC-12" does not shadow "ABC-123"
        core = "|".join(sorted(bodies, key=len, reverse=True))
        if not options.partial:
            core = rf"{_BOUNDARY_BEFORE}(?:{core}){_BOUNDARY_AFTER}"
        flags = 0 if options.case_sensitive else re.IGNORECASE
        self._re = re.compile(core, flags)

    def _body(self, term: str) -> str:
        if self.options.ignore_separators:
            chars = [c for c in term if c not in SEPARATOR_CHARS]
            return _SEP_RE.join(re.escape(c) for c in chars)
        return re.escape(term.strip())

    def find(self, text: str) -> list[Match]:
        found = []
        for m in self._re.finditer(text):
            start, end = m.span()
            exact = not _glued_before(text, start) and not _glued_after(text, end)
            found.append(Match(start, end, m.group(), exact))
        return found


def snippet(text: str, start: int, end: int, width: int = 45) -> tuple[str, str, str]:
    """Return (before, match, after) around a match, whitespace collapsed."""
    a = max(0, start - width)
    b = min(len(text), end + width)
    before = " ".join(text[a:start].split())
    after = " ".join(text[end:b].split())
    if text[a:start][-1:].isspace():
        before += " "
    if text[end:b][:1].isspace():
        after = " " + after
    if a > 0:
        before = "…" + before
    if b < len(text):
        after += "…"
    return before, " ".join(text[start:end].split()), after
