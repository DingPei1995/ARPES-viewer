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
- **The agent's reference (maintenance after every UI or tool change).**
  `agentic/API.md` is generated from the program: the live operations
  (`arpes_viewer/ui/common/live.py`, `L.<name>`), the tool-panel buttons
  (`ui/launcher/main_window.py` `TOOLS`), the MCP tools and the public
  functions under `arpes_viewer/tools/`. After changing any of them:
  1. if a dialog gained or changed something an agent should be able to do,
     add or update the matching operation in `ui/common/live.py` (with a
     description: it is what agents read), and a test in
     `test/agent/test_live.py`;
  2. run `python -m arpes_viewer.agent.catalog --write`;
  3. say in your reply to the user that the reference was updated (or that
     an operation is still missing for a new UI feature).
  `test/agent/test_catalog.py` fails while the file is out of date.
