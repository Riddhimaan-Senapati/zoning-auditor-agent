from pathlib import Path

from auditor.corpus import Corpus
from auditor.models import CellQuote, TextQuote
from auditor.quotes import QuoteError, verify_cell, verify_text

CORPUS = Corpus.load(Path(__file__).parent / "fixtures" / "mini53")
HEIGHT = "Building Height Maximum | Feet"


def _quoted(section_id: str, needle: str) -> str:
    out = verify_text(TextQuote(section_id=section_id, text=needle), CORPUS)
    assert isinstance(out, TextQuote), out
    start, end = out.span
    return CORPUS.section(section_id).text[start:end]


def test_seeded_reference_errors_are_quotable():
    for needle in ("Section 53-8 (Waterfront Yard Area Requirements)", "this Section 53-27", "EBR-1"):
        assert _quoted("53-29.4", needle) == needle


def test_clean_reference_and_prose_height_are_quotable():
    assert _quoted("53-19", "Section 53-10.4 (Waterfront Yard Area Requirements)") == (
        "Section 53-10.4 (Waterfront Yard Area Requirements)"
    )
    assert _quoted("53-21", "the maximum building height is 35 feet") == "the maximum building height is 35 feet"


def test_table_cells_conflicting_with_prose_are_quotable():
    ebr3 = CellQuote(table_id="53:TableH", row_label="EBR-3", column=HEIGHT, text="40")
    assert verify_cell(ebr3, CORPUS).position == (1, 1)
    assert verify_cell(ebr3.model_copy(update={"text": "35"}), CORPUS) == QuoteError(reason="cell text does not match")
    ebr4 = CellQuote(table_id="53:TableH", row_label="EBR-4", column=HEIGHT, text="see fn")
    assert verify_cell(ebr4, CORPUS).position == (2, 1)
