from app.config import get_settings
from app.schemas import SmtpSettingsRequest
from app.services.smtp import decrypt_secret, encrypt_secret


def test_smtp_secret_round_trip(monkeypatch):
    monkeypatch.setenv("APP_SECRET_KEY", "test-secret")
    get_settings.cache_clear()
    encrypted = encrypt_secret("mail-password")
    assert encrypted != "mail-password"
    assert decrypt_secret(encrypted) == "mail-password"
    get_settings.cache_clear()


def test_smtp_transport_modes_are_mutually_exclusive():
    try:
        SmtpSettingsRequest(
            host="smtp.example.com",
            port=465,
            from_email="sender@example.com",
            use_tls=True,
            use_ssl=True,
        )
    except ValueError as exc:
        assert "STARTTLS or SSL" in str(exc)
    else:
        raise AssertionError("Expected validation error")
