from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app import reporting, services
from app.schemas import EqualExpense

pytestmark = pytest.mark.integration


def custom(client, group, users, debtor, creditor, amount):
    response = client.post(
        f"/api/v1/groups/{group}/expenses",
        json={
            "paid_by": creditor,
            "amount": amount,
            "description": "Audit expense",
            "split_type": "custom",
            "splits": [
                {"user_id": user, "amount": amount if user == debtor else 0} for user in users
            ],
        },
    )
    assert response.status_code == 201, response.text


def pay_plan(client, group, mode):
    plan = client.get(f"/api/v1/groups/{group}/settlement-suggestions?mode={mode}").json()
    for transfer in plan["transfers"]:
        response = client.post(
            f"/api/v1/groups/{group}/settlements",
            json={
                "from_user_id": transfer["from_user"]["id"],
                "to_user_id": transfer["to_user"]["id"],
                "amount": transfer["amount"],
                "mode": mode,
            },
        )
        assert response.status_code == 201, response.text
    assert client.get(f"/api/v1/groups/{group}/balances").json()["is_settled"]
    return plan


@pytest.mark.parametrize("mode", ["direct", "simplified"])
def test_aggregate_suggestion_above_expense_cap_is_recordable(trip, mode):
    client, _, group, users = trip
    for _ in range(2):
        custom(client, group, users, users[0], users[1], "10000000.00")
    plan = pay_plan(client, group, mode)
    assert plan["transaction_count"] == 1
    assert plan["transfers"][0]["amount"] == "20000000.00"
    assert plan["optimality_guaranteed"] == (mode == "simplified")


def test_direct_plan_omits_independent_cycle_and_keeps_explanatory_history(trip):
    client, _, group, users = trip
    for name in ("D", "E"):
        user = client.post("/api/v1/users", json={"name": name}).json()["id"]
        client.put(f"/api/v1/groups/{group}/members/{user}")
        users.append(user)
    for debtor, creditor in (
        (users[0], users[1]),
        (users[2], users[3]),
        (users[3], users[4]),
        (users[4], users[2]),
    ):
        custom(client, group, users, debtor, creditor, 100)
    assert pay_plan(client, group, "direct")["transaction_count"] == 1
    balances = client.get(f"/api/v1/groups/{group}/balances").json()
    assert len(balances["balances"]) == 3 and "historical" in balances["explanation"]


@pytest.mark.parametrize("target", ["user", "group", "description", "note", "query"])
def test_null_text_returns_422_without_database_errors(trip, target):
    client, _, group, users = trip
    if target == "user":
        response = client.post("/api/v1/users", json={"name": "bad\x00name"})
    elif target == "group":
        response = client.post("/api/v1/groups", json={"name": "bad\x00name"})
    elif target == "description":
        response = client.post(
            f"/api/v1/groups/{group}/expenses",
            json={"paid_by": users[0], "amount": 100, "description": "bad\x00text"},
        )
    elif target == "note":
        response = client.post(
            f"/api/v1/groups/{group}/settlements",
            json={
                "from_user_id": users[0],
                "to_user_id": users[1],
                "amount": 1,
                "mode": "direct",
                "note": "bad\x00note",
            },
        )
    else:
        response = client.get("/api/v1/search", params={"q": "bad\x00query"})
    assert response.status_code == 422 and "null characters" in response.text


@pytest.mark.parametrize(
    "query,feature",
    [
        ("custom split", "custom-split"),
        ("unequal split", "custom-split"),
        ("create user", "users"),
        ("add member", "membership"),
        ("group report", "group-analytics"),
        ("spending details", "drilldown"),
        ("change category", "category-correction"),
    ],
)
def test_feature_discovery_includes_multiword_capabilities(api, query, feature):
    client, _ = api
    response = client.get("/api/v1/search", params={"q": query, "types": "features"})
    assert response.status_code == 200
    assert feature in {item["id"] for item in response.json()["items"]}


def test_sql_reports_labels_drilldown_and_filters(trip):
    client, _, group, users = trip
    for index in range(7):
        response = client.post(
            f"/api/v1/groups/{group}/expenses",
            json={
                "paid_by": users[0],
                "amount": 300,
                "description": "Dinner" if index % 2 else "bus tickets",
                "occurred_at": f"2026-02-{index + 1:02d}T12:00:00Z",
            },
        )
        assert response.status_code == 201
    report = client.get(f"/api/v1/users/{users[1]}/analytics?from=2026-02-01&to=2026-03-01").json()
    assert report["totals"]["spending"] == "700.00"
    assert report["groups"][0]["label"] == "Goa Trip"
    assert len(report["largest_expenses"]) == 5
    first = client.get(report["drilldown_path"] + "&limit=3").json()
    second = client.get(report["drilldown_path"] + "&limit=3&offset=3").json()
    assert first["total"] == second["total"] == 7
    assert not {row["expense_id"] for row in first["items"]} & {
        row["expense_id"] for row in second["items"]
    }
    assert first["items"][0]["group"]["name"] == "Goa Trip"
    assert first["items"][0]["paid_by"]["name"] == "Mohit"
    assert first["items"][0]["amount"] == "100.00"
    assert client.get(report["drilldown_path"] + "&category=travel").json()["total"] == 4
    grouped = client.get(f"/api/v1/groups/{group}/analytics").json()
    assert {row["label"] for row in grouped["members"]} == {"Mohit", "Rahul", "Ankit"}
    assert grouped["totals"]["spending"] == "2100.00"
    assert (
        client.get(f"/api/v1/groups/{group}/analytics/expenses?sort=date_desc&limit=1").json()[
            "items"
        ][0]["amount"]
        == "300.00"
    )
    # The user's consumption was 100 per expense, rather than the group's 300.
    assert client.get(report["drilldown_path"] + "&from=2026-02-08").json()["total"] == 0


def test_report_snapshot_is_consistent_and_does_not_block_writer(trip, monkeypatch):
    client, application, group, users = trip
    initial = EqualExpense(paid_by=users[0], amount="1200.00", description="Dinner")
    with application.state.sessions() as session:
        services.create_expense(session, group, initial)
    snapshot_ready, writer_done = Event(), Event()
    original = reporting.report_scope

    def paused_scope(session, *args, **kwargs):
        scope = original(session, *args, **kwargs)
        assert session.scalar(text("SHOW transaction_isolation")) == "repeatable read"
        assert session.scalar(text("SHOW transaction_read_only")) == "on"
        snapshot_ready.set()
        assert writer_done.wait(timeout=10), "Report unexpectedly blocked an expense write"
        return scope

    monkeypatch.setattr(reporting, "report_scope", paused_scope)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(client.get, f"/api/v1/users/{users[0]}/analytics")
        assert snapshot_ready.wait(timeout=10)
        try:
            with application.state.sessions() as session:
                session.execute(text("SET lock_timeout = '2s'"))
                session.commit()
                services.create_expense(session, group, initial)
        finally:
            writer_done.set()
        response = future.result(timeout=10)
    assert response.status_code == 200 and response.json()["totals"]["spending"] == "400.00"
    monkeypatch.setattr(reporting, "report_scope", original)
    assert (
        client.get(f"/api/v1/users/{users[0]}/analytics").json()["totals"]["spending"] == "800.00"
    )


def test_downgrade_refuses_to_truncate_large_settlement(trip):
    client, application, group, users = trip
    for _ in range(2):
        custom(client, group, users, users[0], users[1], "10000000.00")
    pay_plan(client, group, "simplified")
    config = Config("alembic.ini")
    config.attributes["database_url"] = application.state.settings.database_url
    with pytest.raises(IntegrityError):
        command.downgrade(config, "0001")
    with application.state.sessions() as session:
        assert session.scalar(text("SELECT version_num FROM alembic_version")) == "0002"
        assert session.scalar(text("SELECT amount_minor FROM settlements")) == 2_000_000_000
