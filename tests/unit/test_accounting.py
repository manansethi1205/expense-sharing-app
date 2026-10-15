from decimal import Decimal
from functools import cache
from itertools import product

import pytest
from pydantic import TypeAdapter, ValidationError

from app.domain.balances import Transfer, direct_balances, net_positions
from app.domain.categories import classify_description
from app.domain.money import format_money, to_minor
from app.domain.settlements import greedy_transfers, suggest_transfers, validate_settlement
from app.domain.splits import equal_shares, validate_custom_shares
from app.schemas import ExpenseCreate, SettlementCreate


def test_assignment_example_and_settlement():
    shares = equal_shares(120000, [1, 2, 3])
    debts = [Transfer(user, 1, amount) for user, amount in shares.items() if user != 1]
    assert direct_balances(debts, []) == [Transfer(2, 1, 40000), Transfer(3, 1, 40000)]
    assert net_positions([1, 2, 3], debts, []) == {1: 80000, 2: -40000, 3: -40000}
    assert direct_balances(debts, [Transfer(2, 1, 40000)]) == [Transfer(3, 1, 40000)]


def test_rounding_conservation_and_tiny_amount():
    assert equal_shares(10000, [3, 1, 2]) == {1: 3334, 2: 3333, 3: 3333}
    assert equal_shares(1, [1, 2, 3]) == {1: 1, 2: 0, 3: 0}
    assert equal_shares(77, [1]) == {1: 77}
    assert format_money(to_minor(Decimal("1000.01"))) == "1000.01"
    assert format_money(-1) == "-0.01"


@pytest.mark.parametrize("amount", ["0", "-1", "NaN", "Infinity", "0.001", "10000000.01", True])
def test_expense_rejects_invalid_money(amount):
    with pytest.raises(ValidationError):
        TypeAdapter(ExpenseCreate).validate_python(
            {"paid_by": 1, "amount": amount, "description": "Dinner"}
        )


def test_equal_is_default_and_rejects_custom_fields():
    adapter = TypeAdapter(ExpenseCreate)
    payload = {"paid_by": 1, "amount": 1200, "description": " Dinner "}
    assert adapter.validate_python(payload).split_type == "equal"
    assert adapter.validate_python(payload).description == "Dinner"
    with pytest.raises(ValidationError):
        adapter.validate_python(payload | {"splits": []})
    with pytest.raises(ValidationError):
        adapter.validate_python(payload | {"occurred_at": "2026-01-01T12:00:00"})


@pytest.mark.parametrize(
    "shares",
    [
        [(1, 50), (1, 50)],
        [(1, 100)],
        [(1, 50), (3, 50)],
        [(1, -1), (2, 101)],
        [(1, 50), (2, 49)],
    ],
)
def test_custom_invalid_shares(shares):
    with pytest.raises(ValueError):
        validate_custom_shares(100, [1, 2], shares)


def test_custom_allows_zero_and_reciprocal_debts_cancel():
    assert validate_custom_shares(100, [1, 2], [(1, 0), (2, 100)]) == {1: 0, 2: 100}
    assert direct_balances([Transfer(1, 2, 80), Transfer(2, 1, 50)], []) == [Transfer(1, 2, 30)]


@cache
def brute_minimum(values: tuple[int, ...]) -> int:
    """Independent exhaustive transfer search; intentionally not the subset-DP recurrence."""
    active = [value for value in values if value]
    if not active:
        return 0
    first, rest = active[0], active[1:]
    best = len(active)
    for index, value in enumerate(rest):
        if first * value < 0:
            merged = rest.copy()
            merged[index] += first
            best = min(best, 1 + brute_minimum(tuple(sorted(merged))))
    return best


def assert_clears(positions, plan):
    remaining = positions.copy()
    for transfer in plan.transfers:
        assert transfer.amount_minor > 0 and transfer.from_user_id != transfer.to_user_id
        remaining[transfer.from_user_id] += transfer.amount_minor
        remaining[transfer.to_user_id] -= transfer.amount_minor
    assert not any(remaining.values())


def test_exact_matches_independent_oracle_exhaustively():
    # 625 independently generated small inputs, including repeated and zero positions.
    for prefix in product(range(-2, 3), repeat=4):
        values = (*prefix, -sum(prefix))
        positions = dict(enumerate(values, start=1))
        original = positions.copy()
        plan = suggest_transfers(positions)
        assert len(plan.transfers) == brute_minimum(tuple(sorted(values)))
        assert plan.strategy == "exact" and plan.optimality_guaranteed
        assert_clears(positions, plan)
        assert positions == original


def test_greedy_counterexample_and_determinism():
    positions = {1: -90000, 2: -80000, 3: -40000, 4: 80000, 5: 70000, 6: 60000}
    assert len(greedy_transfers(positions)) == 5
    exact = suggest_transfers(positions)
    assert len(exact.transfers) == 4
    assert exact == suggest_transfers(dict(reversed(list(positions.items()))))
    assert_clears(positions, exact)


def test_cutoff_counts_active_members_and_empty_is_optimal():
    sixteen = {i: (-1 if i % 2 else 1) for i in range(16)}
    seventeen = {i: -1 for i in range(16)} | {16: 16}
    assert suggest_transfers(sixteen).strategy == "exact"
    plan = suggest_transfers(seventeen)
    assert plan.strategy == "greedy" and not plan.optimality_guaranteed
    assert_clears(seventeen, plan)
    assert suggest_transfers({1: -3, 2: 3} | dict.fromkeys(range(3, 100), 0)).strategy == "exact"
    assert suggest_transfers({1: 0}).optimality_guaranteed
    assert suggest_transfers({1: -3, 2: 3}, threshold=0).strategy == "greedy"
    with pytest.raises(ValueError):
        suggest_transfers({1: 1})


def test_simplified_chain_and_historical_cycle():
    debts = [Transfer(1, 2, 100), Transfer(2, 3, 100)]
    paid = [Transfer(1, 3, 100)]
    assert net_positions([1, 2, 3], debts, paid) == {1: 0, 2: 0, 3: 0}
    assert len(direct_balances(debts, paid)) == 3
    validate_settlement("simplified", 1, 3, 100, {1: -100, 2: 0, 3: 100}, debts)
    with pytest.raises(ValueError):
        validate_settlement("direct", 1, 3, 100, {1: -100, 2: 0, 3: 100}, debts)


@pytest.mark.parametrize(
    "mode,sender,receiver,amount",
    [
        ("direct", 2, 1, 101),
        ("simplified", 1, 2, 1),
        ("direct", 1, 1, 1),
        ("direct", 3, 1, 1),
        ("simplified", 2, 1, 0),
    ],
)
def test_invalid_settlements(mode, sender, receiver, amount):
    with pytest.raises(ValueError):
        validate_settlement(
            mode, sender, receiver, amount, {1: 100, 2: -100}, [Transfer(2, 1, 100)]
        )


def test_settlement_requires_aware_time():
    with pytest.raises(ValidationError):
        SettlementCreate(
            from_user_id=1, to_user_id=2, amount="1", mode="direct", occurred_at="2026-01-01"
        )


@pytest.mark.parametrize(
    "description,category,source",
    [
        ("Auto ride", "travel", "rule"),
        ("Taxi airport", "travel", "rule"),
        ("FLIGHT", "travel", "rule"),
        ("cab", "travel", "rule"),
        ("bike", "travel", "rule"),
        ("Bike purchase", "shopping", "rule"),
        ("Hotel dinner", "food", "rule"),
        ("cab dinner", "other", "fallback"),
        ("cabinet", "other", "fallback"),
        ("unknown", "other", "fallback"),
        ("ｔａｘｉ", "travel", "rule"),
    ],
)
def test_category_rules(description, category, source):
    result = classify_description(description)
    assert (result.category, result.source) == (category, source)
