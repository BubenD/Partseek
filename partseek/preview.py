# Partseek — part number search for PDF and CSV files.
# Copyright (C) 2026 ETS - Expand Technology Solutions.
# Licensed under the GNU AGPL-3.0-or-later. See the LICENSE file for details.

"""Preview panes: rendered PDF pages with highlighted hits, and a CSV table."""
from __future__ import annotations

import os
import subprocess

import pymupdf as fitz
from PySide6.QtCore import QAbstractTableModel, QModelIndex, QPoint, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QFont, QImage, QPainter, QPalette, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QScrollArea, QSpinBox, QTableView, QToolButton,
    QVBoxLayout, QWidget,
)

from .scanner import DRAWING_TYPES, read_csv_rows

HIGHLIGHT_FILL = QColor(255, 220, 0, 140)
HIGHLIGHT_EDGE = QColor(230, 120, 0)
CELL_HIGHLIGHT = QColor(255, 236, 140)


def _tool_button(text: str, tip: str, slot) -> QToolButton:
    b = QToolButton()
    b.setText(text)
    b.setToolTip(tip)
    b.setAutoRaise(True)
    b.clicked.connect(slot)
    return b


def open_externally(path: str) -> None:
    if path and os.path.exists(path):
        os.startfile(path)  # Windows: open with the default application


def show_in_folder(path: str) -> None:
    """Open the containing folder in Windows Explorer with the file selected."""
    if path and os.path.exists(path):
        subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])


class PdfPreview(QWidget):
    ZOOM_STEP = 1.25

    def __init__(self, parent=None):
        super().__init__(parent)
        self.doc: fitz.Document | None = None
        self.path = ""
        self.drawings: dict[str, str] = {}
        self.page_index = 0
        self.terms: list[str] = []
        self.hit_pages: list[int] = []  # 0-based
        self.zoom = 1.0
        self.fit_width = True

        self.title = QLabel()
        self.title.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.page_spin = QSpinBox()
        self.page_spin.setMinimum(1)
        self.page_spin.valueChanged.connect(lambda v: self.go_to(v - 1))
        self.page_total = QLabel("/ 0")
        self.zoom_label = QLabel()

        bar = QHBoxLayout()
        bar.setContentsMargins(0, 0, 0, 0)
        bar.addWidget(_tool_button("◀", "Previous page", lambda: self.go_to(self.page_index - 1)))
        bar.addWidget(self.page_spin)
        bar.addWidget(self.page_total)
        bar.addWidget(_tool_button("▶", "Next page", lambda: self.go_to(self.page_index + 1)))
        bar.addSpacing(12)
        bar.addWidget(_tool_button("⏮ Hit", "Previous page with a hit", lambda: self.jump_hit(-1)))
        bar.addWidget(_tool_button("Hit ⏭", "Next page with a hit", lambda: self.jump_hit(1)))
        bar.addSpacing(12)
        bar.addWidget(_tool_button("−", "Zoom out (Ctrl+wheel)", lambda: self.set_zoom(self.zoom / self.ZOOM_STEP)))
        bar.addWidget(self.zoom_label)
        bar.addWidget(_tool_button("+", "Zoom in (Ctrl+wheel)", lambda: self.set_zoom(self.zoom * self.ZOOM_STEP)))
        bar.addWidget(_tool_button("Fit", "Fit page width", self.set_fit_width))
        bar.addStretch(1)
        self.drawing_btns: dict[str, QToolButton] = {}
        for kind in DRAWING_TYPES:
            b = _tool_button(f"Open {kind}", "", lambda _=False, k=kind: open_externally(self.drawings.get(k, "")))
            b.setStyleSheet("font-weight: bold; color: #1f5fbf")
            b.setVisible(False)
            bar.addWidget(b)
            self.drawing_btns[kind] = b
        bar.addWidget(_tool_button("Open file", "Open in default PDF viewer", lambda: open_externally(self.path)))
        bar.addWidget(_tool_button("Open folder", "Show the file in Windows Explorer", lambda: show_in_folder(self.path)))

        self.canvas = QLabel()
        self.canvas.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.scroll = QScrollArea()
        self.scroll.setWidget(self.canvas)
        self.scroll.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.scroll.setBackgroundRole(QPalette.ColorRole.Dark)
        self.scroll.viewport().installEventFilter(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.title)
        layout.addLayout(bar)
        layout.addWidget(self.scroll, 1)

        self._resize_timer = QTimer(self, singleShot=True, interval=120)
        self._resize_timer.timeout.connect(self.render)

    # --- public -------------------------------------------------------------
    def show_file(self, path: str, page: int, terms: list[str], hit_pages: list[int],
                  drawings: dict[str, str] | None = None) -> None:
        """Show `path` at 1-based `page`, highlighting `terms`. `drawings` are same-name DWG/DXF files."""
        drawings = drawings or {}
        if path != self.path or self.doc is None:
            self.close_doc()
            self.doc = fitz.open(path)
            self.path = path
            self.fit_width = True
            notes = "".join(f'  <span style="color:#1f5fbf"><b>[+{k}: {os.path.basename(p)}]</b></span>'
                            for k, p in drawings.items())
            self.title.setText(f"<b>{os.path.basename(path)}</b> — {os.path.dirname(path)}{notes}")
            self.page_spin.blockSignals(True)
            self.page_spin.setMaximum(max(1, self.doc.page_count))
            self.page_spin.blockSignals(False)
            self.page_total.setText(f"/ {self.doc.page_count}")
        self.drawings = drawings
        for kind, b in self.drawing_btns.items():
            b.setVisible(kind in drawings)
            b.setToolTip(f"Open the {kind} drawing with the same name:\n{drawings[kind]}" if kind in drawings else "")
        self.terms = terms
        self.hit_pages = sorted({p - 1 for p in hit_pages})
        self.go_to(page - 1, force=True)

    def close_doc(self) -> None:
        if self.doc is not None:
            self.doc.close()
        self.doc = None
        self.path = ""
        self.drawings = {}
        for b in self.drawing_btns.values():
            b.setVisible(False)
        self.canvas.clear()

    # --- navigation ---------------------------------------------------------
    def go_to(self, index: int, force: bool = False) -> None:
        if self.doc is None:
            return
        index = max(0, min(index, self.doc.page_count - 1))
        if index == self.page_index and not force:
            return
        self.page_index = index
        self.page_spin.blockSignals(True)
        self.page_spin.setValue(index + 1)
        self.page_spin.blockSignals(False)
        self.render(scroll_to_hit=True)

    def jump_hit(self, direction: int) -> None:
        if direction > 0:
            pages = [p for p in self.hit_pages if p > self.page_index]
            target = pages[0] if pages else None
        else:
            pages = [p for p in self.hit_pages if p < self.page_index]
            target = pages[-1] if pages else None
        if target is not None:
            self.go_to(target)

    def set_zoom(self, zoom: float) -> None:
        self.fit_width = False
        self.zoom = max(0.2, min(zoom, 8.0))
        self.render()

    def set_fit_width(self) -> None:
        self.fit_width = True
        self.render()

    # --- rendering ----------------------------------------------------------
    def _highlight_rects(self, page: fitz.Page) -> list[fitz.Rect]:
        rects: list[fitz.Rect] = []
        for term in self.terms:
            found = page.search_for(term)
            if not found and " " in term:
                # Match spanned a line break: highlight each piece
                for piece in term.split():
                    found.extend(page.search_for(piece))
            rects.extend(found)
        return [r * page.rotation_matrix for r in rects]

    def render(self, scroll_to_hit: bool = False) -> None:
        if self.doc is None:
            return
        page = self.doc[self.page_index]
        if self.fit_width:
            avail = self.scroll.viewport().width() - 24
            self.zoom = max(0.2, avail / max(1.0, page.rect.width))
        self.zoom_label.setText(f"{self.zoom * 100:.0f}%")

        dpr = self.devicePixelRatioF()
        scale = self.zoom * dpr
        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
        img = QImage(pix.samples, pix.width, pix.height, pix.stride,
                     QImage.Format.Format_RGB888).copy()

        rects = self._highlight_rects(page)
        if rects:
            painter = QPainter(img)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Multiply)
            for r in rects:
                painter.fillRect(int(r.x0 * scale) - 2, int(r.y0 * scale) - 2,
                                 int(r.width * scale) + 4, int(r.height * scale) + 4, HIGHLIGHT_FILL)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            painter.setPen(HIGHLIGHT_EDGE)
            for r in rects:
                painter.drawRect(int(r.x0 * scale) - 2, int(r.y0 * scale) - 2,
                                 int(r.width * scale) + 4, int(r.height * scale) + 4)
            painter.end()

        pixmap = QPixmap.fromImage(img)
        pixmap.setDevicePixelRatio(dpr)
        self.canvas.setPixmap(pixmap)
        self.canvas.resize(int(pix.width / dpr), int(pix.height / dpr))

        if scroll_to_hit:
            if rects:
                first = min(rects, key=lambda r: (r.y0, r.x0))
                center = QPoint(int((first.x0 + first.x1) / 2 * self.zoom),
                                int((first.y0 + first.y1) / 2 * self.zoom))
                self.scroll.ensureVisible(center.x(), center.y(), 80, 160)
            else:
                self.scroll.verticalScrollBar().setValue(0)

    # --- events -------------------------------------------------------------
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.fit_width:
            self._resize_timer.start()

    def eventFilter(self, obj, event):
        if obj is self.scroll.viewport() and event.type() == event.Type.Wheel:
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                step = self.ZOOM_STEP if event.angleDelta().y() > 0 else 1 / self.ZOOM_STEP
                self.set_zoom(self.zoom * step)
                return True
        return super().eventFilter(obj, event)


class CsvModel(QAbstractTableModel):
    def __init__(self, rows: list[list[str]], parent=None):
        super().__init__(parent)
        self.rows = rows
        self.columns = max((len(r) for r in rows), default=0)
        self.marked: set[tuple[int, int]] = set()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else self.columns

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        r, c = index.row(), index.column()
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole):
            row = self.rows[r]
            return row[c] if c < len(row) else ""
        if role == Qt.ItemDataRole.BackgroundRole and (r, c) in self.marked:
            return QBrush(CELL_HIGHLIGHT)
        if role == Qt.ItemDataRole.ForegroundRole and (r, c) in self.marked:
            return QBrush(Qt.GlobalColor.black)
        if role == Qt.ItemDataRole.FontRole and r == 0:
            f = QFont()
            f.setBold(True)
            return f
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Vertical:
            return str(section + 1)  # matches "Row N" in the results
        return _excel_column(section)

    def set_marked(self, cells: set[tuple[int, int]]) -> None:
        self.marked = cells
        self.layoutChanged.emit()


def _excel_column(index: int) -> str:
    name = ""
    index += 1
    while index:
        index, rem = divmod(index - 1, 26)
        name = chr(65 + rem) + name
    return name


class CsvPreview(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.path = ""
        self.model: CsvModel | None = None
        self.title = QLabel()
        self.title.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.table = QTableView()
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        self.table.verticalHeader().setDefaultSectionSize(22)

        bar = QHBoxLayout()
        bar.setContentsMargins(0, 0, 0, 0)
        bar.addWidget(self.title, 1)
        bar.addWidget(_tool_button("Open file", "Open in default application", lambda: open_externally(self.path)))
        bar.addWidget(_tool_button("Open folder", "Show the file in Windows Explorer", lambda: show_in_folder(self.path)))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(bar)
        layout.addWidget(self.table, 1)

    def show_file(self, path: str, row: int, column: int, marked: set[tuple[int, int]]) -> None:
        """Show `path`, select 1-based `row` / 0-based `column`, highlight `marked` (0-based cells)."""
        if path != self.path or self.model is None:
            self.model = CsvModel(read_csv_rows(path), self)
            self.table.setModel(self.model)
            self.path = path
            self.title.setText(f"<b>{os.path.basename(path)}</b> — {os.path.dirname(path)}")
            self.table.resizeColumnsToContents()
            for c in range(self.model.columnCount()):
                if self.table.columnWidth(c) > 320:
                    self.table.setColumnWidth(c, 320)
        self.model.set_marked(marked)
        index = self.model.index(row - 1, max(0, column))
        self.table.setCurrentIndex(index)
        self.table.scrollTo(index, QTableView.ScrollHint.PositionAtCenter)
