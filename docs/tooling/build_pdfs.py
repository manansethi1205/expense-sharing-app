"""Author the three submission guides from the current API and ORM metadata."""

import html
import json
import re
import shutil
import subprocess
from pathlib import Path

import pymupdf
import reportlab
from PIL import Image, ImageDraw
from pypdf import PdfReader
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    HRFlowable,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Preformatted,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus import (
    Image as DocumentImage,
)
from reportlab.platypus.tableofcontents import TableOfContents

from app.main import app
from app.models import Base

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output" / "pdf"
TMP = ROOT / "tmp" / "pdfs"
OUT.mkdir(parents=True, exist_ok=True)
TMP.mkdir(parents=True, exist_ok=True)
REF = subprocess.check_output(
    ["git", "log", "-1", "--format=%h", "--", "app", "migrations", "scripts"], cwd=ROOT, text=True
).strip()
DATE = "16 October 2026"
REPO = "https://github.com/manansethi1205/expense-sharing-app"
LIVE = "https://expense-sharing-app-inda.onrender.com"
CI = "https://github.com/manansethi1205/expense-sharing-app/actions/runs/38897558178"
OPENAPI = app.openapi()
NAVY, TEAL, INK = (colors.HexColor(value) for value in ("#112D43", "#087F8C", "#233747"))
PALE, LINE, MUTED = (colors.HexColor(value) for value in ("#F0F6F8", "#D9E4E9", "#526775"))
W, H = A4
MARGIN = 43
WIDTH = W - 2 * MARGIN
windows_fonts = Path("C:/Windows/Fonts")
if (windows_fonts / "segoeui.ttf").exists():
    font_files = [
        (name, windows_fonts / filename)
        for name, filename in (
            ("Body", "segoeui.ttf"),
            ("BodyBold", "segoeuib.ttf"),
            ("BodyItalic", "segoeuii.ttf"),
            ("Mono", "consola.ttf"),
        )
    ]
else:
    font_root = Path(reportlab.__file__).parent / "fonts"
    font_files = [
        (name, font_root / filename)
        for name, filename in (
            ("Body", "Vera.ttf"),
            ("BodyBold", "VeraBd.ttf"),
            ("BodyItalic", "VeraIt.ttf"),
        )
    ]
    pdfmetrics.registerFont(pdfmetrics.Font("Mono", "Courier", "WinAnsiEncoding"))
for name, filename in font_files:
    pdfmetrics.registerFont(TTFont(name, str(filename)))
pdfmetrics.registerFontFamily(
    "Body", normal="Body", bold="BodyBold", italic="BodyItalic", boldItalic="BodyBold"
)

styles = getSampleStyleSheet()
for name, options in {
    "BodyText": dict(fontName="Body", fontSize=10, leading=14.5, textColor=INK, spaceAfter=8),
    "H1": dict(
        fontName="BodyBold",
        fontSize=21,
        leading=26,
        textColor=NAVY,
        spaceAfter=14,
        keepWithNext=True,
    ),
    "H2": dict(
        fontName="BodyBold",
        fontSize=12.3,
        leading=17,
        textColor=TEAL,
        spaceBefore=11,
        spaceAfter=6,
        keepWithNext=True,
    ),
    "H3": dict(
        fontName="BodyBold",
        fontSize=10.5,
        leading=15,
        textColor=NAVY,
        spaceBefore=8,
        spaceAfter=5,
        keepWithNext=True,
    ),
    "Small": dict(fontName="Body", fontSize=8.4, leading=12, textColor=MUTED, spaceAfter=6),
    "Cell": dict(
        fontName="Body",
        fontSize=8.3,
        leading=11.5,
        textColor=INK,
        spaceAfter=0,
        splitLongWords=True,
    ),
    "HeadCell": dict(
        fontName="BodyBold", fontSize=8.3, leading=11.5, textColor=colors.white, spaceAfter=0
    ),
    "Code": dict(
        fontName="Mono",
        fontSize=7.7,
        leading=10.4,
        textColor=INK,
        backColor=PALE,
        borderPadding=9,
        spaceBefore=5,
        spaceAfter=12,
    ),
    "CoverTitle": dict(fontName="BodyBold", fontSize=33, leading=39, textColor=NAVY, spaceAfter=15),
    "CoverSub": dict(fontName="Body", fontSize=13, leading=19, textColor=MUTED, spaceAfter=18),
    "Kicker": dict(fontName="BodyBold", fontSize=9, leading=13, textColor=TEAL, spaceAfter=12),
    "TOC0": dict(
        fontName="Body",
        fontSize=10.5,
        leading=22,
        textColor=INK,
        leftIndent=0,
        firstLineIndent=0,
        spaceBefore=4,
    ),
}.items():
    if name in styles:
        for key, value in options.items():
            setattr(styles[name], key, value)
    else:
        styles.add(ParagraphStyle(name, alignment=TA_LEFT, **options))


def clean(text):
    return str(text).replace("\u2011", "-").replace("\u2013", "-").replace("\u2014", "-")


def p(text, style="BodyText"):
    return Paragraph(clean(text), styles[style])


def code(text):
    text = clean(text).strip("\n")
    longest = max(
        (pdfmetrics.stringWidth(line, "Mono", 7.7) for line in text.splitlines()), default=0
    )
    if longest > WIDTH - 20:
        raise ValueError(f"Code line too wide ({longest:.0f}pt): {text[:150]}")
    return Preformatted(text, styles["Code"])


def js(value):
    def pretty(node, indent=0):
        inline = json.dumps(node, ensure_ascii=False, separators=(",", ":"))
        if pdfmetrics.stringWidth(" " * indent + inline, "Mono", 7.7) < WIDTH - 30:
            return inline
        if isinstance(node, dict):
            parts = []
            for key, val in node.items():
                prefix = json.dumps(key) + ": "
                rendered = pretty(val, indent + 2 + len(prefix))
                parts.append(" " * (indent + 2) + prefix + rendered)
            return "{\n" + ",\n".join(parts) + "\n" + " " * indent + "}"
        if isinstance(node, list):
            return (
                "[\n"
                + ",\n".join(" " * (indent + 2) + pretty(val, indent + 2) for val in node)
                + "\n"
                + " " * indent
                + "]"
            )
        return inline

    return code(pretty(value))


def table(headers, rows, widths=None):
    data = [[p(html.escape(clean(value)), "HeadCell") for value in headers]]
    for row in rows:
        data.append([p(html.escape(clean(value)).replace("\n", "<br/>"), "Cell") for value in row])
    t = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
                ("LINEBELOW", (0, 0), (-1, 0), 0.7, TEAL),
                ("LINEBELOW", (0, 1), (-1, -1), 0.3, LINE),
            ]
        )
    )
    return t


def note(title, text):
    t = Table([[p(title, "H3")], [p(text)]], colWidths=[WIDTH], hAlign="LEFT")
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), PALE),
                ("BOX", (0, 0), (-1, -1), 0.5, LINE),
                ("LINEBEFORE", (0, 0), (0, -1), 3, TEAL),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, 0), 4),
                ("BOTTOMPADDING", (0, -1), (-1, -1), 6),
            ]
        )
    )
    return KeepTogether([Spacer(1, 4), t, Spacer(1, 10)])


class Guide(BaseDocTemplate):
    def __init__(self, filename, label):
        super().__init__(
            str(filename),
            pagesize=A4,
            leftMargin=MARGIN,
            rightMargin=MARGIN,
            topMargin=49,
            bottomMargin=43,
            title=label + " - Expense Sharing App",
            author="Expense Sharing App",
            subject="Assignment submission documentation",
            allowSplitting=True,
        )
        self.label = label
        self.addPageTemplates(
            PageTemplate(
                id="guide",
                frames=[
                    Frame(
                        MARGIN,
                        43,
                        WIDTH,
                        H - 92,
                        leftPadding=0,
                        rightPadding=0,
                        topPadding=0,
                        bottomPadding=0,
                    )
                ],
                onPage=self.decorate,
            )
        )

    def decorate(self, canvas, doc):
        canvas.saveState()
        canvas.setFillColor(TEAL)
        canvas.rect(0, H - 7, W, 7, fill=1, stroke=0)
        canvas.setFont("BodyBold", 8)
        canvas.setFillColor(NAVY)
        canvas.drawString(MARGIN, H - 29, "EXPENSE SHARING APP")
        canvas.setFont("Body", 8)
        canvas.setFillColor(MUTED)
        canvas.drawRightString(W - MARGIN, H - 29, self.label)
        canvas.setStrokeColor(LINE)
        canvas.line(MARGIN, 31, W - MARGIN, 31)
        canvas.setFont("Body", 7.6)
        canvas.drawString(MARGIN, 19, f"{DATE}  |  Code {REF}  |  API 0.1.0 / schema 0002")
        canvas.drawRightString(W - MARGIN, 19, f"Page {doc.page}")
        canvas.restoreState()

    def afterFlowable(self, flowable):
        if isinstance(flowable, Paragraph) and flowable.style.name == "H1":
            title = flowable.getPlainText()
            key = "section-" + re.sub(r"[^a-z0-9]", "-", title.lower())
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(title, key, level=0)
            self.notify("TOCEntry", (0, title, self.page, key))


def cover(number, title, subtitle, purpose, contents):
    story = [
        Spacer(1, 47),
        p(f"ENGINEERING DOCUMENTATION / {number}", "Kicker"),
        p(title, "CoverTitle"),
        p(subtitle, "CoverSub"),
        HRFlowable(width=WIDTH, thickness=2, color=TEAL),
        Spacer(1, 23),
        p(purpose),
        Spacer(1, 12),
        table(
            ["Document reference", "Value"],
            [
                ("Project", "Expense Sharing App / Fairshare UI"),
                ("Edition", "Final recruiter submission"),
                ("Prepared", DATE),
                ("Application baseline", REF),
                ("API / schema", "0.1.0 / Alembic head 0002"),
                ("Currency / default timezone", "INR / Asia/Kolkata"),
            ],
            [160, WIDTH - 160],
        ),
        Spacer(1, 18),
        p("Inside this guide", "H2"),
    ]
    story.extend(p(f"- {item}") for item in contents)
    story.extend(
        [
            Spacer(1, 10),
            p(
                f'<b>Verified Render demo:</b> <link href="{LIVE}/" color="#087F8C">{LIVE}/</link>',
                "Small",
            ),
            p(
                f'<b>Source repository:</b> <link href="{REPO}" color="#087F8C">{REPO}</link>',
                "Small",
            ),
            p(
                "Live UI and API verified on 16 October 2026. Free hosting can sleep; the free database expires 30 days after creation. Shared synthetic data only.",
                "Small",
            ),
            p(
                "Examples use synthetic data. IDs shown in worked examples are illustrative; use IDs returned by your own requests.",
                "Small",
            ),
            PageBreak(),
            p("Contents", "H2"),
        ]
    )
    toc = TableOfContents()
    toc.levelStyles = [styles["TOC0"]]
    story.extend([toc, PageBreak()])
    return story


def section(story, title, first=False):
    if not first:
        story.append(PageBreak())
    story.append(p(title, "H1"))


def build(name, label, story):
    Guide(OUT / name, label).multiBuild(story)


def setup_guide():
    s = cover(
        "01",
        "Setup Instructions",
        "Install, run, verify, and review the backend.",
        "A practical guide for an evaluator or developer starting from a fresh checkout. It explains the shortest Docker path, the local Python alternative, environment settings, migrations, test isolation, and the Postman workflow.",
        [
            "Verified Render demo and recruiter walkthrough",
            "Docker and local Python setup",
            "Render configuration, migrations and troubleshooting",
            "Tests, Postman and final handoff",
        ],
    )
    section(s, "1. Review the live Render demo", True)
    s += [
        p(
            "No local installation is needed to review the deployed application. The Fairshare browser UI calls the real FastAPI endpoints and displays saved PostgreSQL data."
        ),
        table(
            ["Resource", "Verified URL"],
            [
                ("Browser demo", LIVE + "/"),
                ("Swagger UI", LIVE + "/docs"),
                ("OpenAPI contract", LIVE + "/openapi.json"),
                ("Database readiness", LIVE + "/health/ready"),
                ("Public source", REPO),
            ],
            [115, WIDTH - 115],
        ),
        p("Five-minute review", "H2"),
        p(
            "1. Open the demo and select Goa Trip (demo). If the free service is waking up, allow roughly a minute before retrying."
        ),
        p(
            "2. Review total spending and switch the personal-view selector between Mohit, Rahul and Ankit. Compare a person's allocated share with bills they actually paid."
        ),
        p(
            "3. Open Expenses and inspect View split. Category inference is explainable and can be corrected manually."
        ),
        p(
            "4. Choose Create a fresh demo trip before experimenting. It creates a separate group through normal API calls, preserving other reviewers' trip history."
        ),
        p(
            "5. In the fresh group, add an expense or try custom shares, then open Settle up and record a synthetic partial repayment. Refreshing the view shows the new debt and payment history."
        ),
        p("Expected seeded scenario", "H2"),
        table(
            ["Bill", "Paid by", "Amount (INR)"],
            [
                ("Dinner", "Mohit", "1,200.00"),
                ("Taxi to beach", "Rahul", "600.00"),
                ("Hotel stay", "Mohit", "3,000.00"),
            ],
            [210, 135, WIDTH - 345],
        ),
        p(
            "Total spending is INR 4,800.00, with INR 1,600.00 allocated to each member. Mohit paid INR 4,200.00 and receives INR 2,600.00. Rahul owes INR 1,000.00; Ankit owes INR 1,600.00. These are starting-state expectations; shared reviewer changes may alter an existing group. A fresh demo trip recreates the initial scenario."
        ),
        note(
            "Demo scope and lifetime",
            "The demo has no authentication and contains synthetic shared data. Repayments are records, not real money movement. The free web service can sleep after inactivity, and the free PostgreSQL database expires 30 days after its creation. These hosting limits do not affect running the project locally.",
        ),
    ]
    s += [
        PageBreak(),
        p("Live dashboard: actual saved results", "H2"),
        p(
            f'This screenshot was captured from <link href="{LIVE}/" color="#087F8C">the deployed Render application</link> on 16 October 2026. It shows the seeded trip after migrations and sample data were verified.'
        ),
        DocumentImage(str(ROOT / "docs/ui-preview.png"), width=WIDTH, height=WIDTH * 1020 / 1265),
        Spacer(1, 12),
        p(
            "Mohit's personal view shows INR 1,600.00 consumption, INR 4,200.00 bills paid and INR 2,600.00 receivable. The group category totals and all three net positions come from the same saved expense/share/settlement ledger. The screenshot captures a starting state; later shared reviewer activity may change the live display."
        ),
    ]
    section(s, "2. Choose a local setup path")
    s += [
        p(
            "Use Docker for the quickest reproducible review. It runs PostgreSQL, a one-shot migration container, and a nonroot API container. Use local Python when editing or debugging application code; PostgreSQL is still required."
        ),
        table(
            ["Path", "Prerequisites", "Best use"],
            [
                (
                    "Docker",
                    "Git; Docker Engine/Desktop running; Compose v2; internet for first build",
                    "Review the complete service without installing Python dependencies on the host",
                ),
                (
                    "Local Python",
                    "Git; Python 3.12+; uv; PostgreSQL 17 or the supplied Docker DB",
                    "Edit code, use reload, run tests and migration tools",
                ),
            ],
            [77, 218, WIDTH - 295],
        ),
        p("Repository checkout", "H2"),
        code(
            "git clone https://github.com/manansethi1205/expense-sharing-app.git\ncd expense-sharing-app"
        ),
        p(
            "All commands in this guide run from that repository directory. Commands contain no prompt prefix, so they can be copied directly. Docker must be available to the same operating-system user executing the commands."
        ),
        p("What you receive", "H2"),
        table(
            ["Location", "Purpose"],
            [
                (
                    "app/",
                    "FastAPI routes, validation, business services, SQL reports and pure accounting functions",
                ),
                ("migrations/", "Alembic schema revisions 0001 and 0002"),
                ("tests/", "Unit tests and real PostgreSQL integration tests"),
                ("docs/", "Postman collection, plain HTTP walkthrough and verification record"),
                (
                    "README.md / decisions.md / flow.md",
                    "Project overview, reasoning/tradeoffs and actual code call flows",
                ),
            ],
            [180, WIDTH - 180],
        ),
        note(
            "Assignment scope",
            "This is an INR-only backend demo without authentication. Use synthetic data. The service records external cash/UPI/bank payments; it does not send money or verify bank receipts.",
        ),
    ]
    section(s, "3. Run the Docker stack")
    s += [
        p("Start the services and wait for readiness", "H2"),
        code("docker compose up --build -d --wait --wait-timeout 120\ndocker compose ps"),
        p(
            "The first build downloads the Python base image and locked packages. Later builds reuse unchanged layers. The database health check must pass before migrations run; the API starts only after migration completion."
        ),
        table(
            ["Service", "Expected state", "Meaning"],
            [
                ("db", "Running / healthy", "PostgreSQL is accepting connections"),
                (
                    "migrate",
                    "Exited with code 0",
                    "alembic upgrade head completed; exit is expected",
                ),
                ("api", "Running / healthy", "The API can query its database"),
            ],
            [65, 155, WIDTH - 220],
        ),
        p("Open the review tools", "H2"),
        table(
            ["URL", "Purpose"],
            [
                (
                    "http://localhost:8000/docs",
                    "Swagger UI: inspect contracts and execute requests",
                ),
                ("http://localhost:8000/redoc", "Alternative human-readable API reference"),
                ("http://localhost:8000/openapi.json", "Machine-readable OpenAPI contract"),
                ("http://localhost:8000/health/live", "Process liveness; no database query"),
                (
                    "http://localhost:8000/health/ready",
                    "Database connectivity check; 503 if unavailable",
                ),
            ],
            [238, WIDTH - 238],
        ),
        p("Seed synthetic trip data", "H2"),
        code("docker compose exec api python -m scripts.seed_demo"),
        p(
            "The first seed run returns actual IDs for Mohit, Rahul, Ankit and Goa Trip (demo). It records Dinner, Taxi to beach, and Hotel stay, so it demonstrates multiple payers and categories. Running it again returns the existing demo group's ID rather than duplicating it. These three expenses mean its balances differ from the single-dinner example in the API guide."
        ),
        note(
            "Ports and persistence",
            "Published ports bind to localhost: API 8000, database 5432. A named volume preserves application data when containers stop. docker compose down stops/removes the project containers while keeping that volume; it is not a database reset.",
        ),
    ]
    section(s, "4. Develop with local Python")
    s += [
        p(
            'Install Python 3.12+ and <link href="https://docs.astral.sh/uv/" color="#087F8C">uv</link>, then create the locked project environment:'
        ),
        code("uv sync --locked"),
        p("Create a local environment file", "H2"),
        p("PowerShell:"),
        code("Copy-Item .env.example .env"),
        p("macOS/Linux or a POSIX shell:"),
        code("cp .env.example .env"),
        p(
            "Keep .env local; it is ignored by Git. Start only the supplied database service, or point DATABASE_URL at a separately created development PostgreSQL database:"
        ),
        code(
            "docker compose up -d --wait db\nuv run alembic upgrade head\nuv run python -m scripts.seed_demo\nuv run uvicorn app.main:app --reload"
        ),
        p("Expected result", "H2"),
        p(
            "Uvicorn listens on localhost:8000 and reloads when Python source changes. The database schema is created by Alembic, not by importing the API. If both the container API and local API try to bind port 8000, stop the container API first:"
        ),
        code("docker compose stop api"),
        p(
            "When using an existing PostgreSQL installation, create a development database and role with permission to create/alter its schema. The supplied Compose configuration already creates the expense role and expenses database. The role/password in .env.example are demo credentials, not production configuration."
        ),
        note(
            "Host versus container addresses",
            "Local Python connects to localhost and the published DB_PORT. Inside Compose, API/migrate connect to db:5432 through the private network. Compose supplies its own DATABASE_URL, so changing the host DATABASE_URL alone does not redirect the container API.",
        ),
    ]
    section(s, "5. Configure and migrate safely")
    s += [
        table(
            ["Setting", "Default / accepted value", "Effect"],
            [
                (
                    "DATABASE_URL",
                    "postgresql+psycopg://expense:expense@localhost:5432/expenses",
                    "Local Python connection; supplied explicitly inside Compose",
                ),
                (
                    "EXACT_SETTLEMENT_THRESHOLD",
                    "16; integer from 0 through 16",
                    "Maximum nonzero balances using exact optimization; 0 forces greedy for nonempty positions",
                ),
                ("API_PORT", "8000", "Host port mapped to API container port 8000"),
                ("DB_PORT", "5432", "Host port mapped to PostgreSQL container port 5432"),
                ("TEST_DB_PORT", "5433", "Host port for the separate disposable test database"),
                (
                    "TEST_DATABASE_URL",
                    "PostgreSQL URL ending in database name _test",
                    "Read by integration tests; must differ from the application URL",
                ),
            ],
            [150, 190, WIDTH - 340],
        ),
        p(
            "If DB_PORT or TEST_DB_PORT changes, update the corresponding host-side URL. API_PORT changes the host URL used by browsers, Postman and live smoke tests; it does not change the API container's internal port."
        ),
        p("Migration commands", "H2"),
        code("uv run alembic current\nuv run alembic upgrade head\nuv run alembic check"),
        p(
            "The current head is 0002. Revision 0001 creates the relational schema. Revision 0002 removes the old per-expense settlement cap, allowing one payment to clear several individually valid expenses. alembic check compares the current database to the ORM models; it should report no new upgrade operations."
        ),
        p("Future schema changes", "H2"),
        code('uv run alembic revision --autogenerate -m "describe the schema change"'),
        p(
            "Review generated SQL operations before applying them. A downgrade from 0002 to 0001 refuses to proceed if payments above the old cap already exist. This is deliberate: the migration never truncates or rewrites financial history to make a downgrade fit."
        ),
    ]
    section(s, "6. Verify behavior and use Postman")
    s += [
        p("Run the complete collection", "H2"),
        p(
            "Import docs/expense-sharing.postman_collection.json and either Local.postman_environment.json or Render.postman_environment.json. Select the environment before running; its base_url overrides the collection's localhost default. Render uses https://expense-sharing-app-inda.onrender.com/api/v1. No authorization header is needed. Run requests in order in the Collection Runner; captured IDs avoid assumptions about existing seed data."
        ),
        table(
            ["Stage", "What the collection proves"],
            [
                (
                    "Create users/group/members",
                    "IDs are captured into collection variables; no assumption about an empty database",
                ),
                ("Equal dinner", "A 1200.00 expense allocates three 400.00 shares"),
                (
                    "Balances and analytics",
                    "Two 400.00 debts; Mohit paid 1200.00 but consumed 400.00",
                ),
                ("Settlements", "Two recorded payments clear the group"),
                (
                    "Custom split and category",
                    "500.00 / 300.00 / 200.00 allocation and manual category correction",
                ),
                (
                    "Search and drill-down",
                    "Entity search, feature discovery and paginated consumption records",
                ),
            ],
            [135, WIDTH - 135],
        ),
        p(
            "The collection contains 21 requests with response/status checks. Re-running it creates a fresh set of synthetic entities and uses their returned IDs. The plain docs/demo.http alternative includes every request too, but its fixed IDs assume an empty database."
        ),
        p("Live HTTP smoke check", "H2"),
        code("uv run python -m scripts.smoke_http --base-url http://localhost:8000"),
        p(
            "The smoke script creates synthetic records, exercises the original dinner scenario, verifies personal analytics, records the suggested payments, and checks the final settled state. It leaves those records for inspection; run it against a demo/disposable instance."
        ),
        p("A useful manual acceptance check", "H2"),
        p(
            "Create a group with three members, record Dinner 1200.00 paid by Mohit with split_type omitted, and verify Rahul and Ankit each owe Mohit 400.00. Record Rahul's payment, verify only Ankit's debt remains, then record Ankit's payment and verify is_settled=true."
        ),
    ]
    section(s, "7. Run tests and quality checks")
    s += [
        p("Unit checks require no database", "H2"),
        code("uv run pytest tests/unit -q\nuv run ruff check .\nuv run ruff format --check ."),
        p("The full suite uses a dedicated PostgreSQL instance", "H2"),
        code(
            "docker compose --profile test up -d --wait test-db\nuv run --env-file .env pytest -q"
        ),
        p(
            "The .env example includes TEST_DATABASE_URL for localhost:5433/expenses_test. uv run --env-file loads that value into the test process. Without TEST_DATABASE_URL, integration tests explicitly skip; a green unit-only run is not evidence that the entire API/database suite ran."
        ),
        note(
            "Database isolation",
            "The test URL must name a PostgreSQL database ending in _test and differ from the application's URL. Every integration case creates and migrates a generated schema, then drops only that schema. The role needs CREATE SCHEMA privileges. Tests do not reset the application's public schema or application data.",
        ),
        p("What is covered", "H2"),
        p(
            "The final baseline has 87 passing tests: 54 unit cases and 33 PostgreSQL integration tests. Coverage includes exact paise allocation, custom-split validation, membership snapshots, balances, exact optimizer versus an independent oracle, cycle cancellation, category context, search, migration safety, concurrent payments, snapshot reports, hosted URL normalization and static asset serving. The final rerun completed in 24.26 seconds; timings depend on the machine."
        ),
        p("Optional measurement and shutdown", "H2"),
        code(
            "uv run python -m scripts.benchmark_settlements\ndocker compose --profile test stop test-db\ndocker compose down"
        ),
        p(
            "Benchmark results are written to an ignored JSON file. Sample local measurements support the 16-member exact threshold, but are not a worst-case latency guarantee. GitHub Actions also runs lint, format, full PostgreSQL tests, Compose validation and a Docker build."
        ),
    ]
    section(s, "8. Troubleshoot common problems")
    s += [
        table(
            ["Symptom", "Likely cause / next action"],
            [
                (
                    "Cannot connect to Docker",
                    "Start Docker Desktop/Engine; confirm docker version works for the current user. Compose v2 is required.",
                ),
                (
                    "Port is already allocated",
                    "Stop the other API/DB or set API_PORT/DB_PORT/TEST_DB_PORT in .env. Update host-side URLs to match.",
                ),
                (
                    "API returns 503 readiness",
                    "Check database availability and connection settings; readiness tests connectivity, not migration revision.",
                ),
                (
                    "relation/table does not exist",
                    "Run alembic upgrade head against the same DATABASE_URL used by the API. The application does not auto-create tables.",
                ),
                (
                    "migrate container is exited",
                    "Exit code 0 is expected for the one-shot migration job. Nonzero requires inspecting its logs.",
                ),
                (
                    "422 on expense or payment",
                    "Check amount precision/limits, null text, body field names, strict integer IDs and timezone-aware timestamps.",
                ),
                (
                    "409 on payment",
                    "The payer/recipient/mode does not match current debt, the group is already net-settled, or another payment changed the state. Fetch a new preview.",
                ),
                (
                    "Tests pass but API tests skip",
                    "Set TEST_DATABASE_URL and start test-db; confirm it ends in _test and is distinct from the app DB.",
                ),
                (
                    "Postman IDs are unresolved",
                    "Run the collection from its first request so capture scripts set each variable; check base_url and prior response statuses.",
                ),
            ],
            [150, WIDTH - 150],
        ),
        p("Inspect service logs", "H2"),
        code(
            "docker compose logs --tail=100 api\ndocker compose logs --tail=100 migrate\ndocker compose logs --tail=100 db"
        ),
        p("Before handing over the assignment", "H2"),
        p(
            "Confirm the repository URL opens, a fresh checkout starts, the migration reaches 0002, Swagger is accessible, the complete collection runs, and all integration tests actually execute. Read the API and schema PDFs for accounting assumptions and API-specific explanations."
        ),
        p(
            f'<link href="{REPO}/actions" color="#087F8C">CI results</link> | <link href="{REPO}/blob/main/docs/verification.md" color="#087F8C">Detailed verification record</link>',
            "Small",
        ),
    ]
    section(s, "9. Deploy or maintain the Render service")
    s += [
        p(
            "The existing live service was configured manually in Oregon with PostgreSQL 18. Local Docker/tests and the reusable Blueprint use PostgreSQL 17; the Blueprint selects Singapore for new resources. Existing manually created services do not automatically inherit render.yaml. Keep the web service and its database in the same region."
        ),
        p("Required service settings", "H2"),
        table(
            ["Setting", "Value / source"],
            [
                ("Runtime / instance", "Docker / Free"),
                ("Docker Command", "python -m scripts.start_render"),
                ("Health Check Path", "/health/ready"),
                (
                    "DATABASE_URL",
                    "Internal Database URL from the Render PostgreSQL service; keep private",
                ),
                ("EXACT_SETTLEMENT_THRESHOLD", "16"),
                ("PORT", "Supplied by Render; startup binds 0.0.0.0 to this value"),
            ],
            [155, WIDTH - 155],
        ),
        p(
            "No .env upload is needed on Render. Add the variables in the web service's Environment settings. Do not copy the localhost database URL from .env.example. API_PORT, DB_PORT, TEST_DB_PORT and TEST_DATABASE_URL belong to local development/testing."
        ),
        code(
            "python -m scripts.start_render\n# upgrade head -> idempotent seed -> Uvicorn on PORT"
        ),
        p(
            "Startup applies migrations before accepting traffic. The seed creates the synthetic trip only if absent and never resets reviewer changes. Running migrations at startup is a single-instance free-demo tradeoff; a production setup should use a dedicated migration stage."
        ),
        p("Provisioning a separate copy", "H2"),
        p(
            f'Use <link href="https://render.com/deploy?repo={REPO}" color="#087F8C">Deploy to Render</link> or create a Blueprint from render.yaml. It defines a free web service and free PostgreSQL 17 in Singapore, links DATABASE_URL and blocks external database access. If the account already has its free database, resolve the quota rather than unintentionally choosing a paid plan.'
        ),
        p("Diagnose deployment failures", "H2"),
        table(
            ["Observation", "Action"],
            [
                (
                    "Connection refused at localhost:5432",
                    "Set DATABASE_URL to Render's internal database connection URL, save and deploy.",
                ),
                (
                    "Readiness 200 but relation groups does not exist",
                    "Database connectivity works, but migrations were skipped. Set Docker Command to python -m scripts.start_render and deploy.",
                ),
                (
                    "UI reports HTTP 500 / 502",
                    "Read current Render logs. The UI handles non-JSON server/proxy failures; repeated retries do not fix schema or configuration errors.",
                ),
                (
                    "Empty or changed demo history",
                    "Data is shared. Create a fresh demo trip; do not reset another reviewer's records.",
                ),
            ],
            [170, WIDTH - 170],
        ),
        p(
            f'After deployment, verify the root UI, /docs, /health/ready and a real group API. The current public demo passed the full HTTP scenario. Application baseline {REF} also passed <link href="{CI}" color="#087F8C">GitHub CI</link>.',
            "Small",
        ),
        p(
            'Hosting references: <link href="https://render.com/docs/free" color="#087F8C">Render free-tier limits</link> and <link href="https://render.com/docs/docker" color="#087F8C">Docker settings</link>. Free service idle wakeup is about a minute; free databases expire after 30 days.',
            "Small",
        ),
    ]
    build("setup-instructions.pdf", "Setup Instructions", s)


def schema_type(value):
    if "$ref" in value:
        return value["$ref"].split("/")[-1]
    for union in ("anyOf", "oneOf"):
        if union in value:
            return " | ".join(schema_type(item) for item in value[union])
    if value.get("type") == "array":
        return "list[" + schema_type(value.get("items", {})) + "]"
    if "enum" in value:
        return ", ".join(str(item) for item in value["enum"])
    if "const" in value:
        return "literal: " + str(value["const"])
    return value.get("type", "object") + (" (" + value["format"] + ")" if "format" in value else "")


OP_NOTES = {
    (
        "post",
        "/api/v1/users",
    ): "Create a user. Names are trimmed, nonblank and at most 100 characters. Duplicate names are allowed; use the returned ID as identity.",
    (
        "get",
        "/api/v1/users",
    ): "List users, optionally matching q in the name. Results use the standard pagination envelope.",
    ("get", "/api/v1/users/{user_id}"): "Fetch one user by ID; a missing user returns 404.",
    (
        "post",
        "/api/v1/groups",
    ): "Create an INR group. timezone is an IANA zone and defaults to Asia/Kolkata. New groups have no members.",
    (
        "get",
        "/api/v1/groups",
    ): "List groups. user_id restricts results to groups containing that user; q matches group names. Filters are discovery filters, not authorization.",
    (
        "get",
        "/api/v1/groups/{group_id}",
    ): "Return group details, timezone, currency and current member_count.",
    (
        "put",
        "/api/v1/groups/{group_id}/members/{user_id}",
    ): "Add an existing user to an existing group. The URI identifies the membership, so repeating the call is idempotent: 201 when created, 200 when already present. No body is needed.",
    (
        "get",
        "/api/v1/groups/{group_id}/members",
    ): "List current members with user IDs, names and joined_at timestamps. This is the member set used for a newly recorded expense.",
    (
        "post",
        "/api/v1/groups/{group_id}/expenses",
    ): "Atomically save an expense and its participant shares. Omit split_type for equal splitting. Custom mode must include every current member exactly once. The payer must be a current group member.",
    (
        "get",
        "/api/v1/groups/{group_id}/expenses",
    ): "List expense history with optional text, category, payer and local-date filters. Each item includes its saved shares; later membership changes never rewrite them.",
    (
        "get",
        "/api/v1/groups/{group_id}/expenses/{expense_id}",
    ): "Fetch a full expense and all shares. An expense outside the supplied group is treated as not found.",
    (
        "patch",
        "/api/v1/groups/{group_id}/expenses/{expense_id}/category",
    ): 'Correct a category by sending {"category":"travel"}, for example. The category source becomes manual. No amount, payer or split edits are supported.',
    (
        "get",
        "/api/v1/groups/{group_id}/balances",
    ): "Return current lifetime balances. direct is the default and returns debtor-to-creditor transfers; net returns signed positions. Positive net means money to receive. Check is_settled for financial completion.",
    (
        "get",
        "/api/v1/users/{user_id}/balances",
    ): "Return the user's balances grouped by group; net is the default. Only positions/transfers involving the requested user are included, while each group's settled flag describes the whole group.",
    (
        "get",
        "/api/v1/groups/{group_id}/settlement-suggestions",
    ): "Preview transfers without changing data. simplified optimizes net positions, using exact optimization within the configured threshold and greedy matching above it. direct cancels debt circulation while preserving creditor relationships.",
    (
        "post",
        "/api/v1/groups/{group_id}/settlements",
    ): "Record money already paid externally. mode is required. Fresh balances are checked under the group lock; invalid directions, self-payments, outsiders, overpayments and net-settled groups return 409. Partial payments are supported.",
    (
        "get",
        "/api/v1/groups/{group_id}/settlements",
    ): "List recorded payments, optionally filtered by local dates. These are audit records and are separate from expense history.",
    (
        "get",
        "/api/v1/users/{user_id}/analytics",
    ): "Report the user's allocated spending and actual cash flows across groups or within group_id. Saved shares define spending; paying a bill for friends does not make its entire amount personal consumption.",
    (
        "get",
        "/api/v1/groups/{group_id}/analytics",
    ): "Report group spending, categories, monthly totals and member allocations. An expense is counted once in total spending, while settlement flows are reported separately.",
    (
        "get",
        "/api/v1/users/{user_id}/analytics/expenses",
    ): "Paginated evidence behind personal analytics. amount is the user's share and expense_amount is the full bill. Filter by category and dates; choose amount_desc or date_desc ordering.",
    (
        "get",
        "/api/v1/groups/{group_id}/analytics/expenses",
    ): "Paginated evidence behind group analytics. amount and expense_amount both represent the whole expense. Supports category/date filtering and amount_desc or date_desc ordering.",
    (
        "get",
        "/api/v1/search",
    ): "Search users, groups, expense descriptions and a static feature catalog. q is required. types is a comma-separated subset of users,groups,expenses,features. Exact matches rank before prefixes and substrings, with stable tie breaking.",
    (
        "get",
        "/api/v1/categories",
    ): "Return available categories and the rule version. Classification is deterministic, explainable and local; it uses no external AI service.",
    (
        "get",
        "/health/live",
    ): "Process liveness. Does not contact PostgreSQL. This route is outside /api/v1.",
    (
        "get",
        "/health/ready",
    ): "Database connectivity readiness using SELECT 1. Returns 503 if unavailable. It does not verify the Alembic revision; migration execution is a separate deployment step.",
}


def api_guide():
    s = cover(
        "02",
        "API Documentation",
        "Contracts, examples and accounting semantics",
        "A developer reference for using every implemented HTTP operation, with precise money, validation, filtering and settlement behavior.",
        [
            "Conventions and error handling",
            "Worked trip and optional split modes",
            "Balances, settlement suggestions and payments",
            "Search, categorization and analytics",
            "Complete operation and model reference",
        ],
    )
    section(s, "1. API conventions", first=True)
    s += [
        p("Base address and live contract", "H2"),
        p(
            f'<b>Live API base:</b> <link href="{LIVE}/api/v1" color="#087F8C">{LIVE}/api/v1</link><br/><b>Interactive contract:</b> <link href="{LIVE}/docs" color="#087F8C">{LIVE}/docs</link>. The deployed UI at the root calls these same financial APIs. Local development uses the addresses below.'
        ),
        code(
            "Application: http://localhost:8000\nAPI prefix:  /api/v1\nSwagger UI:  http://localhost:8000/docs\nReDoc:       http://localhost:8000/redoc\nOpenAPI:     http://localhost:8000/openapi.json"
        ),
        p(
            "Use Content-Type: application/json for bodies. The service is a single-currency INR demo with no authentication. User/group scope filters do not provide access control. Do not expose a shared instance containing private financial data."
        ),
        table(
            ["Convention", "Meaning"],
            [
                (
                    "Identity",
                    "IDs, not display names, identify entities. Duplicate names are permitted.",
                ),
                (
                    "Money input",
                    'Use decimal strings such as "1200.00". JSON numbers such as 1200 are accepted, but clients should avoid floating-point calculations.',
                ),
                (
                    "Money output",
                    "Amounts are strings with two decimal places. Storage and domain arithmetic use integer paise.",
                ),
                (
                    "Body validation",
                    "Unknown fields are rejected. Body IDs must be positive integers; string IDs are rejected. Text containing a NUL character is rejected.",
                ),
                (
                    "Expense amount",
                    "Greater than 0; at most INR 10,000,000.00; no more than two meaningful decimal places. Custom shares may be zero.",
                ),
                (
                    "Settlement amount",
                    "Greater than 0 and at most INR 92,233,720,368,547,758.07, the positive BIGINT paise range. The current debt may impose a much lower limit.",
                ),
                (
                    "Timestamps",
                    "Use an explicit UTC offset, e.g. 2026-10-16T19:30:00+05:30. occurred_at defaults to now; created_at is generated by the service.",
                ),
                (
                    "Pagination",
                    "Lists return items, total, limit and offset. Default limit=20, maximum=100; offset starts at 0. Search additionally caps offset at 1000.",
                ),
            ],
            [115, WIDTH - 115],
        ),
        p("Typical list envelope", "H2"),
        js({"items": [], "limit": 20, "offset": 0, "total": 0}),
        note(
            "Retries",
            "Membership PUT is safe to repeat. Creation POST requests have no idempotency key; a network retry may create another record. Verify the previous result before retrying a payment record.",
        ),
    ]
    section(s, "2. Validation and error responses")
    s += [
        p(
            "All handled errors use the same JSON envelope. details contains structured validation information when applicable; clients should branch on code and status rather than parsing the human message."
        ),
        js(
            {
                "error": {
                    "code": "payer_not_member",
                    "message": "Payer must be a group member",
                    "details": [],
                }
            }
        ),
        table(
            ["Status", "When it occurs", "Typical codes"],
            [
                (
                    "404",
                    "A referenced user/group is absent, or the expense is outside this group.",
                    "user_not_found, group_not_found, expense_not_found",
                ),
                (
                    "422",
                    "Malformed body, nonpositive amount, excess precision, invalid custom shares, unknown timezone, bad query/date range.",
                    "validation_error, invalid_splits, invalid_timezone, invalid_date_range, invalid_search, invalid_search_types",
                ),
                (
                    "409",
                    "Current state prevents an operation: payer not a member, invalid settlement participants/direction, self-payment or overpayment.",
                    "payer_not_member, invalid_settlement, user_not_member, integrity_conflict",
                ),
                ("503", "Readiness cannot reach the database.", "database_unavailable"),
            ],
            [42, 235, WIDTH - 277],
        ),
        p(
            "A 422 validation response may identify a location such as body.amount. A 409 settlement failure means the client should read current balances and refresh suggestions. No partial expense shares or partial payment records are committed on failure."
        ),
        p("Dates and reporting timezones", "H2"),
        p(
            "Query parameter from is inclusive and to is exclusive. Both are local dates in the selected timezone: from=2026-10-01&amp;to=2026-11-01 covers October. Expense and settlement history use the group's timezone. Analytics accepts a timezone override; a cross-group user report defaults to Asia/Kolkata. A user report restricted to one group uses that group's timezone unless overridden."
        ),
        p(
            "A backdated expense still uses the group's member list at recording time. Its occurred_at affects date-based reporting; created_at preserves when the service recorded it."
        ),
    ]
    section(s, "3. Worked trip: create and share")
    s += [
        p(
            "Example IDs below assume a fresh database. Always use actual IDs returned by the server. The supplied Postman collection captures them automatically and works even when seed data already exists."
        ),
        p("Step 1 - create three users", "H2"),
        code('POST /api/v1/users\n{"name": "Mohit"}'),
        p(
            "Repeat for Rahul and Ankit. Each response is 201 with id, name and created_at. This example uses user IDs 1, 2 and 3 respectively."
        ),
        p("Step 2 - create a group and add members", "H2"),
        code(
            'POST /api/v1/groups\n{"name": "Goa Trip", "timezone": "Asia/Kolkata"}\n\nPUT /api/v1/groups/1/members/1\nPUT /api/v1/groups/1/members/2\nPUT /api/v1/groups/1/members/3'
        ),
        p(
            "The member calls have no request body. A new membership returns 201. Repeating the same PUT returns 200 without duplicating it."
        ),
        p("Step 3 - record the dinner", "H2"),
        code("POST /api/v1/groups/1/expenses"),
        js({"paid_by": 1, "amount": "1200.00", "description": "Dinner"}),
        p(
            "The 201 response is an ExpenseRead object. It includes id, group_id, payer label, amount, currency, description, split_type, category provenance, timestamps and saved shares. The share portion is:"
        ),
        js(
            {
                "shares": [
                    {"user": {"id": 1, "name": "Mohit"}, "amount": "400.00"},
                    {"user": {"id": 2, "name": "Rahul"}, "amount": "400.00"},
                    {"user": {"id": 3, "name": "Ankit"}, "amount": "400.00"},
                ]
            }
        ),
        note(
            "Exact allocation",
            "The service divides integer paise. INR 100.00 among IDs 1, 2 and 3 becomes 33.34, 33.33 and 33.33. Remainder paise go to ascending user IDs. The saved shares always sum to the original bill; the payer's own share never becomes self-debt.",
        ),
    ]
    section(s, "4. Custom splits and history")
    s += [
        p(
            "Equal splitting is the default required behavior. Unequal allocation is an explicit optional mode rather than a change to that default."
        ),
        code("POST /api/v1/groups/1/expenses"),
        js(
            {
                "paid_by": 1,
                "amount": "1000.00",
                "description": "Activity package",
                "split_type": "custom",
                "splits": [
                    {"user_id": 1, "amount": "500.00"},
                    {"user_id": 2, "amount": "300.00"},
                    {"user_id": 3, "amount": "200.00"},
                ],
            }
        ),
        p(
            "Every current member must appear exactly once, including the payer. A zero share is allowed. Duplicates, outsiders, missing members, negative shares or an incorrect total produce 422. The expense and shares are inserted in one transaction."
        ),
        p("Filter and inspect history", "H2"),
        code(
            "GET /api/v1/groups/1/expenses?category=food&limit=20&offset=0\nGET /api/v1/groups/1/expenses/1"
        ),
        p(
            "History also accepts q, paid_by, from and to. GET returns saved participant shares, not a reconstruction from today's memberships. Adding a fourth member leaves this dinner at three shares."
        ),
        p("Category correction", "H2"),
        code('PATCH /api/v1/groups/1/expenses/1/category\n{"category": "food"}'),
        p(
            "Only category metadata can be updated. Financial amount/payer/share edits, deletion and member removal are deliberately absent to preserve the simple audit trail."
        ),
    ]
    section(s, "5. Balances and settlement")
    s += [
        p(
            "The examples in this section use only the original 1200.00 dinner, before the separate custom-split example is added."
        ),
        code("GET /api/v1/groups/1/balances?view=direct"),
        js(
            {
                "group_id": 1,
                "currency": "INR",
                "view": "direct",
                "is_settled": False,
                "balances": [
                    {
                        "from_user": {"id": 2, "name": "Rahul"},
                        "to_user": {"id": 1, "name": "Mohit"},
                        "amount": "400.00",
                    },
                    {
                        "from_user": {"id": 3, "name": "Ankit"},
                        "to_user": {"id": 1, "name": "Mohit"},
                        "amount": "400.00",
                    },
                ],
                "explanation": None,
            }
        ),
        p("Net view is more compact", "H2"),
        p(
            "GET /api/v1/groups/1/balances?view=net returns signed positions: Mohit +800.00, Rahul -400.00 and Ankit -400.00. Positive means receivable; negative means payable. Net positions sum to zero. The payer's 400.00 consumption is already included."
        ),
        code(
            "net = expenses_paid - allocated_shares\n      + settlements_sent - settlements_received"
        ),
        p("Preview before paying", "H2"),
        code("GET /api/v1/groups/1/settlement-suggestions?mode=simplified"),
        p(
            "The PlanRead response contains mode, strategy, objective, optimality_guaranteed, transaction_count, transfers and an explanation. A preview is advisory: it neither stores a plan nor transfers money. Transfer labels include both user IDs and names."
        ),
        table(
            ["Mode / strategy", "Behavior and tradeoff"],
            [
                (
                    "simplified / exact",
                    "Within the configured threshold (default 16 nonzero net positions), a zero-sum subset dynamic program guarantees the minimum transfer count. Cost grows exponentially: O(n * 2^n) time and O(2^n) space.",
                ),
                (
                    "simplified / greedy",
                    "For larger groups, match largest debtors and creditors using heaps in O(n log n). At most n-1 transfers; no minimum-count guarantee.",
                ),
                (
                    "direct / direct",
                    "Remove circulation deterministically, preserving net positions and existing debtor-creditor relationships. The returned actionable graph is acyclic; minimum count is not promised.",
                ),
            ],
            [125, WIDTH - 125],
        ),
    ]
    s += [
        PageBreak(),
        p("Record the external payment", "H2"),
        code("POST /api/v1/groups/1/settlements"),
        js(
            {
                "from_user_id": 2,
                "to_user_id": 1,
                "amount": "400.00",
                "mode": "simplified",
                "note": "Paid via UPI",
            }
        ),
        p(
            "A 201 SettlementRead confirms recording. Rahul's net position is now zero; Ankit still owes Mohit 400.00. Record Ankit's payment similarly and the group's is_settled becomes true. The service only records cash/UPI/bank payments made outside the application."
        ),
        note(
            "Current-state validation",
            "direct payments cannot exceed the current pair debt. simplified payments require a net debtor sending to a net creditor and cannot exceed either position. The server locks the group, recomputes balances and commits atomically, so two concurrent requests cannot both spend the same remaining debt.",
        ),
        p(
            "Raw direct history may retain a zero-net cycle after simplified settlements. That is an accounting representation, not a new amount payable. Use is_settled and the cycle-free settlement-suggestions endpoint for action. Do not blindly record raw balance edges as payments."
        ),
    ]
    section(s, "6. Search and smart categories")
    s += [
        code(
            "GET /api/v1/search?q=goa&types=groups,expenses\nGET /api/v1/search?q=spending%20analytics&types=features\nGET /api/v1/search?q=dinner&group_id=1&user_id=2"
        ),
        p(
            "Search returns a paginated list of SearchHit objects: type, id, label, match_field and api_path. It matches case-insensitive substrings and escapes SQL wildcard characters, so % and _ are literal search text. Feature aliases support discovering API capabilities by everyday phrases."
        ),
        p(
            "group_id and user_id narrow data results and intersect when combined. User-scoped discovery includes the user and peers from their groups; feature results remain global. These filters are not security boundaries. Search uses straightforward SQL substring matching, suitable for assignment-scale data rather than a full search engine."
        ),
        code("GET /api/v1/categories"),
        table(
            ["Category", "Examples / interpretation"],
            [
                ("travel", "Auto, cab, bike transport, taxi, flight and bus tickets."),
                ("food", "Meals, dinner and contextual hotel dinner."),
                ("accommodation", "Hotel bookings and lodging."),
                ("activities", "Activities and entertainment expenses."),
                ("shopping", "Purchases, including bike purchase rather than bike travel."),
                (
                    "other",
                    "No confident rule or conflicting unrelated contexts, e.g. hotel dinner and flight.",
                ),
            ],
            [105, WIDTH - 105],
        ),
        p(
            "Rules v2 normalize text, consume matched phrases and examine remaining context. Generic ticket/tickets is weak evidence. category_source records manual, rule or fallback; category_rule preserves the explanation/version where applicable. Supplying category on creation or using the PATCH endpoint overrides inference. Old records are not silently reclassified when rules change."
        ),
        note(
            "Product choice",
            "Search reduces navigation effort; transparent categorization makes analytics useful without an external model, API key or unpredictable classification cost. Ambiguity intentionally falls back to other so the user can correct it.",
        ),
    ]
    section(s, "7. Spending analytics")
    s += [
        code(
            "GET /api/v1/users/1/analytics?from=2026-10-01&to=2026-11-01\nGET /api/v1/groups/1/analytics?timezone=Asia%2FKolkata\nGET /api/v1/users/1/analytics/expenses?sort=amount_desc"
        ),
        p(
            "Reports answer two distinct questions: what was consumed, and what cash moved? In the dinner-only example, Mohit has spending=400.00 and paid=1200.00. Rahul has spending=400.00 and paid=0.00 before repayment. The group has spending=1200.00, not 3600.00."
        ),
        table(
            ["Field", "Definition"],
            [
                ("totals.spending", "Personal saved shares, or full group expenses once each."),
                (
                    "totals.paid",
                    "Expense cash paid by the user, or all expense cash paid in the group.",
                ),
                (
                    "settlements_sent / received",
                    "Recorded external repayments in the selected period; separate from consumption.",
                ),
                ("net_cash_outflow", "paid + settlements_sent - settlements_received."),
                (
                    "categories / months",
                    "Amount and percentage breakdowns of spending. Monthly is the supported bucket.",
                ),
                (
                    "groups / members",
                    "Group spending breakdown; member allocation breakdown is provided for group reports.",
                ),
                (
                    "largest_expenses",
                    "Up to five named rows with group, payer, category, timestamp, personal/group amount and original bill amount.",
                ),
                (
                    "drilldown_path",
                    "A filter-preserving API path for the full paginated underlying expense list.",
                ),
                ("metric_definitions", "In-response explanations of the report's measures."),
            ],
            [145, WIDTH - 145],
        ),
        p(
            "Report rows are AnalyticsExpenseRead objects. In a user report amount is the user's share; expense_amount is the whole bill. In a group report amount is the full bill. Category filtering is available on drill-downs; sorting supports amount_desc or date_desc with stable tie breaking."
        ),
        p(
            "The totals and breakdowns use a single PostgreSQL read-only repeatable-read snapshot. SQL aggregation avoids loading the entire expense history into Python. Writers are not blocked by the reporting transaction. Percentage values use two decimal places; an empty report yields zero values rather than division errors."
        ),
        note(
            "Period versus lifetime",
            "A payment in November for an October expense appears in November cash flow. Date-limited analytics is not an outstanding-debt calculation. Balances and settlement suggestions use the full group ledger.",
        ),
    ]
    # Keep endpoint sections compact, but include every parameter directly from OpenAPI.
    section(s, "8. Complete endpoint reference")
    s += [
        p(
            "The following inventory is generated from this revision's OpenAPI document. Path parameters are required. Query defaults and limits are shown where declared. Request/response model names refer to the field dictionary in section 9. The /api/v1 prefix is included explicitly to avoid ambiguity."
        )
    ]
    for path, operations in OPENAPI["paths"].items():
        for method, op in operations.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            assert (method, path) in OP_NOTES, (method, path)
            start = len(s)
            # Wrapping path text instead of code prevents narrow-column overflow.
            s += [p(method.upper() + " " + html.escape(path), "H2"), p(OP_NOTES[(method, path)])]
            params = []
            for par in op.get("parameters", []):
                spec = par.get("schema", {})
                constraints = []
                for key in ("default", "minimum", "maximum", "minLength", "maxLength"):
                    if key in spec:
                        constraints.append(f"{key}={spec[key]}")
                params.append(
                    (
                        par["name"],
                        par["in"] + ("; required" if par.get("required") else "; optional"),
                        schema_type(spec) + ("; " + ", ".join(constraints) if constraints else ""),
                    )
                )
            if params:
                s.append(
                    table(
                        ["Parameter", "Location", "Type / constraints"],
                        params,
                        [100, 100, WIDTH - 200],
                    )
                )
            body = (
                op.get("requestBody", {})
                .get("content", {})
                .get("application/json", {})
                .get("schema")
            )
            if body:
                s.append(p("<b>JSON body:</b> " + html.escape(schema_type(body))))
            responses = []
            for status, resp in op.get("responses", {}).items():
                spec = resp.get("content", {}).get("application/json", {}).get("schema", {})
                responses.append((status, schema_type(spec), resp.get("description", "")))
            s.append(
                table(
                    ["Status", "Response model", "Description"], responses, [45, 190, WIDTH - 235]
                )
            )
            if method == "put":
                s.append(
                    p("The runtime also returns 200 when the membership already exists.", "Small")
                )
            if path.startswith("/health/"):
                s.append(
                    p(
                        'Success JSON: {"status":"'
                        + ("ok" if path.endswith("live") else "ready")
                        + '"}',
                        "Small",
                    )
                )
            if path.endswith("/categories"):
                s.append(
                    p(
                        "Success object fields: categories (string list), rules_version (string), keywords (category-to-keyword-list object), phrase_overrides (phrase-to-category object), explanation (string).",
                        "Small",
                    )
                )
            chunk = s[start:]
            del s[start:]
            s.append(KeepTogether(chunk))
    s += [Spacer(1, 20), p("9. JSON field dictionary", "H1")]
    s += [
        p(
            "Generated from the Pydantic/OpenAPI schemas. 'Required' means the field must be present; a null-capable required response field can still contain null. Read models serialize money as strings. Input money accepts a decimal string or a JSON number. Page models consistently use items, total, limit and offset."
        ),
        p(
            "EqualExpense and CustomExpense are selected by split_type; the server injects equal when the discriminator is omitted. The strict-input and financial rules in sections 1-4 also apply beyond the structural fields shown below."
        ),
    ]
    for name, spec in OPENAPI["components"]["schemas"].items():
        if name.startswith("Page_") or name in {"HTTPValidationError", "ValidationError"}:
            continue
        props = spec.get("properties", {})
        if not props:
            continue
        rows = []
        for field, val in props.items():
            details = schema_type(val)
            if "default" in val:
                details += "; default=" + str(val["default"])
            for key in (
                "maxLength",
                "minLength",
                "minItems",
                "minimum",
                "exclusiveMinimum",
                "maximum",
            ):
                if key in val:
                    details += f"; {key}={val[key]}"
            rows.append((field, "yes" if field in spec.get("required", []) else "no", details))
        s.append(
            KeepTogether(
                [
                    p(html.escape(name), "H2"),
                    table(["Field", "Required", "Type / constraint"], rows, [145, 52, WIDTH - 197]),
                ]
            )
        )
    s += [Spacer(1, 20), p("10. Postman and integration notes", "H1")]
    s += [
        p(
            "Import expense-sharing.postman_collection.json and the supplied Local or Render Postman environment. Select Render to use https://expense-sharing-app-inda.onrender.com/api/v1; Local uses http://localhost:8000/api/v1. Environment base_url overrides the collection default. Run from the beginning; scripts capture returned IDs and check expected responses. The 21 requests cover equal/custom expenses, balances, settlements, search, categories and analytics."
        ),
        p(
            "The collection is a runnable walkthrough, not an exhaustive negative-test suite. The 25-operation reference above and live OpenAPI include extra retrieval/filter variations and health routes. Unit and integration tests cover invalid inputs, database constraints, concurrency and optimizer guarantees."
        ),
        p("Suggested client flow", "H2"),
        p(
            "Create/select a group, load its members, record an expense, show saved shares and category provenance, then display net balances. Before a real external payment, fetch a fresh settlement preview; after the external payment succeeds, record it with the same mode and refresh balances. Treat a 409 as a prompt to refresh state, not to retry blindly."
        ),
        note(
            "Deliberate scope",
            "No authentication, invitations, multi-currency conversion, automatic bank/UPI execution, idempotency keys, financial editing or deletion is implemented. These require additional product and integrity decisions. The service focuses on correct sharing, traceable history and explained settlement advice.",
        ),
    ]
    section(s, "11. Deployed UI and live verification")
    s += [
        p(
            f'The final submission runs at <link href="{LIVE}/" color="#087F8C">{LIVE}/</link>. FastAPI serves the Fairshare UI, its static assets and the documented JSON API from one origin. UI HTML/CSS/JavaScript adds no frontend framework, build step or external CDN dependency.'
        ),
        table(
            ["UI action", "API behavior"],
            [
                (
                    "Choose a trip / person",
                    "Group and membership retrieval; individual and group analytics.",
                ),
                (
                    "Add expense / View split",
                    "Expense POST with equal or custom mode; GET reads the saved allocation.",
                ),
                (
                    "Correct category",
                    "PATCH category; category_source becomes manual and reports use the saved result.",
                ),
                (
                    "Apply report dates",
                    "Date filters affect analytics. Outstanding balances remain lifetime values.",
                ),
                (
                    "Settle up",
                    "Fresh direct/simplified suggestions; record a full or partial external payment through the settlement POST.",
                ),
                (
                    "Fresh demo trip",
                    "Ordinary user/group/membership/expense requests create a separate synthetic scenario. Multiple requests are not atomic.",
                ),
                (
                    "Global search",
                    "Search API results open trips in the UI or expose API results/feature documentation.",
                ),
            ],
            [145, WIDTH - 145],
        ),
        p("Two examples with different purposes", "H2"),
        p(
            "The worked API example and Postman runner start with only Dinner 1200.00, producing two 400.00 debts. The deployed sample trip contains Dinner 1200.00, Taxi 600.00 and Hotel 3000.00. It starts with total consumption 4800.00, each share 1600.00, Mohit net +2600.00, Rahul -1000.00 and Ankit -1600.00. Shared data can change; fresh-trip creation recreates the sample."
        ),
        p("Verified behavior", "H2"),
        p(
            "The live service passed health, user/group creation, membership, equal allocation, personal analytics, exact suggestions, repayment recording, settled-state verification and search through the existing HTTP smoke script. Local PostgreSQL tests total 87; the application baseline also passed GitHub CI. The smoke trip is separate from the seeded trip."
        ),
        p("Failure handling and scope", "H2"),
        p(
            "The client preserves structured JSON validation errors. Plain-text/HTML server or proxy failures are displayed as a useful HTTP-status error instead of a JSON parsing exception. This display behavior does not repair an unavailable database or missing schema. /health/ready verifies database connectivity, while the deployment startup ensures migrations run before service traffic."
        ),
        note(
            "Reviewer expectations",
            "The public instance uses free Render hosting, may need a cold start and has a database that expires 30 days after creation. It contains shared synthetic data and no login. Financial POSTs record facts; they do not transfer real money. Use fresh groups for experiments and never enter private financial data.",
        ),
    ]
    build("api-documentation.pdf", "API Documentation", s)


def schema_guide():
    s = cover(
        "03",
        "Database Schema\nExplanation",
        "Relational design, invariants and transaction flow",
        "A table-by-table explanation of the implemented PostgreSQL schema and the reasoning that protects expense history and settlement correctness.",
        [
            "Entity relationships and storage choices",
            "Column dictionary and constraints",
            "Worked accounting example",
            "Write concurrency and report consistency",
            "Indexes, migrations and tradeoffs",
        ],
    )
    section(s, "1. Why this relational design", first=True)
    s += [
        p(
            "PostgreSQL is the authoritative store. SQLAlchemy 2 maps the schema and issues explicit SQL; Alembic owns schema evolution. A single FastAPI service keeps the assignment understandable and avoids distributed coordination."
        ),
        p(
            "The product can be drawn as a debt graph, but its permanent facts are users, memberships, bills, allocations and payments. Foreign keys, atomic multi-row writes and SQL aggregation fit those facts directly. A graph database would add operational cost without a demonstrated traversal workload, and it falls outside the assignment's suggested SQL options."
        ),
        table(
            ["Choice", "Benefit", "Tradeoff"],
            [
                (
                    "PostgreSQL",
                    "Strong constraints, row locks, repeatable-read reports and aggregate queries.",
                    "Requires a database service; Docker makes the demo reproducible.",
                ),
                (
                    "Integer paise",
                    "Exact conservation and comparisons; no binary float error.",
                    "API must validate decimals and convert at boundaries.",
                ),
                (
                    "Saved expense shares",
                    "Historical obligations survive membership changes and support custom splits.",
                    "Stores one row per participant per expense.",
                ),
                (
                    "Derived balances",
                    "One source of truth; no separate mutable balance cache to reconcile.",
                    "Read cost grows with group history; optimize only when measured.",
                ),
                (
                    "Composite membership keys",
                    "Database-enforced payer/participant membership within the same group.",
                    "More verbose foreign keys and one intentionally repeated group_id.",
                ),
            ],
            [112, 200, WIDTH - 312],
        ),
        note(
            "Core distinction",
            "Expenses record money paid to a merchant. Shares record who consumed that expense. Settlements record money sent between members. Keeping these facts separate prevents repayments from being counted as new spending.",
        ),
    ]
    section(s, "2. Entity relationships")
    s += [
        code(
            "users 1 ----< group_members >---- 1 groups\n                     |                  |\n                     | payer/member     | owns\n                     v                  v\n                  expenses 1 ----< expense_shares\n                     ^                  |\n                     |   same group     | member\n                     +------------------+\n\ngroups 1 ----< settlements\n                | sender + recipient\n                +----> group_members (same group)"
        ),
        table(
            ["Relationship", "Cardinality / enforcement"],
            [
                (
                    "users to groups",
                    "Many-to-many through group_members. Composite PK prevents duplicate memberships.",
                ),
                (
                    "group to expenses",
                    "One-to-many. Every expense has a valid group and a payer in that group.",
                ),
                (
                    "expense to shares",
                    "One-to-many. Each participant has one saved allocation per expense.",
                ),
                (
                    "share to membership",
                    "A participant must belong to the expense's group, enforced through composite foreign keys.",
                ),
                (
                    "group to settlements",
                    "One-to-many. Sender and recipient must both have a membership in that group.",
                ),
            ],
            [155, WIDTH - 155],
        ),
        p(
            "There are six domain tables. alembic_version is migration bookkeeping, not a business entity. SQLAlchemy metadata is used to generate the following column dictionary; the migration scripts are the deployment source of truth."
        ),
        p("Deletion policy", "H2"),
        p(
            "Foreign keys use restrictive/default NO ACTION behavior. There are no cascading delete rules and no public delete/member-removal endpoints. This protects historical financial references. User and group names need not be unique; IDs are stable identity."
        ),
    ]
    explanations = {
        "users": "A person's stable identity. The service has no login credentials or authentication model. A nonblank name check exists in the database; the API additionally trims and validates its maximum length.",
        "groups": "A shared accounting boundary. Currency is constrained to INR. timezone interprets local reporting dates; actual timestamps remain offset-aware instants. Currency/timezone defaults are Python ORM defaults, not SQL server defaults.",
        "group_members": "The current user-to-group association. (group_id, user_id) is both identity and the target of financial composite foreign keys. The API adds memberships but never removes them. joined_at records when the membership was saved.",
        "expenses": "One merchant bill, with payer, amount and immutable allocation mode. category_source and category_rule retain categorization provenance. occurred_at is the business time; created_at is recording time. The extra unique (id, group_id) key lets shares enforce that their group matches the expense.",
        "expense_shares": "A snapshot of the amount allocated to each member when an expense is recorded. The composite primary key prevents duplicate participants. group_id is deliberately repeated so foreign keys can prove that expense and participant belong to the same group. A payer's own share is stored as consumption, but excluded from self-debt.",
        "settlements": "An immutable record of an external member-to-member payment. mode records which validation semantics were used. It does not move money or contain payment credentials. The wider BIGINT amount range supports paying accumulated debt across multiple individually capped expenses.",
    }
    for idx, name in enumerate(
        ("users", "groups", "group_members", "expenses", "expense_shares", "settlements"), 3
    ):
        section(s, f"{idx}. Table: {name}")
        s.append(p(explanations[name]))
        t = Base.metadata.tables[name]
        rows = []
        for col in t.columns:
            ty = str(col.type).replace("DATETIME", "TIMESTAMPTZ")
            flags = []
            if col.primary_key:
                flags.append("PK")
            flags.append("nullable" if col.nullable else "NOT NULL")
            if col.default is not None:
                flags.append("ORM default")
            rows.append((col.name, ty, "; ".join(flags)))
        s.append(table(["Column", "PostgreSQL type", "Properties"], rows, [160, 120, WIDTH - 280]))
        constraints = []
        for constraint in t.constraints:
            if constraint.__class__.__name__ == "CheckConstraint":
                constraints.append((constraint.name or "CHECK", str(constraint.sqltext)))
            elif constraint.__class__.__name__ == "ForeignKeyConstraint":
                local = ", ".join(e.parent.name for e in constraint.elements)
                target = ", ".join(e.target_fullname for e in constraint.elements)
                constraints.append(("FOREIGN KEY", f"({local}) -> ({target})"))
            elif constraint.__class__.__name__ == "UniqueConstraint":
                constraints.append(
                    (constraint.name or "UNIQUE", ", ".join(c.name for c in constraint.columns))
                )
        if constraints:
            s += [
                p("Constraints", "H2"),
                table(["Rule", "Definition"], sorted(constraints), [155, WIDTH - 155]),
            ]
        indexes = sorted(
            (index.name, ", ".join(c.name for c in index.columns)) for index in t.indexes
        )
        if indexes:
            s += [
                p("Additional indexes", "H2"),
                table(["Index", "Columns, in order"], indexes, [235, WIDTH - 235]),
            ]
        if name == "expense_shares":
            s.append(
                note(
                    "Aggregate invariant",
                    "The database checks each share is nonnegative and validates its references. The service, inside the expense transaction, checks complete member coverage and sum(shares)=expense amount. There is no database trigger enforcing that cross-row sum; arbitrary SQL that bypasses the service could violate it.",
                )
            )
        if name == "settlements":
            s.append(
                p(
                    "The database rejects self-payments and nonpositive amounts. Current debt direction and overpayment checks require the live ledger and are enforced by the transactional service. The database's BIGINT type provides the upper storage limit; request validation checks that range before insertion."
                )
            )
    section(s, "9. Worked storage and accounting example")
    s += [
        p(
            "Assume users 1=Mohit, 2=Rahul and 3=Ankit belong to group 1=Goa Trip. Values in the storage tables below are paise, not rupees."
        ),
        table(
            ["Table", "Saved rows / important values"],
            [
                ("group_members", "(group=1,user=1), (1,2), (1,3)"),
                (
                    "expenses",
                    "id=10, group_id=1, paid_by=1, amount_minor=120000, description=Dinner, split_type=equal",
                ),
                (
                    "expense_shares",
                    "(expense=10,group=1,user=1,amount=40000); same for users 2 and 3",
                ),
                ("settlements initially", "No rows"),
            ],
            [125, WIDTH - 125],
        ),
        p(
            "Direct obligations are derived from non-payer shares: user 2 owes user 1 40000 paise, and user 3 owes user 1 40000 paise. Mohit's own share exists for analytics, but does not create an edge back to himself."
        ),
        table(
            ["User", "Paid", "Allocated", "Net before repayment"],
            [
                ("Mohit", "1200.00", "400.00", "+800.00"),
                ("Rahul", "0.00", "400.00", "-400.00"),
                ("Ankit", "0.00", "400.00", "-400.00"),
            ],
            [100, 100, 100, WIDTH - 300],
        ),
        p(
            "Recording Rahul's external payment adds a settlements row (group=1, from=2, to=1, amount_minor=40000, mode=simplified). It does not modify the original expense or shares. Mohit's net becomes +400.00 and Rahul's becomes zero. The second payment clears Ankit and the group."
        ),
        p("Membership changes and precision", "H2"),
        p(
            "Adding user 4 later leaves expense 10 with exactly three share rows. A new expense would include four members. For an amount not divisible by member count, integer quotient/remainder allocation gives extra paise to ascending user IDs and preserves the total exactly. Custom splitting stores the validated supplied allocations in the same table."
        ),
    ]
    section(s, "10. Transaction and code flow")
    s += [
        p("Write path", "H2"),
        code(
            "HTTP route -> Pydantic input validation\n           -> application service\n           -> lock group row FOR UPDATE\n           -> read current members / current ledger\n           -> validate and compute exact paise results\n           -> insert expense + all shares, or settlement\n           -> commit once -> serialize response"
        ),
        p(
            "Membership additions and financial writes acquire the same group lock. An expense therefore cannot observe half of a concurrent membership change. Two payments serialize before rechecking debt, preventing duplicate consumption of the same payable balance. The lock is local to one group, so independent groups can progress concurrently."
        ),
        p("Balance reads", "H2"),
        p(
            "Normal balance reads coordinate with group writes through a shared group lock and derive the ledger from a single UNION-based query. Opposite pair debts/payments are netted for direct view; signed totals produce net view. Settlement suggestions reuse the derived ledger rather than storing a second financial truth."
        ),
        p("Analytics read path", "H2"),
        code(
            "analytics route -> report-session dependency\n                -> REPEATABLE READ + READ ONLY transaction\n                -> SQL CTEs / sums / grouped breakdowns\n                -> one consistent report -> close transaction"
        ),
        p(
            "No group share lock is acquired by analytics. PostgreSQL MVCC lets totals, breakdowns and largest expenses see the same snapshot while concurrent expense recording proceeds. Reports aggregate in SQL and expose a paginated drill-down instead of loading the full group history into application memory."
        ),
        note(
            "Boundary",
            "Correctness assumes financial writes use this service's locking/validation protocol. Database constraints defend row-level structure, while service rules defend ledger-dependent and cross-row behavior. This distinction is tested and documented rather than hidden behind a claim that every rule is a CHECK constraint.",
        ),
    ]
    section(s, "11. Indexes and query design")
    s += [
        table(
            ["Access pattern", "Supporting design"],
            [
                (
                    "Groups for a user",
                    "group_members(user_id, group_id) reverses the composite PK's leading group order.",
                ),
                (
                    "Expense history by group/date",
                    "expenses(group_id, occurred_at, id) supports date ranges and stable ties.",
                ),
                ("Bills paid by a member", "expenses(group_id, paid_by) supports payer filtering."),
                (
                    "Personal consumption",
                    "expense_shares(user_id, expense_id) supports share-based joins and reports.",
                ),
                (
                    "Payment history",
                    "settlements(group_id, occurred_at, id) supports group/date access.",
                ),
                (
                    "Referential joins",
                    "Primary keys and expense (id, group_id) uniqueness support referenced-key lookups.",
                ),
            ],
            [165, WIDTH - 165],
        ),
        p(
            "An index's existence does not guarantee every combined filter or sort avoids a scan. Substring search uses escaped case-insensitive matching; there is no trigram/full-text index in this demo. Monthly/category reports use SQL aggregation over filtered rows. Measure EXPLAIN ANALYZE and dataset size before adding indexes, materialized summaries or a balance cache."
        ),
        p("Avoiding overengineering", "H2"),
        p(
            "Category values are a small fixed vocabulary enforced with text checks, not a separate editable category service. Settlement plans are computed previews, not persisted plans that become stale. A balance table, graph store, queue and microservices would increase synchronization work without improving the assignment's core guarantees."
        ),
    ]
    section(s, "12. Migrations and future evolution")
    s += [
        table(
            ["Revision", "Change"],
            [
                (
                    "0001",
                    "Initial six-table schema, constraints and indexes. The original settlement amount check included the per-expense cap.",
                ),
                (
                    "0002 (head)",
                    "Replaces the settlement amount check with positivity only, allowing aggregate payments up to BIGINT storage capacity. Expense limits stay unchanged.",
                ),
            ],
            [100, WIDTH - 100],
        ),
        code("uv run alembic upgrade head\nuv run alembic current\nuv run alembic check"),
        p(
            "The Compose migration service upgrades before API startup. The app does not call metadata.create_all in normal operation. ORM UTC/default values are applied when the app creates rows; a raw SQL insertion must supply required fields without server defaults."
        ),
        p(
            "Downgrading 0002 would restore the old settlement cap. If larger payments already exist, the downgrade fails atomically rather than deleting or rewriting those records. Take a backup and inspect data compatibility before attempting any downgrade."
        ),
        p("Tests and evidence", "H2"),
        p(
            "Integration tests migrate isolated PostgreSQL schemas and verify constraints, snapshot shares, aggregate-payment migration behavior, concurrent settlement rejection and reports that remain consistent without blocking writers. Unit tests cover money arithmetic, zero-sum conservation, category rules and exact optimization. The final baseline has 87 passing tests: 54 unit and 33 PostgreSQL integration tests, including deployment configuration checks."
        ),
        p("With more time", "H2"),
        p(
            "Add authenticated group authorization, idempotency keys for recording, an explicit reversal/correction model, and measured query optimization. Multi-currency support needs currency-specific minor units and a clear exchange-rate policy; merely removing the INR check would be insufficient. Membership removal needs historical validity rules because existing financial references must remain intact."
        ),
        p(
            f'Implementation references: <link href="{REPO}/blob/main/app/models.py" color="#087F8C">app/models.py</link>, <link href="{REPO}/tree/main/migrations/versions" color="#087F8C">migration revisions</link>, decisions.md and flow.md. The version stamp identifies the code revision this guide explains.',
            "Small",
        ),
    ]
    section(s, "13. Schema lifecycle on Render")
    s += [
        p(
            f'The live application at <link href="{LIVE}/" color="#087F8C">{LIVE}/</link> uses a managed Render PostgreSQL 18 instance in Oregon. That version/region was checked in Render. The local Docker and test database image, and the reusable Blueprint, specify PostgreSQL 17. Both environments use the same six-table logical schema and Alembic head 0002; the live HTTP scenario was also verified.'
        ),
        code(
            "Render web process\n  -> python -m scripts.start_render\n  -> Alembic upgrade head against DATABASE_URL\n  -> idempotent seed transaction\n  -> Uvicorn binds 0.0.0.0 to PORT\n  -> UI and financial API use the same PostgreSQL store"
        ),
        p("Hosted configuration", "H2"),
        p(
            "DATABASE_URL is set in Render's service environment, not committed in a .env file. Settings parses standard PostgreSQL URIs and selects the installed Psycopg driver without losing encoded passwords or SSL query options. The database remains separate from the web container's ephemeral filesystem."
        ),
        p("Why schema creation precedes serving", "H2"),
        p(
            "A real deployment check found connectivity readiness succeeding while group queries failed because the groups table did not exist. The manually created web service was using the default Docker command and skipped migrations. Setting its Docker Command to python -m scripts.start_render applied revisions and created the seed. The Health Check Path is /health/ready; its SELECT 1 is a connectivity test, not a schema audit."
        ),
        p("Seed history is preserved", "H2"),
        p(
            "Seeding uses a PostgreSQL advisory lock and one transaction. If Goa Trip (demo) already exists, startup does not overwrite its expenses, shares or payments. The browser's fresh-demo action creates another group through normal APIs rather than deleting or resetting the shared seed."
        ),
        note(
            "Persistence limit",
            "The free web service may sleep, but durable expense data is stored in the separate database. Free Render PostgreSQL expires 30 days after creation and is not an indefinite archival store. Production work would add an approved persistent hosting plan, backups, authentication and a dedicated migration stage.",
        ),
        p(
            'Hosting reference: <link href="https://render.com/docs/free" color="#087F8C">Render free-service and database limits</link>. The schema and API remain independently runnable through Docker/local setup if the hosted review window expires.',
            "Small",
        ),
    ]
    build("database-schema-explanation.pdf", "Database Schema Explanation", s)


def render_and_verify():
    report = {}
    for path in OUT.glob("*.pdf"):
        doc = pymupdf.open(path)
        extracted = "\n".join(page.get_text() for page in doc)
        assert "Table of contents" not in extracted or len(extracted) > 1000
        pages = []
        for i, page in enumerate(doc):
            pix = page.get_pixmap(matrix=pymupdf.Matrix(1.35, 1.35), alpha=False)
            img_path = TMP / f"{path.stem}-{i + 1:02}.png"
            pix.save(img_path)
            pages.append(img_path)
            for block in page.get_text("dict")["blocks"]:
                if block.get("type") != 0:
                    continue
                for line in block["lines"]:
                    for span in line["spans"]:
                        x0, y0, x1, y1 = span["bbox"]
                        assert x0 >= 30 and x1 <= W - 30, (
                            path.name,
                            i + 1,
                            span["text"],
                            span["bbox"],
                        )
                        assert y0 >= 10 and y1 <= H - 9, (path.name, i + 1, span["text"])
        # Contact sheets: all pages visible, at 40% scale; full-size PNGs retained for detailed review.
        for start in range(0, len(pages), 9):
            subset = pages[start : start + 9]
            sheet = Image.new("RGB", (930, 490 * ((len(subset) + 2) // 3)), "#dce3e8")
            draw = ImageDraw.Draw(sheet)
            for j, file in enumerate(subset):
                im = Image.open(file)
                im.thumbnail((295, 448))
                x, y = (j % 3) * 310 + 7, (j // 3) * 490 + 24
                sheet.paste(im, (x, y))
                draw.text((x, y - 18), f"{path.stem} / {start + j + 1}", fill="#112d43")
            sheet.save(TMP / f"{path.stem}-contact-{start // 9 + 1}.png")
        (TMP / f"{path.stem}.txt").write_text(extracted, encoding="utf-8")
        report[path.name] = {
            "pages": len(doc),
            "bytes": path.stat().st_size,
            "text_characters": len(extracted),
        }
        assert len(PdfReader(path).pages) == len(doc)
    collection = ROOT / "docs" / "expense-sharing.postman_collection.json"
    data = json.loads(collection.read_text(encoding="utf-8"))
    assert len(data["item"]) == 21
    shutil.copyfile(collection, OUT.parent / collection.name)
    (TMP / "verification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    setup_guide()
    api_guide()
    schema_guide()
    render_and_verify()
