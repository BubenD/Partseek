import pymupdf as fitz

from partseek.matcher import Matcher, MatchOptions
from partseek.scanner import iter_files, search_file


def make_pdf(path, pages):
    doc = fitz.open()
    for text in pages:
        doc.new_page().insert_text((72, 72), text)
    doc.save(path)
    doc.close()


def test_walks_subfolders_and_filters(tmp_path):
    (tmp_path / "a" / "b").mkdir(parents=True)
    make_pdf(tmp_path / "a" / "b" / "BOM_rev1.pdf", ["x"])
    (tmp_path / "a" / "list.csv").write_text("pn\n1\n")
    (tmp_path / "notes.txt").write_text("x")
    names = lambda files: sorted(p.split("\\")[-1].split("/")[-1] for p in files)
    assert names(iter_files(str(tmp_path), ["PDF", "CSV"])) == ["BOM_rev1.pdf", "list.csv"]
    assert names(iter_files(str(tmp_path), ["CSV"])) == ["list.csv"]
    assert names(iter_files(str(tmp_path), ["PDF", "CSV"], "bom")) == ["BOM_rev1.pdf"]


def test_pdf_hits_have_pages(tmp_path):
    pdf = tmp_path / "doc.pdf"
    make_pdf(pdf, ["nothing here", "Part LM317T fitted", "LM317 again"])
    exact = search_file(str(pdf), Matcher(["LM317"], MatchOptions()))
    assert [(h.location, h.exact) for h in exact.hits] == [(3, True)]
    partial = search_file(str(pdf), Matcher(["LM317"], MatchOptions(partial=True)))
    assert [(h.location, h.exact) for h in partial.hits] == [(2, False), (3, True)]


def test_csv_hits_rows_columns_and_encodings(tmp_path):
    csv_file = tmp_path / "bom.csv"
    csv_file.write_bytes("Ref;Part No;Desc\nR1;RC0603-10K;Résistance\nU1;LM317;Regulator\n".encode("cp1252"))
    res = search_file(str(csv_file), Matcher(["lm317"], MatchOptions()))
    assert res.error is None
    [hit] = res.hits
    assert (hit.location, hit.column, hit.column_index) == (3, "Part No", 1)
    assert hit.context == "U1 | LM317 | Regulator"


def test_pdf_with_same_name_drawings(tmp_path):
    make_pdf(tmp_path / "Bracket-01.pdf", ["LM317"])
    (tmp_path / "BRACKET-01.DWG").write_bytes(b"AC1032")
    (tmp_path / "bracket-01.dxf").write_text("0\nEOF\n")
    make_pdf(tmp_path / "plate.pdf", ["LM317"])
    (tmp_path / "plate.dxf").write_text("0\nEOF\n")
    make_pdf(tmp_path / "other.pdf", ["LM317"])
    (tmp_path / "other_v2.dwg").write_bytes(b"AC1032")
    matcher = Matcher(["LM317"], MatchOptions())
    res = search_file(str(tmp_path / "Bracket-01.pdf"), matcher)
    assert res.drawings == {"DWG": str(tmp_path / "BRACKET-01.DWG"),
                            "DXF": str(tmp_path / "bracket-01.dxf")}
    assert search_file(str(tmp_path / "plate.pdf"), matcher).drawings == {"DXF": str(tmp_path / "plate.dxf")}
    assert search_file(str(tmp_path / "other.pdf"), matcher).drawings == {}


def test_bad_file_reports_error(tmp_path):
    bad = tmp_path / "broken.pdf"
    bad.write_bytes(b"not a pdf")
    res = search_file(str(bad), Matcher(["x"], MatchOptions()))
    assert res.error and not res.hits
