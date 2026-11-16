# Partseek

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](LICENSE)

**By ETS - Expand Technology Solutions.** Free and open-source software, licensed under the **GNU AGPL-3.0-or-later**.

Desktop app that searches a folder and all its subfolders for part numbers (P/N) inside **PDF** and **CSV** files.

## Install

Download **`Partseek-Setup-1.0.0.exe`** from the [latest release](../../releases/latest) and run it. The installer adds Start Menu (and optional desktop) shortcuts and an uninstaller. No Python needed on the target PC.

## Start

Double-click **`Partseek.bat`**. The first run sets up a local Python environment.

Or run it from a terminal:

```
.venv\Scripts\python -m partseek
```

## Using it

1. **Folder**: pick the root folder. All subfolders are searched.
2. **P/N**: enter a part number. To search for several, separate them with `;` (for example `LM317; NE555`).
3. **Files to search**: tick PDF, CSV or both. The optional **Name filter** limits the search to matching file names, for example `BOM` or `*rev*;*.csv`.
4. **Matching**
   - *Partial match*: also shows hits where the P/N is part of a longer string, such as `LM317` inside `LM317T` or `LM317-ADJ`. These hits are shown in orange and marked "(partial)".
   - *Match case*: matches upper and lower case exactly.
   - *Ignore separators*: treats `- . / _` and spaces as optional, so `ABC-123` also finds `ABC123` and `ABC 123`.
5. Press **Search** (or Enter). Results are grouped by file and show the page (PDF) or row and column (CSV), plus the text around each hit.
6. **Click a result** to preview it. PDFs open at the page with every hit highlighted (use Hit ⏮/⏭ to jump between pages, Ctrl+wheel to zoom). CSVs open as a table with the matching cells highlighted.
   **Double-click** opens the file in its default program. **Open folder** (in the results bar, the preview toolbar or the right-click menu) opens the folder containing the file in Windows Explorer, with the file selected. Right-click also gives *Copy path*.
   **DWG / DXF drawings**: if a PDF with hits has a `.dwg` or `.dxf` file with the same name in the same folder (for example `Bracket-01.pdf` and `Bracket-01.dwg`), the PDF is marked in blue in the results: **[+DWG]**, **[+DXF]** or **[+DWG +DXF]**. Open the drawing with **Open DWG** / **Open DXF** (in the results bar, the preview toolbar or the right-click menu). Exported CSV results include the DWG and DXF file names.
7. **Show: PDF / CSV** above the result list hides or shows PDF or CSV results right away, without searching again.
8. **Export CSV…** / **Print…** save or print the results that are shown.

**Issues** lists files that could not be searched: damaged or password-protected files, and scanned PDFs that have no text layer (these need OCR first).

## Development

```
py -3 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt pytest
.venv\Scripts\python -m pytest
```

### Build the Windows release (standalone exe + installer)

The release is a single-file exe built with **PyInstaller** (carrying the
ETS version resource and icon), wrapped in a Windows installer with
**Inno Setup**. The build also runs the Python through **PyArmor** — on an
open-source project this is just packaging, not a security measure, since the
source is public; it can be removed if you prefer a plain PyInstaller build.

```
rem 1. Standalone exe  ->  release_out\Partseek.exe
.venv\Scripts\python installer\build_protected.py

rem 2. Windows installer  ->  release_out\Partseek-Setup-1.0.0.exe
"%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" installer\Partseek.iss
```

Or run both steps at once with **`build_release.bat`**. Build tools are in
`requirements-build.txt`. `build_exe.bat` produces a simpler one-file exe.

## License

Copyright (C) 2026 **ETS - Expand Technology Solutions**.

Partseek is free software released under the **GNU Affero General Public
License v3.0 or later** (AGPL-3.0). You may use, study, share and modify it
under those terms; if you distribute it or run a modified version as a network
service, you must make the corresponding source available under the same
license. See [LICENSE](LICENSE) for the full text.

### Third-party components

| Component | License |
|---|---|
| [PyMuPDF](https://github.com/pymupdf/PyMuPDF) | GNU AGPL-3.0 (or Artifex commercial) |
| [Qt for Python / PySide6](https://doc.qt.io/qtforpython/) | GNU LGPL-3.0 |

Partseek uses PyMuPDF, which is AGPL-3.0; that is why the combined work is
distributed under the AGPL-3.0. For a permissively licensed or closed-source
distribution you would need a commercial PyMuPDF license from Artifex.
