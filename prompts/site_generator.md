You are the lead designer-engineer. Build the complete website from a blank canvas.

Read these first:
- `_agent/brief.json`
- `_agent/RESEARCH.md`
- `_agent/DESIGN.md`
- `_agent/ASSET_PLAN.md`
- `_agent/ASSET_MANIFEST.json`

The user's generation prompt is:
{{GENERATION_PROMPT}}

The research and creative direction are inputs, not a template. Execute the design with the level of craft expected from a strong human web designer.

Implementation rules:
- Start from the current blank site workspace; do not reuse a generic site template.
- Build a static, Vercel-deployable site using semantic HTML5, modern CSS, and small vanilla JavaScript where useful.
- `index.html` is required. Choose any additional pages only when the information architecture justifies them.
- You decide the section structure, layout, typography, visual motifs, and interactions.
- Use the acquired local assets deliberately. You may use available network tools to obtain an additional clearly licensed or first-party asset if the design truly needs it; update `_agent/ASSET_MANIFEST.json` when you do.
- Keep factual copy grounded in `_agent/brief.json` and `_agent/RESEARCH.md`. Never invent awards, testimonials, employee names, prices, years in business, guarantees, certifications, licences, service areas, or other unsupported claims.
- Use `tel:` only for the verified phone and `mailto:` only for the verified public email.
- Do not create a functioning form that collects customer data. A visual form concept must be non-submitting and clearly disabled.
- Every HTML page must contain robots metadata with both `noindex` and `nofollow`.
- Include JSON-LD LocalBusiness data using verified fields only when appropriate.
- Include the exact phrase "Unofficial concept preview" discreetly in the footer or equivalent.
- Create `robots.txt`, `sitemap.xml`, `README.md`, and `vercel.json`.
- All local links and asset paths must resolve.
- Responsive behaviour must be polished at 390 px, 768 px, 1280 px, and 1440 px.
- Include visible keyboard focus states, adequate contrast, semantic landmarks, alt text, and reduced-motion support.
- Avoid template fingerprints: repetitive equal cards, excessive border radius, default Tailwind/SaaS composition, generic stock-person imagery, excessive gradients, glassmorphism, fake dashboards, counters, and decorative clutter.
- Prefer a few strong visual decisions over many generic components.
- The site should look materially different from other local-business sites even if only the business name were removed.

Before finishing, inspect the complete site in source, verify paths, and make a final polish pass. Do not merely satisfy the checklist.
