"""Validate and bundle the final recruiter documents from an explicit allowlist."""

import hashlib
import json
import re
import shutil
import subprocess
import zipfile
from pathlib import Path

from pypdf import PdfReader

from app.main import app

ROOT = Path(__file__).resolve().parents[2]
LIVE = "https://expense-sharing-app-inda.onrender.com"
REPO = "https://github.com/manansethi1205/expense-sharing-app"
METHODS = {"get", "post", "put", "patch", "delete"}
PDFS = (
    "setup-instructions.pdf",
    "api-documentation.pdf",
    "database-schema-explanation.pdf",
)


def main():
    output = ROOT / "output"
    output.mkdir(exist_ok=True)
    source_ref = subprocess.check_output(
        ["git", "log", "-1", "--format=%h", "--", "app", "migrations", "scripts"],
        cwd=ROOT,
        text=True,
    ).strip()
    openapi = app.openapi()
    (ROOT / "docs/openapi.json").write_text(
        json.dumps(openapi, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    operations = [
        (method.upper(), path)
        for path, methods in openapi["paths"].items()
        for method in methods
        if method in METHODS
    ]
    assert len(operations) == 25

    pdf_metadata = {}
    for name in PDFS:
        reader = PdfReader(output / "pdf" / name)
        text = "\n".join(page.extract_text() for page in reader.pages)
        compact = re.sub(r"\s+", "", text)
        assert LIVE in compact, (name, "Missing live URL")
        assert source_ref in text, (name, "Stale application baseline")
        assert "c5a0a64" not in text and "83 passing tests" not in text
        if name == "api-documentation.pdf":
            for method, path in operations:
                assert method + path in compact, (method, path)
        pdf_metadata[name] = {
            "pages": len(reader.pages),
            "bytes": (output / "pdf" / name).stat().st_size,
        }

    collection_file = ROOT / "docs/expense-sharing.postman_collection.json"
    collection = json.loads(collection_file.read_text(encoding="utf-8"))
    assert len(collection["item"]) == 21
    assert all("{{base_url}}" in item["request"]["url"] for item in collection["item"])
    for name in ("Local", "Render"):
        env_file = ROOT / "docs" / f"{name}.postman_environment.json"
        env = json.loads(env_file.read_text(encoding="utf-8"))
        assert env["values"][0]["key"] == "base_url"
        assert env["values"][0]["value"] == (
            LIVE + "/api/v1" if name == "Render" else "http://localhost:8000/api/v1"
        )
        shutil.copyfile(env_file, output / env_file.name)
    shutil.copyfile(collection_file, output / collection_file.name)
    assert collection_file.read_bytes() == (output / collection_file.name).read_bytes()

    # Stable repository-relative layout keeps document links understandable offline.
    allowlist = [
        "SUBMISSION.md",
        "README.md",
        "decisions.md",
        "flow.md",
        "render.yaml",
        ".env.example",
        "docs/render.md",
        "docs/verification.md",
        "docs/ui-preview.png",
        "docs/demo.http",
        "docs/openapi.json",
        "docs/expense-sharing.postman_collection.json",
        "docs/Local.postman_environment.json",
        "docs/Render.postman_environment.json",
        "docs/tooling/README.md",
        "docs/tooling/requirements.txt",
        "docs/tooling/build_pdfs.py",
        "docs/tooling/package_submission.py",
        *("output/pdf/" + name for name in PDFS),
    ]
    entries = []
    for relative in allowlist:
        file = ROOT / relative
        assert file.is_file(), relative
        entries.append(
            {
                "path": relative,
                "bytes": file.stat().st_size,
                "sha256": hashlib.sha256(file.read_bytes()).hexdigest(),
            }
        )
    manifest = {
        "edition": "Final recruiter submission - 16 October 2026",
        "application_baseline": source_ref,
        "api_version": app.version,
        "schema_head": "0002",
        "live_demo": LIVE + "/",
        "source_repository": REPO,
        "pdfs": pdf_metadata,
        "files": entries,
    }
    encoded_manifest = json.dumps(manifest, indent=2) + "\n"
    (output / "submission-manifest.json").write_text(encoded_manifest, encoding="utf-8")
    start_here = """# Final recruiter submission

Start with [SUBMISSION.md](SUBMISSION.md) for links, the five-minute walkthrough and assignment coverage.

- [Setup Instructions](output/pdf/setup-instructions.pdf)
- [API Documentation](output/pdf/api-documentation.pdf)
- [Database Schema Explanation](output/pdf/database-schema-explanation.pdf)
- [Postman collection](docs/expense-sharing.postman_collection.json)
- [Render Postman environment](docs/Render.postman_environment.json)
- [Local Postman environment](docs/Local.postman_environment.json)
- [Deployment guide](docs/render.md)
- [Verification record](docs/verification.md)

Live demo: https://expense-sharing-app-inda.onrender.com/
Source: https://github.com/manansethi1205/expense-sharing-app

This archive contains documentation and review artifacts. Clone the source repository to run the full project; application source/dependencies are not duplicated in this document bundle. The .env.example contains synthetic local defaults, not hosted credentials. MANIFEST.json records file hashes and the application baseline. No real .env file, credential, database, log or cache is included.
"""
    prefix = "expense-sharing-final-submission/"
    archive = output / "expense-sharing-final-submission.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for relative in allowlist:
            bundle.write(ROOT / relative, prefix + relative)
        bundle.writestr(prefix + "MANIFEST.json", encoded_manifest)
        bundle.writestr(prefix + "START_HERE.md", start_here)
    with zipfile.ZipFile(archive) as bundle:
        assert bundle.testzip() is None
        assert len(bundle.namelist()) == len(allowlist) + 2
        for entry in entries:
            assert (
                hashlib.sha256(bundle.read(prefix + entry["path"])).hexdigest() == entry["sha256"]
            )
        assert not any(Path(name).name == ".env" for name in bundle.namelist())
    shutil.copyfile(archive, output / "expense-sharing-documentation.zip")

    for relative in allowlist:
        file = ROOT / relative
        if file.suffix != ".md":
            continue
        for target in re.findall(r"\]\(([^\s)]+)\)", file.read_text(encoding="utf-8")):
            if target.startswith(("http://", "https://", "#", "mailto:")):
                continue
            local = target.split("#", 1)[0]
            assert (file.parent / local).exists(), (relative, target)
    print(
        json.dumps(
            {
                "application_baseline": source_ref,
                "pdfs": pdf_metadata,
                "zip_entries": len(allowlist) + 2,
                "archive_bytes": archive.stat().st_size,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
