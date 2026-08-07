You are the lead designer-engineer revising a site that failed quality review.

Read the full current workspace, especially:
- `_agent/brief.json`
- `_agent/RESEARCH.md`
- `_agent/DESIGN.md`
- `_agent/design_review.json`
- `_agent/screenshots/*.png`

The user's generation prompt is:
{{GENERATION_PROMPT}}

Failures:
- {{FAILURES}}

Full design review:
{{DESIGN_REVIEW}}

Fix the underlying design problems, not just superficial symptoms. You may substantially restructure sections, rewrite grounded copy, change typography, replace weak assets, create new original SVG/CSS artwork, or use available network tools for additional clearly licensed/first-party assets. Update `_agent/ASSET_MANIFEST.json` for any asset changes.

If the critique says the site feels templated, redesign the composition and information architecture rather than simply changing colours, shadows, or border radii.

Preserve all factual/preview/contact guardrails. Verify local paths and responsive behaviour before finishing.
