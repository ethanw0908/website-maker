You are creating a private, unindexed website concept for a real local business.

Use only the verified information in the JSON brief. Do not invent awards, testimonials, employee names, prices, years in business, guarantees, certifications, licences, locations, service areas, or claims.

Design requirements:
- Build a bespoke visual system appropriate to this exact industry and company; do not reuse a generic SaaS layout.
- Use semantic HTML5, modern CSS, CSS custom properties, and small vanilla JavaScript only.
- Produce responsive, polished layouts at 390 px, 768 px, 1280 px, and 1440 px widths.
- Use accessible colour contrast, visible focus states, keyboard-operable navigation, labelled forms, and reduced-motion support.
- Keep the text concise and factual.
- Use `tel:` only when a verified phone number is present. Use `mailto:` only when a verified public email is present.
- If neither a phone nor public email is verified, show the verified address, website, or Google Maps information instead; do not invent a contact action.
- Do not add a functioning lead form; a form may be a non-submitting visual concept clearly marked as disabled.
- Every HTML page must include robots metadata containing both `noindex` and `nofollow`. Attribute order and quote style do not matter.
- Include JSON-LD LocalBusiness data containing only verified fields.
- Avoid excessive gradients, glassmorphism, floating cards, fake dashboards, animated counters, generic AI wording, and decorative clutter.
- Use the phrase “Unofficial concept preview” for any disclaimer. Do not claim endorsement or ownership by the business.

Required files:
index.html
about.html
services.html
contact.html
assets/css/styles.css
assets/js/main.js
robots.txt
sitemap.xml
README.md
vercel.json

The README must state that this is an unofficial, unsolicited concept preview. The site must not accept bookings, payments, or customer data.

Company brief:
{{BRIEF_JSON}}

Create the complete site directly in the current directory. Verify all local links and paths before finishing.
