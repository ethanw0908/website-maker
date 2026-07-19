from app.models import WebsiteAudit


def test_website_audit_maps_metadata_column_without_reserved_attribute():
    assert "metadata" in WebsiteAudit.__table__.c
    assert hasattr(WebsiteAudit, "audit_metadata")
