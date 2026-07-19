from dataclasses import dataclass

from app.models import Business, WebsiteAudit


@dataclass(frozen=True)
class DraftContent:
    subject: str
    body: str


def build_outreach_draft(*, business: Business, audit: WebsiteAudit | None, preview_url: str,
                         sender_name: str, sender_business: str, sender_address: str,
                         unsubscribe_email: str) -> DraftContent:
    observation = "I noticed your business does not currently list a website on Google."
    improvement = "The concept makes your core services, contact details, and mobile call-to-action easier to find."
    if audit:
        if not audit.mobile_responsive:
            observation = "I noticed the current site is difficult to use on a phone."
            improvement = "The concept uses a responsive layout and keeps the main contact action visible on smaller screens."
        elif not audit.has_call_to_action:
            observation = "I noticed the current site does not make the next step especially clear."
            improvement = "The concept adds a direct, prominent contact action while preserving the existing business information."

    subject = f"Private website concept for {business.name}"
    body = f"""Hello {business.name} team,

{observation} {improvement}

I prepared a private, unsolicited concept for review:
{preview_url}

This is only a design concept and is not your official website. Nothing is published under your business's domain, and the preview does not accept bookings, payments, or customer information.

Would it be useful to discuss what you would change before considering anything further?

{sender_name}
{sender_business}
{sender_address}

To stop receiving messages from me, reply with “unsubscribe” or email {unsubscribe_email}.
"""
    return DraftContent(subject=subject, body=body)
