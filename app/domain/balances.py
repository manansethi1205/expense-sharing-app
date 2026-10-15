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


def remove_circulation(transfers: list[Transfer]) -> list[Transfer]:
    """Cancel cycles, preserving net positions and existing creditor relationships.

    Each pass removes an edge; iterative DFS avoids a recursion-depth limit.
    An acyclic result cannot leave a nonempty zero-net payment remainder.
    """
    edges = {
        (t.from_user_id, t.to_user_id): t.amount_minor for t in transfers if t.amount_minor > 0
    }
    while True:
        adjacency: dict[int, list[int]] = defaultdict(list)
        for sender, receiver in sorted(edges):
            adjacency[sender].append(receiver)
        color, parents, cycle = {}, {}, []
        for root in sorted(adjacency):
            if color.get(root):
                continue
            color[root] = 1
            stack = [(root, iter(adjacency[root]))]
            while stack and not cycle:
                sender, neighbors = stack[-1]
                receiver = next(neighbors, None)
                if receiver is None:
                    color[sender] = 2
                    stack.pop()
                elif color.get(receiver) == 1:
                    cycle = [(sender, receiver)]
                    cursor = sender
                    while cursor != receiver:
                        previous = parents[cursor]
                        cycle.append((previous, cursor))
                        cursor = previous
                elif not color.get(receiver):
                    parents[receiver] = sender
                    color[receiver] = 1
                    stack.append((receiver, iter(adjacency.get(receiver, []))))
            if cycle:
                break
        if not cycle:
            return [
                Transfer(sender, receiver, amount)
                for (sender, receiver), amount in sorted(edges.items())
            ]
        reduction = min(edges[edge] for edge in cycle)
        for edge in cycle:
            edges[edge] -= reduction
            if edges[edge] == 0:
                del edges[edge]
