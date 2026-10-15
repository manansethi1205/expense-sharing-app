from decimal import Decimal


def to_minor(amount: Decimal) -> int:
    scaled = amount * 100
    if not amount.is_finite() or scaled != scaled.to_integral_value():
        raise ValueError("Amount must be finite and use at most two decimal places")
    return int(scaled)


def format_money(amount_minor: int) -> str:
    return f"{Decimal(amount_minor) / 100:.2f}"
