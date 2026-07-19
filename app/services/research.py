from app.models import Business, WebsiteAudit


def build_research_brief(business: Business, audit: WebsiteAudit | None) -> dict:
    contact = business.contacts[0] if business.contacts else None
    return {
        "company": {
            "name": business.name,
            "industry": business.category,
            "address": business.address,
            "city": business.city,
            "phone": business.phone,
            "website": business.website_url,
            "rating": business.rating,
            "review_count": business.review_count,
            "public_email": contact.email if contact else None,
            "contact_form": contact.contact_form_url if contact else None,
        },
        "audit": {
            "reachable": audit.reachable if audit else False,
            "mobile_responsive": audit.mobile_responsive if audit else False,
            "has_call_to_action": audit.has_call_to_action if audit else False,
            "has_service_information": audit.has_service_information if audit else False,
            "metadata": audit.audit_metadata if audit else {},
        },
        "requirements": {
            "pages": ["Home", "About", "Services", "Contact"],
            "mobile_first": True,
            "wcag_target": "WCAG 2.2 AA where practical",
            "preview_only": True,
            "noindex": True,
            "do_not_invent": [
                "awards",
                "testimonials",
                "employee names",
                "certifications",
                "prices",
                "years in business",
                "guarantees",
                "licence numbers",
                "service areas",
            ],
        },
    }
