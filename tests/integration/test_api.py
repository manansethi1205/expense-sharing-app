from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app import services
from app.domain.balances import Transfer
from app.models import Expense, Member, Share
from app.schemas import SettlementCreate

pytestmark = pytest.mark.integration


def dinner(client, group, payer, **extra):
    return client.post(
        f"/api/v1/groups/{group}/expenses",
        json={"paid_by": payer, "amount": 1200, "description": "Dinner", **extra},
    )


def test_assignment_end_to_end(trip):
    client, _, group, users = trip
    mohit, rahul, ankit = users
    response = dinner(client, group, mohit)
    assert response.status_code == 201, response.text
    expense = response.json()
    assert expense["amount"] == "1200.00" and expense["category"] == "food"
    assert [share["amount"] for share in expense["shares"]] == ["400.00"] * 3
    balances = client.get(f"/api/v1/groups/{group}/balances").json()
    assert {
        (t["from_user"]["id"], t["to_user"]["id"], t["amount"]) for t in balances["balances"]
    } == {(rahul, mohit, "400.00"), (ankit, mohit, "400.00")}
    plan = client.get(f"/api/v1/groups/{group}/settlement-suggestions").json()
    assert (
        plan["strategy"] == "exact"
        and plan["optimality_guaranteed"]
        and plan["transaction_count"] == 2
    )
    payment = client.post(
        f"/api/v1/groups/{group}/settlements",
        json={"from_user_id": rahul, "to_user_id": mohit, "amount": "150.00", "mode": "direct"},
    )
    assert payment.status_code == 201, payment.text
    balances = client.get(f"/api/v1/groups/{group}/balances").json()["balances"]
    assert next(b["amount"] for b in balances if b["from_user"]["id"] == rahul) == "250.00"
    assert client.get(f"/api/v1/groups/{group}/expenses").json()["total"] == 1
    assert client.get(f"/api/v1/groups/{group}/settlements").json()["total"] == 1
    assert (
        client.get(f"/api/v1/users/{rahul}/balances").json()["groups"][0]["balances"][0]["amount"]
        == "-250.00"
    )
    assert client.get("/health/ready").status_code == 200


def test_validation_and_atomicity(trip):
    client, app, group, users = trip
    for amount in (0, -1, "0.001", "NaN", "10000000.01"):
        response = dinner(client, group, users[0], amount=amount)
        assert response.status_code == 422 and "error" in response.json()
    assert dinner(client, 999999, users[0]).status_code == 404
    outsider = client.post("/api/v1/users", json={"name": "Outsider"}).json()["id"]
    assert dinner(client, group, outsider).status_code == 409
    custom = {"split_type": "custom", "splits": [{"user_id": users[0], "amount": 1200}]}
    assert dinner(client, group, users[0], **custom).status_code == 422
    with app.state.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Expense)) == 0
        assert session.scalar(select(func.count()).select_from(Share)) == 0
    assert client.post("/api/v1/users", json={"name": "   "}).status_code == 422
    assert (
        client.post("/api/v1/groups", json={"name": "Trip", "timezone": "invalid"}).status_code
        == 422
    )
    assert (
        client.get(f"/api/v1/groups/{group}/expenses?from=2026-02-01&to=2026-01-01").status_code
        == 422
    )


def test_membership_snapshot_and_rounding(trip):
    client, _, group, users = trip
    expense = dinner(client, group, users[0], amount="100.00").json()
    assert [s["amount"] for s in expense["shares"]] == ["33.34", "33.33", "33.33"]
    newcomer = client.post("/api/v1/users", json={"name": "New member"}).json()["id"]
    assert client.put(f"/api/v1/groups/{group}/members/{newcomer}").status_code == 201
    assert client.put(f"/api/v1/groups/{group}/members/{newcomer}").status_code == 200
    assert (
        client.get(f"/api/v1/groups/{group}/expenses/{expense['id']}").json()["shares"]
        == expense["shares"]
    )
    report = client.get(f"/api/v1/users/{newcomer}/analytics").json()
    assert report["totals"]["spending"] == "0.00" and not report["largest_expenses"]
    next_expense = dinner(client, group, users[0], amount="100.00").json()
    assert [s["amount"] for s in next_expense["shares"]] == ["25.00"] * 4


def test_analytics_cashflow_categories_and_date_boundary(trip):
    client, _, group, users = trip
    dinner(client, group, users[0], occurred_at="2026-01-31T18:30:00Z")  # Feb 1 in Kolkata
    client.post(
        f"/api/v1/groups/{group}/settlements",
        json={
            "from_user_id": users[1],
            "to_user_id": users[0],
            "amount": 400,
            "mode": "direct",
            "occurred_at": "2026-02-02T00:00:00Z",
        },
    )
    for user, paid, sent, received in (
        (users[0], "1200.00", "0.00", "400.00"),
        (users[1], "0.00", "400.00", "0.00"),
    ):
        report = client.get(f"/api/v1/users/{user}/analytics?from=2026-02-01&to=2026-03-01").json()
        assert report["totals"]["spending"] == "400.00"
        assert report["totals"]["paid"] == paid
        assert report["totals"]["settlements_sent"] == sent
        assert report["totals"]["settlements_received"] == received
        assert report["months"][0]["key"] == "2026-02"
        assert report["categories"][0]["amount"] == "400.00"
    group_report = client.get(f"/api/v1/groups/{group}/analytics").json()
    assert group_report["totals"]["spending"] == "1200.00"
    assert sum(float(row["amount"]) for row in group_report["members"]) == 1200
    assert (
        client.get(f"/api/v1/groups/{group}/analytics?from=2026-01-01&to=2026-02-01").json()[
            "totals"
        ]["spending"]
        == "0.00"
    )
    assert client.get(f"/api/v1/groups/{group}/analytics?timezone=invalid").status_code == 422


def test_search_scope_wildcards_ranking_and_manual_override(trip):
    client, _, group, users = trip
    expense = dinner(client, group, users[0], description="Taxi to Goa").json()
    assert expense["category"] == "travel"
    assert (
        client.patch(
            f"/api/v1/groups/{group}/expenses/{expense['id']}/category", json={"category": "other"}
        ).json()["category_source"]
        == "manual"
    )
    hits = client.get("/api/v1/search?q=Goa").json()
    assert {hit["type"] for hit in hits["items"]} == {"groups", "expenses"}
    assert client.get("/api/v1/search?q=settle&types=features").json()["total"] > 0
    assert client.get("/api/v1/search?q=%25&types=groups,expenses").json()["total"] == 0
    assert client.get("/api/v1/search?q=_&types=groups,expenses").json()["total"] == 0
    assert client.get("/api/v1/search?q=go&types=invalid").status_code == 422
    assert client.get("/api/v1/search?q=%20%20").status_code == 422
    other = client.post("/api/v1/groups", json={"name": "Goa outside"}).json()["id"]
    scoped = client.get(f"/api/v1/search?q=Goa&user_id={users[0]}").json()
    assert not any(h["type"] == "groups" and h["id"] == other for h in scoped["items"])
    assert (
        client.get(f"/api/v1/search?q=Goa&user_id={users[0]}&group_id={other}").json()["total"] == 0
    )
    all_hits = client.get("/api/v1/search?q=a").json()
    pages = [
        client.get(f"/api/v1/search?q=a&limit=1&offset={i}").json()["items"][0]
        for i in range(all_hits["total"])
    ]
    assert pages == all_hits["items"]


def test_custom_split_and_wrong_group(trip):
    client, _, group, users = trip
    expense = dinner(
        client,
        group,
        users[0],
        amount=1000,
        split_type="custom",
        splits=[
            {"user_id": user, "amount": amount}
            for user, amount in zip(users, (500, 300, 200), strict=True)
        ],
    )
    assert expense.status_code == 201
    assert [s["amount"] for s in expense.json()["shares"]] == ["500.00", "300.00", "200.00"]
    other = client.post("/api/v1/groups", json={"name": "Other"}).json()["id"]
    assert client.get(f"/api/v1/groups/{other}/expenses/{expense.json()['id']}").status_code == 404


def test_oversized_self_nonmember_and_full_settlements(trip):
    client, _, group, users = trip
    dinner(client, group, users[0])
    for sender, receiver, amount in (
        (users[1], users[0], 401),
        (users[1], users[1], 1),
        (99999, users[0], 1),
    ):
        assert (
            client.post(
                f"/api/v1/groups/{group}/settlements",
                json={
                    "from_user_id": sender,
                    "to_user_id": receiver,
                    "amount": amount,
                    "mode": "direct",
                },
            ).status_code
            == 409
        )
    for sender in users[1:]:
        assert (
            client.post(
                f"/api/v1/groups/{group}/settlements",
                json={
                    "from_user_id": sender,
                    "to_user_id": users[0],
                    "amount": 400,
                    "mode": "direct",
                },
            ).status_code
            == 201
        )
    assert client.get(f"/api/v1/groups/{group}/balances").json()["is_settled"]
    assert (
        client.get(f"/api/v1/groups/{group}/settlement-suggestions").json()["transaction_count"]
        == 0
    )


def test_concurrent_settlements_cannot_overpay(trip):
    client, application, group, users = trip
    dinner(client, group, users[0])
    barrier = Barrier(2)
    payload = SettlementCreate(
        from_user_id=users[1], to_user_id=users[0], amount="300.00", mode="direct"
    )

    def attempt():
        from app.errors import DomainError

        with application.state.sessions() as session:
            barrier.wait(timeout=10)
            try:
                services.record_settlement(session, group, payload)
                return 201
            except DomainError as exc:
                return exc.status

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: attempt(), range(2)))
    assert sorted(results) == [201, 409]
    with application.state.sessions() as session:
        debts, settled = services.load_ledger(session, group)
        assert settled == [Transfer(users[1], users[0], 30000)]


def test_foreign_key_constraints_reject_outsider_share(trip):
    client, application, group, users = trip
    expense = dinner(client, group, users[0]).json()
    outsider = client.post("/api/v1/users", json={"name": "Outsider"}).json()["id"]
    with application.state.sessions() as session, pytest.raises(IntegrityError), session.begin():
        session.add(
            Share(expense_id=expense["id"], group_id=group, user_id=outsider, amount_minor=0)
        )
        session.flush()
    with application.state.sessions() as session:
        assert session.get(Member, (group, outsider)) is None


def test_one_member_expense_and_empty_group(api):
    client, _ = api
    user = client.post("/api/v1/users", json={"name": "Solo"}).json()["id"]
    group = client.post("/api/v1/groups", json={"name": "Solo trip"}).json()["id"]
    assert dinner(client, group, user).status_code == 409
    client.put(f"/api/v1/groups/{group}/members/{user}")
    assert dinner(client, group, user).status_code == 201
    assert client.get(f"/api/v1/groups/{group}/balances").json()["balances"] == []
    assert client.get(f"/api/v1/users/{user}/analytics").json()["totals"]["spending"] == "1200.00"
