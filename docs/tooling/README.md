# Rebuild submission PDFs

From the repository root, install the authoring utilities without adding them to backend runtime dependencies:

```sh
uv pip install -r docs/tooling/requirements.txt
uv run --no-sync python -m docs.tooling.build_pdfs
```

`uv run --no-sync` preserves the separately installed authoring utilities; a normal `uv sync` may remove packages outside the project lock. This tooling is optional and is not needed to run the application or tests.

The generator combines authored explanations with `app.openapi()` and `Base.metadata`, writes the three PDFs under `output/pdf/`, renders every page to PNG with PyMuPDF, and creates contact sheets/text checks under ignored `tmp/pdfs/`. Review every contact sheet and any dense pages before publishing. Windows uses embedded Segoe UI/Consolas; other systems use ReportLab's bundled Vera body fonts and standard Courier for code, so recheck pagination when switching systems.

Application-baseline stamps come from the latest commit affecting app, migrations or scripts, rather than a documentation-only commit. Update verified hosting details, test counts, dated evidence and release notes in the source when they change. `docs/tooling/package_submission.py` refreshes the offline OpenAPI export, copies the collection/environments, verifies PDF coverage and links, and rebuilds both ZIP names from an explicit allowlist.
