You are recovering a website build that exited without leaving a publishable `index.html` at the workspace root.

Read the existing studio artefacts before doing anything:
- `_agent/brief.json`
- `_agent/RESEARCH.md`
- `_agent/DESIGN.md`
- `_agent/ASSET_PLAN.md`
- `_agent/ASSET_MANIFEST.json`

User generation prompt:
{{GENERATION_PROMPT}}

Previous builder output, for diagnosis only:
{{PREVIOUS_OUTPUT}}

Do not discuss the failure. Fix it.

You are currently inside the publishable website root. Use filesystem write tools to create the actual site now.

Mandatory recovery contract:
1. Create a complete, non-empty `./index.html` directly in the current working directory.
2. Do not place the finished site under `site/`, `public/`, `dist/`, `build/`, `src/`, or another wrapper directory.
3. Create the CSS/JS/assets needed to execute `_agent/DESIGN.md` with high visual quality.
4. Use only grounded business facts from the brief/research.
5. Preserve the preview, accessibility, noindex/nofollow, contact, asset-licensing, and no-data-collection guardrails from the original build instructions.
6. Before finishing, verify `index.html` exists and is non-empty and inspect the resulting file tree.

Do not return until actual website files have been written to disk.
