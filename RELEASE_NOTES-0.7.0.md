Release 0.7.0 - Highlights

- Fix: Return newest-first events from the API by default (use `sort=-date`) so real-time `AUTO_LOC` pings are not hidden behind older events.
- Fix: `Device.refresh()` now compares timestamps from both the asset `lastLocation` and the latest event and uses the freshest source (avoids relying on stale `locationLastReported`).
- Add: Diagnostic troubleshooting scripts (`scripts/poll_locations.py`, `scripts/diagnose_staleness.py`, `scripts/probe_events.py`) to help investigate API data freshness.
- Add: `scripts/credentials.py` helper for consistent and robust `.credentials` parsing and improved script error messages.
- Fix: Pre-commit hook (`.git/hooks/pre-commit`) now falls back gracefully if the venv Python is broken, allowing commits while the local venv is fixed.
- Style/Quality: Fixed linting and formatting issues; all tests now pass (105 tests) and pre-commit checks succeed locally.
- Misc: Documentation and minor refactors; improved error handling in scripts.

Notes for release tag:
- The issue where locations visible in the provider app were more recent than the integration is resolved by prioritizing newest events and comparing timestamps.
- Recommended next step for maintainers: consider monitoring the `/assets/{id}/events` responses for event type distribution (e.g., `AUTO_LOC` frequency) and consider exposing a configuration to prefer `AUTO_LOC` events explicitly if provider behavior changes.
