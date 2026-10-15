import heapq
from dataclasses import dataclass

from app.domain.balances import Transfer


@dataclass(frozen=True)
class Plan:
    transfers: list[Transfer]
    strategy: str
    objective: str
    optimality_guaranteed: bool


def greedy_transfers(positions: dict[int, int]) -> list[Transfer]:
    debtors = [(-abs(amount), user) for user, amount in positions.items() if amount < 0]
    creditors = [(-amount, user) for user, amount in positions.items() if amount > 0]
    heapq.heapify(debtors)
    heapq.heapify(creditors)
    transfers = []
    while debtors and creditors:
        debt, sender = heapq.heappop(debtors)
        credit, receiver = heapq.heappop(creditors)
        amount = min(-debt, -credit)
        transfers.append(Transfer(sender, receiver, amount))
        if debt + amount:
            heapq.heappush(debtors, (debt + amount, sender))
        if credit + amount:
            heapq.heappush(creditors, (credit + amount, receiver))
    return transfers


def exact_partition(positions: dict[int, int]) -> list[dict[int, int]]:
    """Maximize zero-sum blocks over all orderings: O(n*2**n) time, O(2**n) memory."""
    users = sorted(positions)
    size = 1 << len(users)
    sums, best, parent = [0] * size, [0] * size, [0] * size
    for mask in range(1, size):
        bit = mask & -mask
        sums[mask] = sums[mask ^ bit] + positions[users[bit.bit_length() - 1]]
        remaining, maximum, chosen = mask, -1, 0
        while remaining:
            bit = remaining & -remaining
            candidate = best[mask ^ bit]
            if candidate > maximum:
                maximum, chosen = candidate, bit
            remaining ^= bit
        best[mask] = maximum + (sums[mask] == 0)
        parent[mask] = chosen
    order, mask = [], size - 1
    while mask:
        bit = parent[mask]
        order.append(users[bit.bit_length() - 1])
        mask ^= bit
    subsets, current, total = [], {}, 0
    for user in reversed(order):
        current[user] = positions[user]
        total += positions[user]
        if total == 0:
            subsets.append(current)
            current = {}
    return subsets


def suggest_transfers(positions: dict[int, int], threshold: int = 16) -> Plan:
    if not 0 <= threshold <= 16 or sum(positions.values()) != 0:
        raise ValueError("Positions must sum to zero; threshold must be between 0 and 16")
    active = {user: amount for user, amount in positions.items() if amount}
    if len(active) <= threshold:
        subsets = exact_partition(active)
        transfers = [transfer for subset in subsets for transfer in greedy_transfers(subset)]
        return Plan(transfers, "exact", "minimum_transactions", True)
    return Plan(greedy_transfers(active), "greedy", "minimum_transactions", False)


def validate_settlement(
    mode: str,
    sender: int,
    receiver: int,
    amount: int,
    positions: dict[int, int],
    direct: list[Transfer],
) -> None:
    if sender == receiver or sender not in positions or receiver not in positions or amount <= 0:
        raise ValueError("A positive settlement between distinct group members is required")
    if mode == "direct":
        maximum = next(
            (
                t.amount_minor
                for t in direct
                if (t.from_user_id, t.to_user_id) == (sender, receiver)
            ),
            0,
        )
    elif mode == "simplified":
        maximum = min(max(-positions[sender], 0), max(positions[receiver], 0))
    else:
        raise ValueError("Unknown settlement mode")
    if amount > maximum:
        raise ValueError("Payment exceeds the current debt for this settlement mode")
