"""Run the assignment scenario against a live API (creates synthetic demo records)."""

import argparse
import json
import urllib.request


def smoke(base: str):
    def request(path, body=None, method=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            base.rstrip("/") + path,
            data=data,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            return json.load(response)

    assert request("/health/ready")["status"] == "ready"
    assert "/api/v1/groups/{group_id}/expenses" in request("/openapi.json")["paths"]
    users = [request("/api/v1/users", {"name": name})["id"] for name in ("Mohit", "Rahul", "Ankit")]
    group = request("/api/v1/groups", {"name": "HTTP verification trip"})["id"]
    for user in users:
        request(f"/api/v1/groups/{group}/members/{user}", method="PUT")
    expense = request(
        f"/api/v1/groups/{group}/expenses",
        {"paid_by": users[0], "amount": 1200, "description": "Dinner"},
    )
    assert [share["amount"] for share in expense["shares"]] == ["400.00"] * 3
    balances = request(f"/api/v1/groups/{group}/balances")
    assert len(balances["balances"]) == 2
    personal = request(f"/api/v1/users/{users[0]}/analytics")
    assert personal["totals"]["spending"] == "400.00" and personal["totals"]["paid"] == "1200.00"
    plan = request(f"/api/v1/groups/{group}/settlement-suggestions")
    assert plan["optimality_guaranteed"] and plan["transaction_count"] == 2
    for transfer in plan["transfers"]:
        request(
            f"/api/v1/groups/{group}/settlements",
            {
                "from_user_id": transfer["from_user"]["id"],
                "to_user_id": transfer["to_user"]["id"],
                "amount": transfer["amount"],
                "mode": "simplified",
            },
        )
    assert request(f"/api/v1/groups/{group}/balances")["is_settled"]
    assert request(f"/api/v1/search?q=verification&group_id={group}")["total"] >= 1
    return {
        "status": "passed",
        "base_url": base,
        "group_id": group,
        "checks": [
            "health",
            "openapi",
            "users",
            "membership",
            "equal_split",
            "balances",
            "analytics",
            "exact_plan",
            "recorded_settlements",
            "search",
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    print(json.dumps(smoke(parser.parse_args().base_url), indent=2))
