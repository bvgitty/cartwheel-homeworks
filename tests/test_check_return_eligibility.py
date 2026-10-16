"""Tests for the student-added check_return_eligibility tool (HW1 own tool)."""

from agent.auth import AuthContext
from agent.tools import check_return_eligibility

SUPPORT = AuthContext(user_id=9501, role="support")
SHOPPER_1 = AuthContext(user_id=1, role="shopper")


def test_eligible_order_has_deadline():
    r = check_return_eligibility(SHOPPER_1, 4127)
    assert r["ok"] is True
    assert r["eligible"] is True
    assert r["deadline"] == "2026-07-19"
    assert r["policy_id"] == "cw-returns"


def test_expired_order_is_not_eligible():
    r = check_return_eligibility(SHOPPER_1, 3980)
    assert r["eligible"] is False
    assert r["days_left"] < 0


def test_reversed_dates_are_flagged_not_guessed():
    r = check_return_eligibility(SUPPORT, 8001)
    assert r["eligible"] is None
    assert r["deadline"] is None
    assert r["data_issues"]


def test_missing_delivery_date_is_flagged():
    r = check_return_eligibility(SUPPORT, 8002)
    assert r["eligible"] is None
    assert "delivered_at is missing" in r["data_issues"][0]


def test_shopper_cannot_check_someone_elses_order():
    r = check_return_eligibility(SHOPPER_1, 8001)
    assert r["ok"] is False
    assert r["error"] == "permission_denied"


def test_unknown_order_is_not_found():
    r = check_return_eligibility(SUPPORT, 999999)
    assert r["error"] == "not_found"