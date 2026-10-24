"""Tests for the read-only MCP server (design §5.6, Correctness Property 5).

Three layers:
  * each tool function called directly on a Corpus, with literal expected outputs;
  * Property 5, that every tool, called with hypothesis-generated arguments, leaves every
    file under the build dir and the fixture dir byte-for-byte unchanged;
  * one stdio smoke test that starts `python -m auditor.mcp_server <build_dir>` as a
    subprocess, drives it with the SDK client, and lists the seven tool names.
"""

from __future__ import annotations

import hashlib
import json
import sys
from decimal import Decimal
from pathlib import Path

import anyio
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from auditor.mcp_server import Tools
from auditor.models import (
    Rule,
    Section,
    SourceRef,
    TextQuote,
)
from auditor.search import build_search

MINI53 = Path(__file__).parent / "fixtures" / "mini53"
HEIGHT = "Building Height Maximum | Feet"

TOOL_NAMES = {
    "get_section",
    "get_table",
    "search_sections",
    "related_sections",
    "get_rules",
    "get_definition",
    "resolve_reference",
}


@pytest.fixture
def tools(tmp_path) -> Tools:
    return Tools.from_build_dir(MINI53, tmp_path)


# --- get_section -------------------------------------------------------------------


def test_get_section_returns_heading_text_parent_and_children(tools: Tools):
    assert tools.get_section("53-4") == {
        "id": "53-4",
        "heading": "Establishment of Subdistricts",
        "text": "The following subdistricts are established: EBR-2.5, EBR-3, and EBR-4. "
        "Each subdistrict has the dimensional regulations set out in Table H.",
        "parent": "53",
        "children": ["53-4.1"],
    }


def test_get_section_unknown_is_none(tools: Tools):
    assert tools.get_section("53-999") is None


def test_get_section_truncates_long_text(tmp_path):
    long = "A" * 3000
    tools = _tools(tmp_path, [_sec("7-1", text=long)])
    out = tools.get_section("7-1")
    assert out is not None
    assert out["text"] == "A" * 2000 + "\u2026[truncated]"


# --- get_table ---------------------------------------------------------------------


def test_get_table_returns_columns_rows_and_footnotes(tools: Tools):
    assert tools.get_table("53:TableH") == {
        "id": "53:TableH",
        "title": "Table H: Dimensional Regulations",
        "columns": ["Subdistrict", HEIGHT, "Minimum Lot Area | Square Feet"],
        "rows": [
            {"label": "EBR-2.5", "cells": ["EBR-2.5", "30", "5000"]},
            {"label": "EBR-3", "cells": ["EBR-3", "40", "4000"]},
            {"label": "EBR-4", "cells": ["EBR-4", "see fn", "3000"]},
        ],
        "footnotes": {"3": "53:TableH:fn3", "9": "53:TableH:fn9"},
    }


def test_get_table_unknown_is_none(tools: Tools):
    assert tools.get_table("53:TableZ") is None


# --- search_sections ---------------------------------------------------------------


def test_search_sections_ranks_by_relevance(tools: Tools):
    assert tools.search_sections("waterfront yard area", 3) == [
        {
            "id": "53-19",
            "heading": "Design Review",
            "snippet": "Projects shall satisfy the waterfront yard standard in Section 53-10.4 "
            "(Waterfront Yard Area Requirements).",
        },
        {
            "id": "53-10.4",
            "heading": "Waterfront Yard Area Requirements",
            "snippet": "A waterfront yard of at least 50 feet shall be provided along the water's edge.",
        },
        {
            "id": "53-29.4",
            "heading": "Exceptions",
            "snippet": "Except as otherwise provided in this Section 53-27, lots in EBR-1 shall meet "
            "the yard standards in Section 53-8 (Waterfront Yard Area Requirements).",
        },
    ]


def test_search_sections_punctuation_only_is_empty(tools: Tools):
    assert tools.search_sections("()", 5) == []


# --- get_rules and related_sections (need a rules.jsonl) ---------------------------


def _rule(id: str, section_id: str, item: str, district: str | None, value: str) -> Rule:
    return Rule(
        id=id,
        district=district,
        use=None,
        item=item,  # type: ignore[arg-type]
        comparator="max",
        value=Decimal(value),
        unit="ft",
        status=None,
        conditions=[],
        footnotes=[],
        quote=TextQuote(section_id=section_id, text=f"{value} feet", span=(0, len(value) + 5)),
        source="prose",
        review_reason=None,
    )


RULES = [
    _rule("r1", "53-21", "building_height_ft", "EBR-3", "35"),
    _rule("r2", "53-22", "building_height_ft", "EBR-3", "40"),
    _rule("r3", "53-23", "front_yard_min", "EBR-4", "10"),
    _rule("r4", "53-24", "building_height_ft", "EBR-9", "50"),
    _rule("r5", "53-25", "front_yard_min", "EBR-3", "20"),
]


def _rules_tools(tmp_path) -> Tools:
    return _tools(tmp_path, [_sec(sid) for sid in ("53-21", "53-22", "53-23", "53-24", "53-25")], RULES)


def test_get_rules_with_no_rules_file_is_empty(tools: Tools):
    assert tools.get_rules() == []


def test_get_rules_filters_by_district_use_and_item(tmp_path):
    tools = _rules_tools(tmp_path)
    got = tools.get_rules(item="building_height_ft")
    assert [r["id"] for r in got] == ["r1", "r2", "r4"]
    assert tools.get_rules(district="EBR-4") == [
        {
            "id": "r3",
            "district": "EBR-4",
            "use": None,
            "item": "front_yard_min",
            "comparator": "max",
            "value": "10",
            "unit": "ft",
            "status": None,
            "conditions": [],
            "footnotes": [],
            "quote": {"kind": "text", "section_id": "53-23", "text": "10 feet", "span": [0, 7]},
            "source": "prose",
            "review_reason": None,
            "needs_review": False,
        }
    ]


def test_related_sections_needs_district_or_use_plus_item(tmp_path):
    # 53-24 shares only the item and 53-25 only the district with 53-21.
    assert _rules_tools(tmp_path).related_sections("53-21") == ["53-22"]


def test_related_sections_empty_without_rules(tools: Tools):
    assert tools.related_sections("53-21") == []


# --- get_definition (needs an Article 2) -------------------------------------------


def _definition_tools(tmp_path) -> Tools:
    art2 = [
        _sec("2", heading="Definitions", text="This Article defines terms used in the Code.", parent=None),
        _sec(
            "2-1",
            heading="Accessory Family Child Care Home",
            text="Accessory Family Child Care Home means a child care home that is accessory to a dwelling.",
            parent="2",
        ),
        _sec("2-2", heading="Allotment Garden", text="Allotment Garden means a garden of plots.", parent="2"),
        _sec("2-3", heading="Lot", text='"Lot," a parcel of land.', parent="2"),
    ]
    return _tools(tmp_path, art2)


def test_get_definition_matches_article_2_heading(tmp_path):
    tools = _definition_tools(tmp_path)
    assert tools.get_definition("Accessory Family Child Care Home") == {
        "id": "2-1",
        "term": "Accessory Family Child Care Home",
        "definition": "Accessory Family Child Care Home means a child care home that is accessory to a dwelling.",
    }


def test_get_definition_none_when_no_article_2(tools: Tools):
    assert tools.get_definition("EBR-3") is None


def test_get_definition_none_when_term_absent(tmp_path):
    assert _definition_tools(tmp_path).get_definition("Floor Area Ratio") is None


def test_get_definition_needs_the_whole_term(tmp_path):
    tools = _definition_tools(tmp_path)
    assert tools.get_definition("lot")["id"] == "2-3"
    assert tools.get_definition("a") is None
    assert tools.get_definition("garden") is None


# --- resolve_reference -------------------------------------------------------------


def test_resolve_reference_title_mismatch(tools: Tools):
    assert tools.resolve_reference(
        "see Section 53-8 (Waterfront Yard Area Requirements)", "53-29.4"
    ) == {
        "status": "title_mismatch",
        "detail": 'Section 53-29.4 cites Section 53-8 as "Waterfront Yard Area Requirements", '
        'but Section 53-8 is titled "Regulations Applicable on Tidelands". Section 53-10.4 '
        'is titled "Waterfront Yard Area Requirements".',
        "references": [
            {
                "raw": "Section 53-8",
                "status": "title_mismatch",
                "detail": 'Section 53-29.4 cites Section 53-8 as "Waterfront Yard Area Requirements", '
                'but Section 53-8 is titled "Regulations Applicable on Tidelands". Section 53-10.4 '
                'is titled "Waterfront Yard Area Requirements".',
            }
        ],
    }


def test_resolve_reference_self_mismatch(tools: Tools):
    out = tools.resolve_reference("this Section 53-27", "53-29.4")
    assert out["status"] == "self_mismatch"
    assert out["detail"] == 'Section 53-29.4 says "this Section 53-27", but it sits in Section 53-29.4.'


def test_resolve_reference_no_reference(tools: Tools):
    assert tools.resolve_reference("no reference here", "53-1") == {
        "status": "no_reference",
        "detail": "No reference found in 'no reference here'.",
        "references": [],
    }


# --- Property 5: tools are read-only -----------------------------------------------


def _digest(*dirs: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for d in dirs:
        for p in sorted(d.rglob("*")):
            if p.is_file():
                out[str(p)] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


_ID = st.text(min_size=0, max_size=40)
_ARGS = {
    "get_section": st.fixed_dictionaries({"section_id": _ID}),
    "get_table": st.fixed_dictionaries({"table_id": _ID}),
    "search_sections": st.fixed_dictionaries(
        {"query": st.text(max_size=40), "k": st.integers(min_value=0, max_value=10)}
    ),
    "related_sections": st.fixed_dictionaries(
        {"section_id": _ID, "k": st.integers(min_value=0, max_value=10)}
    ),
    "get_rules": st.fixed_dictionaries(
        {
            "district": st.none() | _ID,
            "use": st.none() | _ID,
            "item": st.none() | _ID,
        }
    ),
    "get_definition": st.fixed_dictionaries({"term": st.text(max_size=40)}),
    "resolve_reference": st.fixed_dictionaries(
        {"text": st.text(max_size=60), "from_section": _ID}
    ),
}


@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(st.sampled_from(sorted(TOOL_NAMES)).flatmap(lambda n: st.tuples(st.just(n), _ARGS[n])))
def test_property_5_tools_never_write(tools: Tools, call: tuple[str, dict]):
    name, kwargs = call
    before = _digest(MINI53)
    try:
        getattr(tools, name)(**kwargs)
    except (ValueError, KeyError):
        # A bad id may be rejected by validation; the invariant is still "no writes".
        pass
    assert _digest(MINI53) == before


# --- stdio smoke test --------------------------------------------------------------


def test_stdio_server_lists_the_seven_tools_and_leaves_no_temp_index(tmp_path):
    build_dir = str(MINI53.resolve())

    async def run() -> list[str]:
        params = StdioServerParameters(
            command=sys.executable, args=["-m", "auditor.mcp_server", build_dir], env={"TMPDIR": str(tmp_path)}
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                listing = await session.list_tools()
                names = [t.name for t in listing.tools]
                result = await session.call_tool("get_section", {"section_id": "53-21"})
        assert result.isError is False
        payload = json.loads(result.content[0].text)
        assert payload["id"] == "53-21"
        return names

    names = anyio.run(run)
    assert set(names) == TOOL_NAMES
    assert len(names) == 7
    assert list(tmp_path.iterdir()) == []


# --- helpers -----------------------------------------------------------------------


def _sec(
    id: str,
    heading: str = "Heading",
    text: str = "Body text.",
    parent: str | None = "__article__",
) -> Section:
    article = id.split("-")[0].split(":")[0]
    return Section(
        id=id,
        article=article,
        heading=heading,
        text=text,
        parent=article if parent == "__article__" else parent,
        kind="section",
        source=SourceRef(file="f", anchor="a"),
    )


def _tools(tmp_path: Path, sections: list[Section], rules: list[Rule] = ()) -> Tools:
    build_search(sections, tmp_path / "search.sqlite")
    return Tools(sections, [], list(rules), tmp_path / "search.sqlite")
