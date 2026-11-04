# The user guide's sources

The user guides `docs/USER_GUIDE_<lang>.md` are **assembled** from the files
here; edit these, not the assembled guides.

```
docs/guide/<lang>/00_front.md            title, version line, introduction (<!-- contents --> marks the table of contents)
docs/guide/<lang>/01_getting_started.md  Part 1
docs/guide/<lang>/02_main_panel.md       Part 2
docs/guide/<lang>/03_viewers.md          Part 3
docs/guide/<lang>/04_basic_tab.md        Part 4
docs/guide/<lang>/05_advanced_tab.md     Part 5
docs/guide/<lang>/06_figure_tab.md       Part 6
docs/guide/<lang>/07_ai_agents.md        Part 7
docs/guide/<lang>/08_housekeeping.md     Part 8
```

- Each part starts with `# Part N — …`; its sections are `## N.M Title`
  (the table of contents is made from these). Sub-headings are `###`.
- The three languages keep the same files and the same section numbers (a
  test checks it).
- Write links as from this folder: pictures `../../images/x.png`, the code
  `../../../arpes_viewer/...`, other sections by their GitHub anchor
  (`#42-fermi-edge-fit`).

After editing:

```bash
python devtools/build_guide.py            # assemble docs/USER_GUIDE_{en,zh,fr}.md
python devtools/build_guide_pdfs.py       # print docs/pdf/*.pdf (pandoc + Playwright)
python devtools/guide_screenshots.py      # only when a window changed: re-take docs/images/
```

`test/test_user_guide.py` fails when an assembled guide is out of date, or
when a link or picture in it leads nowhere.
