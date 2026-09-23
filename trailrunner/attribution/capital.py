"""How a long-lived asset's construction is attributed to what it makes.

Static LCA never has to ask: the factory and its output are the same instant.
Once the inventory knows what year things happen in, the question is
unavoidable and has no value-free answer, so it is a setting — and the three
answers live here rather than in each model, so that every model gives the
same one.
"""

CAPITAL_RULES = ("per_output", "per_year", "first_life")


def amortize(
    capital: float,
    *,
    rule: str,
    demanded_output: float,
    annual_output: float,
    lifetime_output: float,
    lifetime_years: int,
    demand_year: int,
    build_year: int,
) -> float:
    """The share of ``capital`` attributed to ``demanded_output``.

    ``per_output`` spreads it over everything the asset will ever make, so a
    lean year carries only its own share. ``per_year`` gives each year of life
    an equal share, so a lean year carries as much capital as a busy one.
    ``first_life`` puts all of it in the year the asset was built, keeping
    construction where it physically happened at the cost of a spike.

    ``annual_output`` is the demanded year's output and ``lifetime_output`` is
    the whole life's. They are separate arguments rather than one derived from
    the other because their difference is exactly what makes the first two
    rules give different answers.
    """
    if rule not in CAPITAL_RULES:
        raise ValueError(
            f"{rule!r} is not a known capital rule; allowed: {', '.join(CAPITAL_RULES)}"
        )
    if annual_output <= 0 or lifetime_output <= 0 or lifetime_years <= 0:
        raise ValueError(
            "annual_output, lifetime_output and lifetime_years must all be positive "
            f"to attribute capital; got annual_output={annual_output}, "
            f"lifetime_output={lifetime_output}, lifetime_years={lifetime_years}"
        )

    if rule == "per_output":
        return capital * demanded_output / lifetime_output
    if rule == "per_year":
        return capital / lifetime_years * demanded_output / annual_output
    return capital * demanded_output / annual_output if demand_year == build_year else 0.0
