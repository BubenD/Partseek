"""Partseek main window."""
from __future__ import annotations

import csv
import html
import os
import sys
import threading

from PySide6.QtCore import QRectF, QSettings, Qt, QThread, Signal
from PySide6.QtGui import QAction, QColor, QKeySequence, QTextDocument
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QFileDialog, QGroupBox, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox, QProgressBar,
    QPushButton, QSplitter, QStackedWidget, QStyle, QStyledItemDelegate,
    QStyleOptionViewItem, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from . import __version__, __company__, __copyright__, __product__
from .matcher import Matcher, MatchOptions, split_terms
from .preview import CsvPreview, PdfPreview, open_externally, show_in_folder
from .scanner import DRAWING_TYPES, FileResult, Hit, iter_files, search_file

DATA_ROLE = Qt.ItemDataRole.UserRole
HTML_ROLE = Qt.ItemDataRole.UserRole + 1
PARTIAL_COLOR = QColor(200, 110, 0)
ERROR_COLOR = QColor(190, 30, 30)
DRAWING_COLOR = QColor(31, 95, 191)


def _drawing_mark(drawings: dict[str, str]) -> str:
    """'  [+DWG]', '  [+DXF]', '  [+DWG +DXF]' or '' for the files next to a PDF."""
    return f"  [{' '.join('+' + k for k in drawings)}]" if drawings else ""


class SearchWorker(QThread):
    listed = Signal(int)
    progress = Signal(int, int, str)
    fileDone = Signal(object)

    def __init__(self, root: str, kinds: list[str], name_filter: str, matcher: Matcher):
        super().__init__()
        self.root, self.kinds, self.name_filter, self.matcher = root, kinds, name_filter, matcher
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def run(self) -> None:
        files = []
        for path in iter_files(self.root, self.kinds, self.name_filter):
            if self._cancel.is_set():
                return
            files.append(path)
            if len(files) % 200 == 0:
                self.progress.emit(0, 0, f"Listing files… {len(files)}")
        self.listed.emit(len(files))
        for i, path in enumerate(files):
            if self._cancel.is_set():
                return
            self.progress.emit(i, len(files), path)
            self.fileDone.emit(search_file(path, self.matcher))
        self.progress.emit(len(files), len(files), "")


class HtmlDelegate(QStyledItemDelegate):
    """Draws the context column with the matched P/N marked."""

    def paint(self, painter, option, index):
        text = index.data(HTML_ROLE)
        if text is None:
            return super().paint(painter, option, index)
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""
        style = opt.widget.style() if opt.widget else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)
        rect = style.subElementRect(QStyle.SubElement.SE_ItemViewItemText, opt, opt.widget)
        selected = bool(opt.state & QStyle.StateFlag.State_Selected)
        color = opt.palette.highlightedText().color() if selected else opt.palette.text().color()
        doc = QTextDocument()
        doc.setDocumentMargin(0)
        doc.setDefaultFont(opt.font)
        doc.setHtml(f'<span style="white-space:pre; color:{color.name()}">{text}</span>')
        painter.save()
        painter.translate(rect.left() + 2, rect.top() + (rect.height() - doc.size().height()) / 2)
        painter.setClipRect(QRectF(0, 0, rect.width() - 2, rect.height()))
        doc.drawContents(painter)
        painter.restore()


def _context_html(hit: Hit) -> str:
    return (f"{html.escape(hit.before)}"
            f'<span style="background:#ffd84d; color:#000; font-weight:600">{html.escape(hit.matched)}</span>'
            f"{html.escape(hit.after)}")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Partseek {__version__} — part number search")
        self.resize(1400, 850)
        self.settings = QSettings(__company__, "Partseek")
        self.worker: SearchWorker | None = None
        self.results: list[FileResult] = []
        self.issues: list[FileResult] = []
        self.files_scanned = 0
        self.hit_count = 0
        self.root = ""

        self._build_ui()
        self._build_menu()
        self._load_settings()

    # --- Menu / About -------------------------------------------------------
    def _build_menu(self) -> None:
        help_menu = self.menuBar().addMenu("&Help")
        about = QAction("&About Partseek", self)
        about.triggered.connect(self.show_about)
        help_menu.addAction(about)

    def show_about(self) -> None:
        box = QMessageBox(self)
        box.setWindowTitle("About Partseek")
        box.setIconPixmap(
            self.windowIcon().pixmap(64, 64)
            if not self.windowIcon().isNull()
            else QApplication.style()
            .standardIcon(QStyle.StandardPixmap.SP_FileDialogContentsView)
            .pixmap(64, 64)
        )
        box.setTextFormat(Qt.TextFormat.RichText)
        box.setText(
            f"<h3>{__product__} {__version__}</h3>"
            "<p>Search PDF and CSV files for part numbers.</p>"
            f"<p><b>{html.escape(__company__)}</b><br>"
            f"{html.escape(__copyright__)}</p>"
            "<p>This software is proprietary. Unauthorized copying, distribution "
            "or reverse engineering is prohibited.</p>"
        )
        box.exec()

    # --- UI -----------------------------------------------------------------
    def _build_ui(self) -> None:
        self.folder_edit = QLineEdit()
        self.folder_edit.setPlaceholderText("Folder to search (all subfolders are included)")
        browse = QPushButton("Browse…")
        browse.clicked.connect(self.choose_folder)

        self.pn_edit = QLineEdit()
        self.pn_edit.setPlaceholderText("Part number, e.g. LM317T   (several: separate with ;)")
        self.pn_edit.returnPressed.connect(self.start_search)
        f = self.pn_edit.font()
        f.setPointSizeF(f.pointSizeF() * 1.25)
        self.pn_edit.setFont(f)

        self.search_btn = QPushButton("Search")
        self.search_btn.setDefault(True)
        self.search_btn.clicked.connect(self.start_search)
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_search)

        self.pdf_check = QCheckBox("PDF")
        self.csv_check = QCheckBox("CSV")
        self.name_filter_edit = QLineEdit()
        self.name_filter_edit.setPlaceholderText("all files   (e.g. BOM;*rev*)")
        self.name_filter_edit.setToolTip(
            "Only search files whose name matches.\n"
            "Text without wildcards matches anywhere in the name; separate several with ;")
        self.name_filter_edit.returnPressed.connect(self.start_search)

        self.partial_check = QCheckBox("Partial match")
        self.partial_check.setToolTip(
            "Also show hits where the P/N is part of a longer string\n"
            "(e.g. LM317 finds LM317T). Partial hits are shown in orange.")
        self.case_check = QCheckBox("Match case")
        self.sep_check = QCheckBox("Ignore separators")
        self.sep_check.setToolTip("Treat - . / _ and spaces as optional, so 'ABC-123' also finds 'ABC123' and 'ABC 123'")

        grid_top = QHBoxLayout()
        grid_top.addWidget(QLabel("Folder:"))
        grid_top.addWidget(self.folder_edit, 1)
        grid_top.addWidget(browse)

        grid_pn = QHBoxLayout()
        grid_pn.addWidget(QLabel("P/N:"))
        grid_pn.addWidget(self.pn_edit, 1)
        grid_pn.addWidget(self.search_btn)
        grid_pn.addWidget(self.stop_btn)

        files_box = QGroupBox("Files to search")
        fb = QHBoxLayout(files_box)
        fb.addWidget(self.pdf_check)
        fb.addWidget(self.csv_check)
        fb.addSpacing(10)
        fb.addWidget(QLabel("Name filter:"))
        fb.addWidget(self.name_filter_edit, 1)

        match_box = QGroupBox("Matching")
        mb = QHBoxLayout(match_box)
        mb.addWidget(self.partial_check)
        mb.addWidget(self.case_check)
        mb.addWidget(self.sep_check)

        options = QHBoxLayout()
        options.addWidget(files_box, 3)
        options.addWidget(match_box, 2)

        # Results tree
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["File / location", "Match", "Context", "Folder"])
        self.tree.setAlternatingRowColors(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tree.setItemDelegateForColumn(2, HtmlDelegate(self.tree))
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._tree_menu)
        self.tree.currentItemChanged.connect(self._on_current_changed)
        self.tree.itemDoubleClicked.connect(lambda item, _c: open_externally(self._item_path(item)))
        header = self.tree.header()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.resizeSection(0, 260)
        header.resizeSection(1, 130)
        header.resizeSection(2, 360)

        self.summary = QLabel("Choose a folder, enter a P/N and press Search.")
        self.show_pdf_check = QCheckBox("PDF")
        self.show_csv_check = QCheckBox("CSV")
        for cb in (self.show_pdf_check, self.show_csv_check):
            cb.setChecked(True)
            cb.setToolTip("Show or hide these results in the list (no new search needed)")
            cb.toggled.connect(self._apply_view_filter)
        self.expand_btn = QPushButton("Expand all")
        self.expand_btn.clicked.connect(self.tree.expandAll)
        self.collapse_btn = QPushButton("Collapse all")
        self.collapse_btn.clicked.connect(self.tree.collapseAll)
        self.folder_btn = QPushButton("Open folder")
        self.folder_btn.setToolTip("Open the folder containing the selected file in Windows Explorer")
        self.folder_btn.setEnabled(False)
        self.folder_btn.clicked.connect(lambda: show_in_folder(self._item_path(self.tree.currentItem())))
        self.drawing_btns: dict[str, QPushButton] = {}
        for kind in DRAWING_TYPES:
            b = QPushButton(f"Open {kind}")
            b.setToolTip(f"Open the {kind} drawing with the same name as the selected PDF")
            b.setEnabled(False)
            b.clicked.connect(lambda _=False, k=kind:
                              open_externally(self._item_drawings(self.tree.currentItem()).get(k, "")))
            self.drawing_btns[kind] = b
        self.issues_btn = QPushButton("Issues (0)")
        self.issues_btn.setEnabled(False)
        self.issues_btn.clicked.connect(self.show_issues)
        self.export_btn = QPushButton("Export CSV…")
        self.export_btn.clicked.connect(self.export_csv)
        self.print_btn = QPushButton("Print…")
        self.print_btn.clicked.connect(self.print_results)

        res_bar = QHBoxLayout()
        res_bar.addWidget(QLabel("Show:"))
        res_bar.addWidget(self.show_pdf_check)
        res_bar.addWidget(self.show_csv_check)
        res_bar.addStretch(1)
        for b in (self.expand_btn, self.collapse_btn, self.folder_btn, *self.drawing_btns.values(),
                  self.issues_btn, self.export_btn, self.print_btn):
            res_bar.addWidget(b)

        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.addWidget(self.summary)
        lv.addLayout(res_bar)
        lv.addWidget(self.tree, 1)

        # Preview
        self.pdf_preview = PdfPreview()
        self.csv_preview = CsvPreview()
        placeholder = QLabel("Click a result to preview it here.\nDouble-click opens the file.")
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder.setStyleSheet("color: gray")
        self.preview_stack = QStackedWidget()
        self.preview_stack.addWidget(placeholder)
        self.preview_stack.addWidget(self.pdf_preview)
        self.preview_stack.addWidget(self.csv_preview)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.addWidget(left)
        self.splitter.addWidget(self.preview_stack)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([760, 640])

        central = QWidget()
        v = QVBoxLayout(central)
        v.addLayout(grid_top)
        v.addLayout(grid_pn)
        v.addLayout(options)
        v.addWidget(self.splitter, 1)
        self.setCentralWidget(central)

        self.progress = QProgressBar()
        self.progress.setMaximumWidth(260)
        self.progress.setVisible(False)
        self.status_file = QLabel()
        self.statusBar().addWidget(self.status_file, 1)
        self.statusBar().addPermanentWidget(self.progress)

        find = QAction(self)
        find.setShortcut(QKeySequence("Ctrl+F"))
        find.triggered.connect(lambda: (self.pn_edit.setFocus(), self.pn_edit.selectAll()))
        self.addAction(find)
        esc = QAction(self)
        esc.setShortcut(QKeySequence("Escape"))
        esc.triggered.connect(self.stop_search)
        self.addAction(esc)

    # --- settings -----------------------------------------------------------
    def _load_settings(self) -> None:
        s = self.settings
        self.folder_edit.setText(s.value("folder", ""))
        self.pn_edit.setText(s.value("pn", ""))
        self.name_filter_edit.setText(s.value("name_filter", ""))
        self.pdf_check.setChecked(s.value("pdf", True, type=bool))
        self.csv_check.setChecked(s.value("csv", True, type=bool))
        self.partial_check.setChecked(s.value("partial", False, type=bool))
        self.case_check.setChecked(s.value("case", False, type=bool))
        self.sep_check.setChecked(s.value("separators", False, type=bool))
        self.show_pdf_check.setChecked(s.value("show_pdf", True, type=bool))
        self.show_csv_check.setChecked(s.value("show_csv", True, type=bool))
        if s.contains("geometry"):
            self.restoreGeometry(s.value("geometry"))
        if s.contains("splitter"):
            self.splitter.restoreState(s.value("splitter"))

    def _save_settings(self) -> None:
        s = self.settings
        s.setValue("folder", self.folder_edit.text())
        s.setValue("pn", self.pn_edit.text())
        s.setValue("name_filter", self.name_filter_edit.text())
        s.setValue("pdf", self.pdf_check.isChecked())
        s.setValue("csv", self.csv_check.isChecked())
        s.setValue("partial", self.partial_check.isChecked())
        s.setValue("case", self.case_check.isChecked())
        s.setValue("separators", self.sep_check.isChecked())
        s.setValue("show_pdf", self.show_pdf_check.isChecked())
        s.setValue("show_csv", self.show_csv_check.isChecked())
        s.setValue("geometry", self.saveGeometry())
        s.setValue("splitter", self.splitter.saveState())

    def closeEvent(self, event):
        self.stop_search()
        if self.worker is not None:
            self.worker.wait(3000)
        self._save_settings()
        super().closeEvent(event)

    # --- search -------------------------------------------------------------
    def choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Folder to search", self.folder_edit.text())
        if folder:
            self.folder_edit.setText(os.path.normpath(folder))

    def start_search(self) -> None:
        if self.worker is not None:
            return
        root = self.folder_edit.text().strip().strip('"')
        if not root or not os.path.isdir(root):
            QMessageBox.warning(self, "Partseek", "Choose an existing folder to search.")
            return
        kinds = [k for k, cb in (("PDF", self.pdf_check), ("CSV", self.csv_check)) if cb.isChecked()]
        if not kinds:
            QMessageBox.warning(self, "Partseek", "Select at least one file type (PDF or CSV).")
            return
        options = MatchOptions(
            partial=self.partial_check.isChecked(),
            case_sensitive=self.case_check.isChecked(),
            ignore_separators=self.sep_check.isChecked(),
        )
        try:
            matcher = Matcher(split_terms(self.pn_edit.text()), options)
        except ValueError as exc:
            QMessageBox.warning(self, "Partseek", str(exc))
            return

        self._save_settings()
        self.root = os.path.normpath(root)
        self.tree.clear()
        self.results.clear()
        self.issues.clear()
        self.files_scanned = self.hit_count = 0
        self.issues_btn.setText("Issues (0)")
        self.issues_btn.setEnabled(False)
        self.preview_stack.setCurrentIndex(0)
        self.pdf_preview.close_doc()

        self.worker = SearchWorker(self.root, kinds, self.name_filter_edit.text(), matcher)
        self.worker.listed.connect(self._on_listed)
        self.worker.progress.connect(self._on_progress)
        self.worker.fileDone.connect(self._on_file_done)
        self.worker.finished.connect(self._on_finished)
        self.search_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress.setRange(0, 0)
        self.progress.setVisible(True)
        self.summary.setText("Searching…")
        self.worker.start()

    def stop_search(self) -> None:
        if self.worker is not None:
            self.worker.cancel()

    def _on_listed(self, total: int) -> None:
        self.progress.setRange(0, max(1, total))
        self.total_files = total

    def _on_progress(self, done: int, total: int, path: str) -> None:
        if total:
            self.progress.setValue(done)
        if path:
            self.status_file.setText(os.path.relpath(path, self.root) if os.path.isabs(path) else path)

    def _on_file_done(self, result: FileResult) -> None:
        self.files_scanned += 1
        if result.error or result.no_text:
            self.issues.append(result)
            self.issues_btn.setText(f"Issues ({len(self.issues)})")
            self.issues_btn.setEnabled(True)
        if result.hits:
            self.results.append(result)
            self.hit_count += len(result.hits)
            self._add_result_item(result)
        self._update_summary(running=True)

    def _on_finished(self) -> None:
        cancelled = self.worker.cancelled if self.worker else False
        self.worker = None
        self.search_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.progress.setVisible(False)
        self.status_file.setText("Search stopped." if cancelled else "Search finished.")
        self._update_summary(running=False, cancelled=cancelled)
        if self.tree.currentItem() is None:
            self._select_first_visible()

    def _update_summary(self, running: bool | None = None, cancelled: bool = False) -> None:
        if running is not None:
            self._summary_state = "Searching… " if running else ("Stopped — " if cancelled else "")
        text = (f"{getattr(self, '_summary_state', '')}<b>{self.hit_count}</b> hit(s) in "
                f"<b>{len(self.results)}</b> file(s) · {self.files_scanned} file(s) scanned")
        with_drawing = sum(1 for r in self.results if r.drawings)
        if with_drawing:
            text += (f' · <span style="color:{DRAWING_COLOR.name()}"><b>{with_drawing}</b>'
                     f" PDF(s) with DWG/DXF</span>")
        shown = [r for r in self.results if r.kind in self._shown_kinds()]
        if len(shown) != len(self.results):
            text += f" · <b>{len(shown)}</b> file(s) shown"
        self.summary.setText(text)

    # --- view filter --------------------------------------------------------
    def _shown_kinds(self) -> set[str]:
        return {k for k, cb in (("PDF", self.show_pdf_check), ("CSV", self.show_csv_check)) if cb.isChecked()}

    def _apply_view_filter(self) -> None:
        kinds = self._shown_kinds()
        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            top.setHidden(top.data(0, DATA_ROLE).kind not in kinds)
        current = self.tree.currentItem()
        if current is None or current.isHidden() or (current.parent() and current.parent().isHidden()):
            self.tree.setCurrentItem(None)
            self.preview_stack.setCurrentIndex(0)
            self._select_first_visible()
        if self.root:
            self._update_summary()

    def _select_first_visible(self) -> None:
        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            if not top.isHidden() and top.childCount():
                self.tree.setCurrentItem(top.child(0))
                return

    def _add_result_item(self, result: FileResult) -> None:
        exact = sum(h.exact for h in result.hits)
        partial = len(result.hits) - exact
        counts = f"{len(result.hits)} hit(s)" + (f", {partial} partial" if partial else "")
        folder = os.path.relpath(os.path.dirname(result.path), self.root)
        name = os.path.basename(result.path) + _drawing_mark(result.drawings)
        top = QTreeWidgetItem([name, counts, "", "" if folder == "." else folder])
        top.setData(0, DATA_ROLE, result)
        top.setToolTip(0, "\n".join([result.path] + [f"{k}: {p}" for k, p in result.drawings.items()]))
        if result.drawings:
            top.setForeground(0, DRAWING_COLOR)
        f = top.font(0)
        f.setBold(True)
        top.setFont(0, f)
        top.setIcon(0, self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon))
        for hit in result.hits:
            label = hit.matched if hit.exact else f"{hit.matched}  (partial)"
            child = QTreeWidgetItem([hit.location_label, label, "", ""])
            child.setData(0, DATA_ROLE, hit)
            child.setData(2, HTML_ROLE, _context_html(hit))
            child.setToolTip(2, hit.context)
            if not hit.exact:
                child.setForeground(1, PARTIAL_COLOR)
            top.addChild(child)
        self.tree.addTopLevelItem(top)
        top.setHidden(result.kind not in self._shown_kinds())
        top.setExpanded(len(result.hits) <= 20)

    # --- preview ------------------------------------------------------------
    def _item_path(self, item: QTreeWidgetItem | None) -> str:
        if item is None:
            return ""
        data = item.data(0, DATA_ROLE)
        return getattr(data, "path", "")

    def _item_drawings(self, item: QTreeWidgetItem | None) -> dict[str, str]:
        """Same-name DWG/DXF files of the file that `item` (a file or one of its hits) belongs to."""
        if item is None:
            return {}
        top = item.parent() or item
        return getattr(top.data(0, DATA_ROLE), "drawings", {})

    def _on_current_changed(self, item: QTreeWidgetItem | None, _prev) -> None:
        self.folder_btn.setEnabled(bool(self._item_path(item)))
        drawings = self._item_drawings(item)
        for kind, b in self.drawing_btns.items():
            b.setEnabled(kind in drawings)
        if item is None:
            return
        data = item.data(0, DATA_ROLE)
        if isinstance(data, FileResult):
            if not data.hits:
                return
            hit, result = data.hits[0], data
        else:
            hit, result = data, item.parent().data(0, DATA_ROLE)
        try:
            if hit.kind == "PDF":
                terms = sorted({h.matched for h in result.hits}, key=len, reverse=True)
                self.pdf_preview.show_file(hit.path, hit.location, terms, [h.location for h in result.hits],
                                           result.drawings)
                self.preview_stack.setCurrentWidget(self.pdf_preview)
            else:
                marked = {(h.location - 1, h.column_index) for h in result.hits}
                self.csv_preview.show_file(hit.path, hit.location, hit.column_index, marked)
                self.preview_stack.setCurrentWidget(self.csv_preview)
        except Exception as exc:
            self.preview_stack.setCurrentIndex(0)
            QMessageBox.warning(self, "Partseek", f"Cannot preview {hit.path}:\n{exc}")

    def _tree_menu(self, pos) -> None:
        item = self.tree.itemAt(pos)
        path = self._item_path(item)
        if not path:
            return
        menu = QMenu(self)
        menu.addAction("Open file", lambda: open_externally(path))
        for kind, drawing in self._item_drawings(item).items():
            menu.addAction(f"Open {kind} ({os.path.basename(drawing)})",
                           lambda d=drawing: open_externally(d))
        menu.addAction("Open containing folder", lambda: show_in_folder(path))
        menu.addAction("Copy path", lambda: QApplication.clipboard().setText(path))
        data = item.data(0, DATA_ROLE)
        if isinstance(data, Hit):
            menu.addAction("Copy context", lambda: QApplication.clipboard().setText(data.context))
        menu.exec(self.tree.viewport().mapToGlobal(pos))

    # --- issues / export / print -------------------------------------------
    def show_issues(self) -> None:
        lines = []
        for r in self.issues:
            reason = r.error or "No text layer (scanned PDF — needs OCR to be searchable)"
            lines.append(f"{r.path}\n    {reason}")
        box = QMessageBox(self)
        box.setWindowTitle("Partseek — issues")
        box.setIcon(QMessageBox.Icon.Information)
        box.setText(f"{len(self.issues)} file(s) could not be fully searched.")
        box.setDetailedText("\n".join(lines))
        box.exec()

    def _all_hits(self) -> list[Hit]:
        kinds = self._shown_kinds()
        return [h for r in self.results if r.kind in kinds for h in r.hits]

    def _drawings_by_path(self) -> dict[str, dict[str, str]]:
        return {r.path: r.drawings for r in self.results if r.drawings}

    def export_csv(self) -> None:
        hits = self._all_hits()
        if not hits:
            QMessageBox.information(self, "Partseek", "There are no shown results to export.")
            return
        default = os.path.join(self.settings.value("export_dir", os.path.expanduser("~")),
                               "partseek_results.csv")
        path, _ = QFileDialog.getSaveFileName(self, "Export results", default, "CSV files (*.csv)")
        if not path:
            return
        self.settings.setValue("export_dir", os.path.dirname(path))
        drawings = self._drawings_by_path()
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["File", "Folder", "Type", "Page/Row", "Column", "Match", "Exact", "Context",
                        *DRAWING_TYPES])
            for h in hits:
                found = drawings.get(h.path, {})
                w.writerow([os.path.basename(h.path), os.path.dirname(h.path), h.kind, h.location,
                            h.column, h.matched, "yes" if h.exact else "partial", h.context,
                            *(os.path.basename(found.get(k, "")) for k in DRAWING_TYPES)])
        self.status_file.setText(f"Exported {len(hits)} hit(s) to {path}")

    def print_results(self) -> None:
        hits = self._all_hits()
        if not hits:
            QMessageBox.information(self, "Partseek", "There are no shown results to print.")
            return
        drawings = self._drawings_by_path()
        rows = "".join(
            f"<tr><td>{html.escape(os.path.relpath(h.path, self.root))}"
            f"<b>{_drawing_mark(drawings.get(h.path, {}))}</b></td>"
            f"<td>{html.escape(h.location_label)}</td>"
            f"<td>{html.escape(h.matched)}{'' if h.exact else ' (partial)'}</td>"
            f"<td>{_context_html(h)}</td></tr>"
            for h in hits)
        doc = QTextDocument()
        doc.setHtml(
            f"<h3>Partseek results: {html.escape(self.pn_edit.text())}</h3>"
            f"<p>Folder: {html.escape(self.root)}<br>{len(hits)} hit(s) in {len({h.path for h in hits})} file(s)</p>"
            '<table border="1" cellspacing="0" cellpadding="3" width="100%">'
            "<tr><th>File</th><th>Location</th><th>Match</th><th>Context</th></tr>"
            f"{rows}</table>")
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        if QPrintDialog(printer, self).exec():
            doc.print_(printer)


def _resource_path(name: str) -> str:
    """Path to a bundled resource, both from source and inside a PyInstaller exe."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, name)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(__product__)
    app.setApplicationDisplayName(__product__)
    app.setApplicationVersion(__version__)
    app.setOrganizationName(__company__)
    app.setStyle("Fusion")
    icon_path = _resource_path("partseek.ico")
    if os.path.exists(icon_path):
        from PySide6.QtGui import QIcon

        app.setWindowIcon(QIcon(icon_path))
    win = MainWindow()
    win.show()
    return app.exec()
