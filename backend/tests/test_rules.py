from app.services import rules


def test_completeness_and_validation():
    full = {f: 1 for f in rules.NUMERIC_FIELDS}
    assert rules.completeness(full) == 100
    assert rules.completeness({}) == 0
    assert rules.validate_activity("Draft", {"diesel": 10**9}) == ("Not Run", [])
    assert rules.validate_activity("Submitted", {"diesel": 250_001})[0] == "Warnings"
    assert rules.validate_activity("Submitted", {"diesel": 250_000})[0] == "Passed"


def test_initiative_progress_matches_original_ui_formula():
    r = rules.advance_initiative(expected_reduction=8400, completion=95, timeline="At Risk", step=10)
    assert r == {"completion": 100, "status": "Completed", "timeline": "Complete"}  # actual reduction is never invented
    assert rules.js_round(2.5) == 3  # JS half-up, not Python banker's rounding
