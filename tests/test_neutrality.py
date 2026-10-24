from __future__ import annotations

from auditor.neutrality import flags


def test_flags_should_in_a_claim():
    assert flags("The applicant should provide a buffer.") == ["should"]


def test_no_flag_when_should_is_only_inside_a_quote():
    assert flags('Section 53-4 says "each lot should provide a buffer".') == []


def test_flags_outside_but_not_inside_the_same_sentence():
    assert flags('It recommends a change, though the code only says "density limits apply".') == ["recommend"]


def test_multiple_distinct_terms_in_order_without_repeats():
    assert flags("This is better and density is better than worse.") == ["better", "density", "worse"]


def test_clean_claim_has_no_flags():
    assert flags("Section 53-8 is titled Regulations Applicable on Tidelands.") == []
