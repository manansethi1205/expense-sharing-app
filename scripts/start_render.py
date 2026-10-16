"""Single-instance free demo startup: migrate, seed once, then serve UI and API."""

import os

import uvicorn
from alembic import command
from alembic.config import Config

from scripts.seed_demo import seed


def main():
    command.upgrade(Config("alembic.ini"), "head")
    seed()  # Existing synthetic group is preserved, including reviewer changes.
    uvicorn.run("app.main:app", host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))


if __name__ == "__main__":
    main()
