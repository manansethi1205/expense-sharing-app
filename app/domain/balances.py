from collections import defaultdict
from dataclasses import dataclass


@dataclass(frozen=True)
class Transfer:
    from_user_id: int
    to_user_id: int
    amount_minor: int


def direct_balances(obligations: list[Transfer], settlements: list[Transfer]) -> list[Transfer]:
    pairs: dict[tuple[int, int], int] = defaultdict(int)
    for events, sign in ((obligations, 1), (settlements, -1)):
        for event in events:
            if event.from_user_id == event.to_user_id:
                continue
            low, high = sorted((event.from_user_id, event.to_user_id))
            pairs[low, high] += sign * event.amount_minor * (1 if event.from_user_id == low else -1)
    return [
        Transfer(low, high, value) if value > 0 else Transfer(high, low, -value)
        for (low, high), value in sorted(pairs.items())
        if value
    ]


def net_positions(
    members: list[int], obligations: list[Transfer], settlements: list[Transfer]
) -> dict[int, int]:
    positions = dict.fromkeys(members, 0)
    for events, sign in ((obligations, 1), (settlements, -1)):
        for event in events:
            positions[event.from_user_id] -= sign * event.amount_minor
            positions[event.to_user_id] += sign * event.amount_minor
    return positions
