from dataclasses import asdict

from app.models import Contact
from app.services.auditor import ContactCandidate


def test_contact_candidate_matches_contact_model_fields():
    payload = asdict(ContactCandidate(
        email="hello@example.com",
        email_source_url="https://example.com/contact",
        source_type="mailto",
        contact_form_url="https://example.com/contact",
        confidence=0.95,
        mx_valid=True,
    ))
    valid_fields = set(Contact.__table__.columns.keys()) - {"id", "business_id", "discovered_at"}
    assert set(payload).issubset(valid_fields)
