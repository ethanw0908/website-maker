from app.services.scoring import score_lead


def test_no_website_with_strong_reputation_qualifies():
    result = score_lead(has_website=False, rating=4.7, review_count=100, has_public_contact=True)
    assert result.score == 55


def test_recent_redesign_is_penalized():
    result = score_lead(has_website=True, recently_redesigned=True)
    assert result.score == -40


def test_poor_site_accumulates_reasons():
    result = score_lead(
        has_website=True,
        reachable=False,
        mobile_responsive=False,
        outdated_visual_signals=True,
        has_call_to_action=False,
        has_service_information=False,
    )
    assert result.score == 90
    assert len(result.reasons) == 5
