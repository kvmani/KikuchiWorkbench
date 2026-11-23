# KikuchiWorkbench

Desktop workbench (PySide6) and headless CLI for master-pattern-based EBSD dictionary indexing and phase
discrimination. See [the project scope](KikuchiWorkbench_Project_Scope.md), [the roadmap](ROADMAP.md) and
[the progress ledger](LEDGER.md).

Status: **early development** — not yet a release candidate. See the ledger for what is verified.

## Developer setup

```bash
python -m venv .venv
. .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest -q
```

Documentation: [conventions](docs/conventions.md).
