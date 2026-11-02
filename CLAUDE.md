# Notes for coding agents

- **Changelog.** `CHANGELOG.md` keeps one entry per release only within the
  current minor version. When a change starts a new minor version (for
  example 1.2.5 → 1.3.0), merge all entries of the previous minor version
  into one simplified summary headed `## 1.2 — 1.2.0 to 1.2.5, <first
  date> to <last date>`, placed after the new entry and before the older
  summaries. See *Versions and the changelog* in `docs/DEVELOPER.md`.
- **Version.** Bump `arpes_viewer/version.py` and the places
  `test/test_version_consistency.py` checks together.
- **Tests.** `python -m pytest` from the repository root, before pushing.
