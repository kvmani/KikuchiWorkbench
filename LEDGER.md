# Progress Ledger

Append-only log of work done against [ROADMAP.md](ROADMAP.md). Each entry records what changed, the evidence
(tests, commands, outputs), and any blockers or limitations. Planned features belong in the roadmap, not here.

**How to resume after an interruption:** read the latest entry's "Next" line, check `git log`, run
`pytest -q`, then continue with the first unticked roadmap item in the current phase.

---

## 2026-11-23 — Entry 1: Roadmap and ledger

- Created `ROADMAP.md` (phases 0–7 + release gate) and this ledger.
- Environment probed: Linux container, Python 3.13, 4 CPU, 15 GB RAM, no GPU/OpenCL, no Windows.
  Packages installable from PyPI: kikuchipy 0.14.2, orix 0.15.0, h5py 3.16, numpy 2.5, PySide6 6.12.
- kikuchipy ships small offline files usable in tests (not redistributed by us): Ni EMsoft master
  (`emsoft_ebsd_master_pattern`), Ni 3×3 patterns, and reader samples for Oxford `.ebsp`, EDAX `.up1/.up2`,
  EDAX H5EBSD and EMsoft simulated EBSD. These are reader test files, **not** verified real vendor exports.
- Blocker (roadmap 3.7, release gate): native Windows 11 EMsoft + OpenCL cannot run in this container.
  Continuing with master import and the headless CPU demo, as AGENTS.md directs.
- Next: Phase 0 scaffolding.
