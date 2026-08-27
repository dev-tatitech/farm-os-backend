def calculate_profitability(animal, expected_sale_price=None, price_per_kg=None, farm=None):
    from finance.services import compute_total_cost_to_date, compute_income_generated
    from .sale_readiness import resolve_sale_policy

    total_cost = compute_total_cost_to_date(animal)
    income = compute_income_generated(animal)
    policy = resolve_sale_policy(animal, farm=farm)
    expenses_pct = policy.expected_sale_expenses_pct if policy else 0

    break_even_price = max(total_cost - income, 0)

    result = {
        "total_cost_to_date": total_cost,
        "income_generated": income,
        "break_even_price": break_even_price,
        "break_even_weight_kg": (break_even_price / price_per_kg) if price_per_kg else None,
        "expected_sale_expenses": None,
        "estimated_sale_profit": None,
        "estimated_profit_margin_pct": None,
        "estimated_return_on_cost_pct": None,
    }

    if expected_sale_price is not None:
        expected_sale_expenses = expected_sale_price * (expenses_pct / 100)
        profit = expected_sale_price - total_cost - expected_sale_expenses + income

        result["expected_sale_expenses"] = expected_sale_expenses
        result["estimated_sale_profit"] = profit
        result["estimated_profit_margin_pct"] = (profit / expected_sale_price * 100) if expected_sale_price else None
        result["estimated_return_on_cost_pct"] = (profit / total_cost * 100) if total_cost else None

    return result
