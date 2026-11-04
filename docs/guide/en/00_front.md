# ARPES viewer — User Guide

*[中文版 / Chinese version](../../USER_GUIDE_zh.md) · [Version française](../../USER_GUIDE_fr.md)*

*Last updated: 4 November 2026 — for ARPES viewer v1.3.2*

The version and its date are in the main window's title bar and on its last
line. Bug reports, questions and the latest version:
<https://github.com/DingPei1995/ARPES-viewer> (please give the version
number when reporting a bug).

The guide follows the program as it appears on screen:

- **Part 1** gets you started: installing, the demo data, the files the
  program reads, setting up an AI agent, and how the code is organised.
- **Part 2** is the main panel: the list of datasets and what is around it.
- **Part 3** is the data viewers: cuts, maps, kz maps, k-maps, curves, spin
  and spatially resolved scans.
- **Parts 4, 5 and 6** are the three tabs of the tool panel (**Basic**,
  **Advanced**, **Figure**). Part 6 ends with an example that goes from
  loading data to a finished figure.
- **Part 7** is AI agents: how they drive the program, how to start and
  watch one, and an example from set-up to figure.
- **Part 8** is housekeeping: autosave and recovery, saving work, error
  logs, versions, and troubleshooting.

Every screenshot was taken from the running program on the synthetic data
of `devtools/demo_data.py`, so you can follow along without a beamtime
([§1.3](#13-trying-it-with-demo-data)). **These are not real experimental
data.** The technical background of each step (formulas, tests, design
choices) is in the references beside the code:
[reading data](../../../arpes_viewer/loader/README.md),
[the windows](../../../arpes_viewer/ui/README.md),
[analysis](../../../arpes_viewer/tools/README.md), and the
[CHANGELOG](../../../CHANGELOG.md).

<!-- contents -->
