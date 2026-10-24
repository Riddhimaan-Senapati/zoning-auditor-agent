from hypothesis import example, given
from hypothesis import strategies as st

from auditor.corpus import Corpus
from auditor.models import Cell, CellQuote, Section, SourceRef, Table, TableRow, TextQuote
from auditor.quotes import QuoteError, normalize, verify_cell, verify_text

# Characters that make normalization non-trivial: combining marks, a precomposed accent,
# U+00B4 (NFKC turns it into space + combining mark), a ligature, NBSP, CRLF, curly
# quotes, hyphen and dash variants, and Hangul jamo that NFKC composes.
_TRICKY = "e\u0301\u00e9\u00b4\ufb01\u00a0\r\n \u2019\u201c\u2011\u2013\u2014\u2212\u1100\u1161\u11a8"
_text = st.text(alphabet=st.sampled_from(list("aZ5-.() ") + list(_TRICKY)), min_size=1)


def _corpus(text: str) -> Corpus:
    section = Section(
        id="53-1", article="53", heading="h", text=text, parent=None,
        kind="section", source=SourceRef(file="f", anchor="a"),
    )
    return Corpus([section], [])


def _span(text: str, quote: str) -> str:
    out = verify_text(TextQuote(section_id="53-1", text=quote), _corpus(text))
    assert isinstance(out, TextQuote), out
    start, end = out.span
    return text[start:end]


@given(_text, st.integers(), st.integers())
@example("a\u0301", 0, 1)
@example("\u1100\u1161 x", 0, 1)
def test_property_1_every_substring_round_trips(text, i, j):
    lo, hi = sorted((i % len(text), j % len(text)))
    sub = text[lo : hi + 1]
    out = verify_text(TextQuote(section_id="53-1", text=sub), _corpus(text))
    if isinstance(out, QuoteError):
        # Only allowed when the substring is blank or cuts a cluster NFKC treats as one unit.
        assert not normalize(sub) or normalize(sub) not in normalize(text) or out.reason == "quote splits a source character"
        return
    start, end = out.span
    assert normalize(text[start:end]) == normalize(sub)


@given(_text, _text)
def test_property_1_absent_strings_are_rejected(text, needle):
    if normalize(needle) and normalize(needle) not in normalize(text):
        assert isinstance(verify_text(TextQuote(section_id="53-1", text=needle), _corpus(text)), QuoteError)


@given(_text)
def test_property_1_normalize_is_idempotent(s):
    assert normalize(normalize(s)) == normalize(s)


def test_decomposed_accent_in_source_matches_precomposed_quote():
    assert _span("the cafe\u0301 zone", "caf\u00e9") == "cafe\u0301"


def test_plain_substring_has_literal_span():
    out = verify_text(TextQuote(section_id="53-1", text="Section 53-10.4"),
                      _corpus("See Section 53-8.4 Section 53-10.4 (Waterfront Yard Area Requirements)."))
    assert out.span == (19, 34)


def test_curly_quotes_match_straight():
    assert _span("The \u201cWaterfront\u201d district applies.", '"Waterfront"') == "\u201cWaterfront\u201d"


def test_ligature_folds_whole_but_not_split():
    assert _span("No a\ufb01davit required.", "afidavit") == "a\ufb01davit"
    out = verify_text(TextQuote(section_id="53-1", text="af"), _corpus("No a\ufb01davit required."))
    assert out == QuoteError(reason="quote splits a source character")


def test_whitespace_and_dash_variants_fold():
    assert _span("Setback  requirements \u2014 see\u00a0below.", "requirements - see below") == "requirements \u2014 see\u00a0below"
    assert _span("See Section 53\u20118.", "Section 53-8") == "Section 53\u20118"


def test_verify_cell_sets_position_and_rejects_mismatch():
    table = Table(
        id="53:TableH", article="53", title="H",
        columns=["Subdistrict", "Building Height Maximum | Feet"],
        rows=[
            TableRow(label="EBR-2.5", cells=[Cell(text="EBR-2.5", footnote_marks=[]), Cell(text="30", footnote_marks=[])]),
            TableRow(label="EBR-3", cells=[Cell(text="EBR-3", footnote_marks=[]), Cell(text="35", footnote_marks=[])]),
        ],
        footnotes={}, applicable_footnotes=[], source=SourceRef(file="f", anchor="a"),
    )
    corpus = Corpus([], [table])
    q = CellQuote(table_id="53:TableH", row_label="EBR-3", column="Building Height Maximum | Feet", text="35")
    assert verify_cell(q, corpus).position == (1, 1)
    assert verify_cell(q.model_copy(update={"text": "40"}), corpus) == QuoteError(reason="cell text does not match")
