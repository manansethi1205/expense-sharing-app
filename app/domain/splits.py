def equal_shares(amount_minor: int, members: list[int]) -> dict[int, int]:
    if amount_minor <= 0 or not members or len(set(members)) != len(members):
        raise ValueError("A positive amount and unique participants are required")
    quotient, remainder = divmod(amount_minor, len(members))
    return {user: quotient + (index < remainder) for index, user in enumerate(sorted(members))}


def validate_custom_shares(
    amount_minor: int, members: list[int], shares: list[tuple[int, int]]
) -> dict[int, int]:
    result = dict(shares)
    if len(result) != len(shares) or set(result) != set(members):
        raise ValueError("Custom splits must include every current member exactly once")
    if any(amount < 0 for amount in result.values()) or sum(result.values()) != amount_minor:
        raise ValueError("Nonnegative shares must sum exactly to the expense amount")
    return result
