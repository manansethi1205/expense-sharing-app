import json
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


def test_postman_walkthrough_runs_twice_with_captured_ids(api):
    """Execute the collection's HTTP requests; do not evaluate arbitrary JavaScript."""
    client, _ = api
    collection = json.loads(Path("docs/expense-sharing.postman_collection.json").read_text())
    for _ in range(2):
        variables = {"base_url": "/api/v1"}

        def resolve(value, values=variables):
            return re.sub(r"\{\{(\w+)\}\}", lambda match: str(values[match[1]]), value)

        for item in collection["item"]:
            request = item["request"]
            body = json.loads(resolve(request["body"]["raw"])) if "body" in request else None
            response = client.request(request["method"], resolve(request["url"]), json=body)
            script = "\n".join(item["event"][0]["script"]["exec"])
            expected = int(re.search(r"to\.have\.status\((\d+)\)", script)[1])
            assert response.status_code == expected, (item["name"], response.text)
            capture = re.search(r'collectionVariables\.set\("([^"]+)"', script)
            if capture:
                variables[capture[1]] = response.json()["id"]
            if item["name"] == "Verify fully settled":
                assert response.json()["is_settled"] and response.json()["balances"] == []
            if item["name"] == "Personal spending versus paid":
                assert response.json()["totals"]["spending"] == "400.00"
                assert response.json()["totals"]["paid"] == "1200.00"
