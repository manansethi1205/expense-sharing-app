import random

import pytest
from pydantic import ValidationError

from app.domain.balances import Transfer, direct_balances, net_positions, remove_circulation
from app.domain.categories import classify_description
from app.domain.money import MAX_SETTLEMENT_AMOUNT, MAX_SETTLEMENT_MINOR, to_minor
from app.schemas import SettlementCreate


def test_settlement_limit_uses_bigint_capacity_and_exact_precision():
    payload = dict(from_user_id=1, to_user_id=2, mode="simplified")
    amount = SettlementCreate(**payload, amount=str(MAX_SETTLEMENT_AMOUNT)).amount
    assert to_minor(amount) == MAX_SETTLEMENT_MINOR
    assert SettlementCreate(**payload, amount="20000000.00").amount == 20_000_000
    for value in ("92233720368547758.08", "20000000.001", "NaN", "0", "-1"):
        with pytest.raises(ValidationError):
            SettlementCreate(**payload, amount=value)


def test_cycle_cancellation_preserves_capacities_and_replayability():
    randomizer = random.Random(822)
    for _ in range(100):
        members = list(range(6))
        original = direct_balances(
            [
                Transfer(a, b, randomizer.randint(1, 100))
                for a in members
                for b in members
                if a != b and randomizer.random() < 0.4
            ],
            [],
        )
        expected = net_positions(members, original, [])
        plan = remove_circulation(original)
        assert plan == remove_circulation(list(reversed(original)))
        assert net_positions(members, plan, []) == expected
        capacities = {(t.from_user_id, t.to_user_id): t.amount_minor for t in original}
        settled = []
        for transfer in plan:
            assert any(net_positions(members, original, settled).values())
            assert (
                0 < transfer.amount_minor <= capacities[transfer.from_user_id, transfer.to_user_id]
            )
            settled.append(transfer)
        assert not any(net_positions(members, original, settled).values())


@pytest.mark.parametrize(
    "description,category",
    [
        ("bus tickets", "travel"),
        ("flight ticket", "travel"),
        ("train to Goa tickets", "travel"),
        ("Hotel dinner and flight", "other"),
        ("hotel dinner", "food"),
        ("Bike purchase", "shopping"),
        ("bike rental and dinner", "other"),
        ("museum tickets", "activities"),
        ("tickets", "activities"),
        ("bus concert tickets", "other"),
        ("bus dinner flight tickets", "other"),
    ],
)
def test_category_specificity_and_surrounding_context(description, category):
    result = classify_description(description)
    assert result.category == category
    assert result.rule.startswith("v2:")
