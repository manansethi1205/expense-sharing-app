import pytest

pytestmark = pytest.mark.integration


def custom_expense(client, group, payer, users, amounts):
    return client.post(
        f"/api/v1/groups/{group}/expenses",
        json={
            "description": "Custom allocation",
            "paid_by": payer,
            "amount": sum(amounts.values()),
            "split_type": "custom",
            "splits": [{"user_id": user, "amount": amounts.get(user, 0)} for user in users],
        },
    )


def test_exact_api_counterexample_fallback_and_simplified_clearance(trip):
    client, application, group, debtors = trip
    creditors = []
    for name in ("D", "E", "F"):
        user = client.post("/api/v1/users", json={"name": name}).json()["id"]
        client.put(f"/api/v1/groups/{group}/members/{user}")
        creditors.append(user)
    users = debtors + creditors
    allocations = [
        {debtors[0]: 800},
        {debtors[1]: 700},
        {debtors[0]: 100, debtors[1]: 100, debtors[2]: 400},
    ]
    for payer, amounts in zip(creditors, allocations, strict=True):
        result = custom_expense(client, group, payer, users, amounts)
        assert result.status_code == 201, result.text
    plan = client.get(f"/api/v1/groups/{group}/settlement-suggestions").json()
    assert plan["transaction_count"] == 4 and plan["optimality_guaranteed"]
    application.state.settings.exact_settlement_threshold = 0
    fallback = client.get(f"/api/v1/groups/{group}/settlement-suggestions").json()
    assert fallback["strategy"] == "greedy" and not fallback["optimality_guaranteed"]
    assert fallback["transaction_count"] == 5
    for transfer in plan["transfers"]:
        result = client.post(
            f"/api/v1/groups/{group}/settlements",
            json={
                "from_user_id": transfer["from_user"]["id"],
                "to_user_id": transfer["to_user"]["id"],
                "amount": transfer["amount"],
                "mode": "simplified",
            },
        )
        assert result.status_code == 201, result.text
    assert client.get(f"/api/v1/groups/{group}/balances?view=net").json()["is_settled"]
    assert (
        client.get(f"/api/v1/groups/{group}/settlement-suggestions?mode=direct").json()[
            "transaction_count"
        ]
        == 0
    )


def test_simplified_chain_explains_historical_cycle(trip):
    client, _, group, users = trip
    a, b, c = users
    for payer, debtor in ((b, a), (c, b)):
        assert custom_expense(client, group, payer, users, {debtor: 100}).status_code == 201
    assert (
        client.post(
            f"/api/v1/groups/{group}/settlements",
            json={"from_user_id": a, "to_user_id": c, "amount": 100, "mode": "direct"},
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"/api/v1/groups/{group}/settlements",
            json={"from_user_id": a, "to_user_id": c, "amount": 100, "mode": "simplified"},
        ).status_code
        == 201
    )
    direct = client.get(f"/api/v1/groups/{group}/balances").json()
    assert (
        direct["is_settled"]
        and len(direct["balances"]) == 3
        and "historical" in direct["explanation"]
    )
    assert (
        client.get(f"/api/v1/groups/{group}/settlement-suggestions?mode=direct").json()["transfers"]
        == []
    )


def test_duplicate_names_and_resource_validation(trip):
    client, _, group, users = trip
    duplicate = client.post("/api/v1/users", json={"name": "Mohit"}).json()["id"]
    assert duplicate != users[0]
    hits = client.get("/api/v1/search?q=Mohit&types=users").json()["items"]
    assert {hit["id"] for hit in hits} == {duplicate, users[0]}
    assert client.get("/api/v1/users/99999").status_code == 404
    assert client.get("/api/v1/groups/99999").status_code == 404
    assert client.get("/api/v1/groups?user_id=99999").status_code == 404
    assert client.put(f"/api/v1/groups/{group}/members/99999").status_code == 404
    assert client.get(f"/api/v1/groups/{group}/expenses?limit=101").status_code == 422
