import pytest

from partseek.matcher import Matcher, MatchOptions, snippet, split_terms


def texts(matcher, text):
    return [(m.text, m.exact) for m in matcher.find(text)]


def test_exact_requires_standalone_pn():
    m = Matcher(["LM317"], MatchOptions())
    assert texts(m, "Use LM317, not LM317T or XLM317") == [("LM317", True)]


def test_partial_finds_embedded_and_labels_exactness():
    m = Matcher(["LM317"], MatchOptions(partial=True))
    assert texts(m, "LM317 LM317T XLM317") == [("LM317", True), ("LM317", False), ("LM317", False)]


def test_case_sensitivity():
    assert texts(Matcher(["abc-1"], MatchOptions()), "ABC-1") == [("ABC-1", True)]
    assert texts(Matcher(["abc-1"], MatchOptions(case_sensitive=True)), "ABC-1") == []


def test_ignore_separators():
    m = Matcher(["ABC-123/4"], MatchOptions(ignore_separators=True))
    assert texts(m, "ABC1234 ; ABC 123.4 ; ABC-\n123-4") == [
        ("ABC1234", True), ("ABC 123.4", True), ("ABC-\n123-4", True)]


def test_punctuation_in_pn_is_literal():
    m = Matcher(["R1.5(K)"], MatchOptions())
    assert texts(m, "R1.5(K) R135(K)") == [("R1.5(K)", True)]


def test_multiple_terms_longest_first():
    m = Matcher(split_terms("ABC-12; ABC-123"), MatchOptions(partial=True))
    assert texts(m, "ABC-123") == [("ABC-123", True)]


def test_split_terms_and_empty():
    assert split_terms(" a ; b;a;; ") == ["a", "b"]
    with pytest.raises(ValueError):
        Matcher([], MatchOptions())


def test_snippet():
    before, mid, after = snippet("x" * 100 + " PN-1\n here", 101, 105, width=5)
    assert (before, mid, after) == ("…xxxx ", "PN-1", " her…")


def test_joined_suffix_is_a_different_pn():
    m = Matcher(["LM317"], MatchOptions())
    assert texts(m, "LM317-ADJ, X-LM317, LM317. (LM317) LM317/") == [
        ("LM317", True), ("LM317", True), ("LM317", True)]
    p = Matcher(["LM317"], MatchOptions(partial=True))
    assert [e for _, e in texts(p, "LM317-ADJ LM317.")] == [False, True]
