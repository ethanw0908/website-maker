from pathlib import Path

import pytest
from pydantic import ValidationError

from app.main import BulkLeadActionRequest


def test_bulk_action_accepts_supported_actions():
    request = BulkLeadActionRequest(ids=[3, 3, 9], action="make_website")
    assert request.ids == [3, 3, 9]
    assert request.action == "make_website"


def test_bulk_action_rejects_empty_selection():
    with pytest.raises(ValidationError):
        BulkLeadActionRequest(ids=[], action="sold")


def test_leads_frontend_has_selection_and_floating_actions():
    html = Path("app/static/index.html").read_text(encoding="utf-8")
    assert 'id="select-all-leads"' in html
    assert 'id="bulk-actions"' in html
    assert 'id="make-website-selected"' in html
    assert "GitHub repo" in html
    assert "Vercel" in html
