<!-- Branch flow: feat/* | fix/* | chore/* → develop, and only develop → main. -->

## What & why

<!-- What does this change do, and what problem does it solve? Link issues with "Closes #123". -->

## How to verify

<!-- Commands run, manual steps, screenshots of the rendered PDF, or sample API output. -->

## Checklist

- [ ] Target branch is correct (feature branch → `develop`; `develop → main` only)
- [ ] `make ci` passes (ruff, cspell, mypy, pytest)
- [ ] `models.py` changed → ran `make schema` and included `schema/*.schema.json`
- [ ] Web form changed (`web/`, `index.html`, `app.js`) → ran `make web-assets` and included `web_static/assets/`
- [ ] Layout changes stay ATS-safe: single column, no tables, text boxes or floats
- [ ] Validation still fails loudly (bad payloads → `422`); no security layer weakened
- [ ] README / docs updated if behavior, the data format or the API changed
- [ ] No secrets, `.env` values or unintended personal data committed
