import base64
import hashlib
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings
from app.models import EmailDraft, SmtpAccount


def _fernet() -> Fernet:
    settings = get_settings()
    secret = settings.app_secret_key or settings.admin_api_key
    if not secret or secret == "change-me-with-openssl-rand-hex-32":
        raise RuntimeError("Set a unique APP_SECRET_KEY before saving SMTP credentials")
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_secret(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return _fernet().decrypt(value.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise RuntimeError("SMTP password cannot be decrypted. Restore the APP_SECRET_KEY used when it was saved.") from exc


def _connect(account: SmtpAccount):
    context = ssl.create_default_context()
    if account.use_ssl:
        client = smtplib.SMTP_SSL(account.host, account.port, timeout=25, context=context)
    else:
        client = smtplib.SMTP(account.host, account.port, timeout=25)
        client.ehlo()
        if account.use_tls:
            client.starttls(context=context)
            client.ehlo()

    if account.username:
        password = decrypt_secret(account.encrypted_password)
        if not password:
            client.quit()
            raise RuntimeError("SMTP password is missing")
        client.login(account.username, password)
    return client


def test_smtp(account: SmtpAccount) -> None:
    if not account.enabled:
        raise RuntimeError("SMTP is disabled")
    client = _connect(account)
    try:
        code, response = client.noop()
        if code >= 400:
            raise RuntimeError(f"SMTP server returned {code}: {response!r}")
    finally:
        client.quit()


def send_draft(account: SmtpAccount, draft: EmailDraft) -> None:
    if not account.enabled:
        raise RuntimeError("SMTP is disabled")
    message = EmailMessage()
    message["From"] = formataddr((account.from_name or "", account.from_email))
    message["To"] = draft.recipient
    message["Subject"] = draft.subject
    message["Reply-To"] = account.unsubscribe_email or account.from_email
    message.set_content(draft.body)

    client = _connect(account)
    try:
        client.send_message(message)
    finally:
        client.quit()
