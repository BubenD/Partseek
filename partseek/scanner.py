# Partseek — part number search for PDF and CSV files.
# Copyright (C) 2026 ETS - Expand Technology Solutions.
# Licensed under the GNU AGPL-3.0-or-later. See the LICENSE file for details.

"""Walks a folder tree and searches PDF / CSV files for part numbers."""
from __future__ import annotations

import csv
import fnmatch
import io
import os
from dataclasses import dataclass, field
from typing import Iterator

import pymupdf as fitz

from .matcher import Match, Matcher, snippet

FILE_TYPES = {"PDF": (".pdf",), "CSV": (".csv",)}
CSV_CELL_SEP = " | "


@dataclass
class Hit:
    path: str
    kind: str  # "PDF" or "CSV"
    location: int  # 1-based page (PDF) or row (CSV)
    matched: str
    before: str
    after: str
    exact: bool
    column: str = ""
    column_index: int = -1

    @property
    def context(self) -> str:
        return f"{self.before}{self.matched}{self.after}"

    @property
    def location_label(self) -> str:
        if self.kind == "PDF":
            return f"Page {self.location}"
        return f"Row {self.location}" + (f" · {self.column}" if self.column else "")


@dataclass
class FileResult:
    path: str
    kind: str
    hits: list[Hit] = field(default_factory=list)
    error: str | None = None
    no_text: bool = False  # PDF without a text layer (scanned image)
    # Drawings with the same name next to a PDF, e.g. {"DWG": path, "DXF": path}
    drawings: dict[str, str] = field(default_factory=dict)


DRAWING_TYPES = ("DWG", "DXF")


def find_drawings(path: str) -> dict[str, str]:
    """Return the .dwg / .dxf files with the same base name in the same folder."""
    folder, name = os.path.split(path)
    stem = os.path.splitext(name)[0].lower()
    try:
        names = os.listdir(folder or ".")
    except OSError:
        return {}
    found: dict[str, str] = {}
    for other in sorted(names, key=str.lower):
        base, ext = os.path.splitext(other)
        kind = ext[1:].upper()
        if kind in DRAWING_TYPES and kind not in found and base.lower() == stem:
            found[kind] = os.path.join(folder, other)
    return {k: found[k] for k in DRAWING_TYPES if k in found}


def _name_patterns(name_filter: str) -> list[str]:
    patterns = []
    for p in name_filter.replace(",", ";").split(";"):
        p = p.strip().lower()
        if not p:
            continue
        if not any(c in p for c in "*?["):
            p = f"*{p}*"
        patterns.append(p)
    return patterns or ["*"]


def iter_files(root: str, kinds: list[str], name_filter: str = "") -> Iterator[str]:
    """Yield matching files under root, recursing into all subfolders."""
    exts = tuple(ext for k in kinds for ext in FILE_TYPES[k])
    if not exts:
        return
    patterns = _name_patterns(name_filter)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort(key=str.lower)
        for name in sorted(filenames, key=str.lower):
            low = name.lower()
            if name.startswith("~$") or not low.endswith(exts):
                continue
            if any(fnmatch.fnmatchcase(low, p) for p in patterns):
                yield os.path.join(dirpath, name)


def kind_of(path: str) -> str:
    low = path.lower()
    for kind, exts in FILE_TYPES.items():
        if low.endswith(exts):
            return kind
    raise ValueError(f"Unsupported file type: {path}")


def _make_hit(path: str, kind: str, location: int, text: str, m: Match, **extra) -> Hit:
    before, matched, after = snippet(text, m.start, m.end)
    return Hit(path, kind, location, matched, before, after, m.exact, **extra)


def search_pdf(path: str, matcher: Matcher) -> FileResult:
    result = FileResult(path, "PDF")
    with fitz.open(path) as doc:
        if doc.needs_pass:
            result.error = "Password protected"
            return result
        has_text = False
        for index, page in enumerate(doc):
            text = page.get_text("text")
            if text.strip():
                has_text = True
            for m in matcher.find(text):
                result.hits.append(_make_hit(path, "PDF", index + 1, text, m))
        result.no_text = doc.page_count > 0 and not has_text
    return result


def read_csv_rows(path: str) -> list[list[str]]:
    with open(path, "rb") as f:
        raw = f.read()
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    try:
        dialect = csv.Sniffer().sniff(text[:16384], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    return list(csv.reader(io.StringIO(text, newline=""), dialect))


def column_name(header: list[str], index: int) -> str:
    if index < len(header) and header[index].strip():
        return header[index].strip()
    return f"Col {index + 1}"


def search_csv(path: str, matcher: Matcher) -> FileResult:
    result = FileResult(path, "CSV")
    rows = read_csv_rows(path)
    header = rows[0] if rows else []
    for r, row in enumerate(rows):
        offset = 0
        joined = CSV_CELL_SEP.join(row)
        for c, cell in enumerate(row):
            for m in matcher.find(cell):
                # Show the whole row as context, with this cell's match marked
                shifted = Match(m.start + offset, m.end + offset, m.text, m.exact)
                result.hits.append(
                    _make_hit(path, "CSV", r + 1, joined, shifted,
                              column=column_name(header, c) if r > 0 else "",
                              column_index=c)
                )
            offset += len(cell) + len(CSV_CELL_SEP)
    return result


def search_file(path: str, matcher: Matcher) -> FileResult:
    kind = kind_of(path)
    try:
        result = search_pdf(path, matcher) if kind == "PDF" else search_csv(path, matcher)
    except Exception as exc:  # corrupt / locked files must not stop the scan
        return FileResult(path, kind, error=f"{type(exc).__name__}: {exc}")
    if kind == "PDF" and result.hits:
        result.drawings = find_drawings(path)
    return result
