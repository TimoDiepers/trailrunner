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
    lifetime_years: int | float,
    demand_year: int | None,
    build_year: int,
) -> float:
    """The share of ``capital`` attributed to ``demanded_output``.

    ``per_output`` spreads it over everything the asset will ever make, so a
    lean year carries only its own share. ``per_year`` gives each year of life
    an equal share, so a lean year carries as much capital as a busy one.
    ``first_life`` puts all of it in the year the asset was built, keeping
    construction where it physically happened at the cost of a spike.

    That spike is visible only if the study year *is* a build year. Asked for
    any other year, ``first_life`` attributes **zero** capital — not a small
    share, none at all — because by then the construction has already been
    charged to the year it happened in. A 2030 study of a fleet built in 2026
    and 2029 therefore shows no construction whatsoever, which is the rule
    working, not a fleet that failed to load. Only a study spanning the build
    years sees the spike the name promises.

    ``demand_year`` may be ``None`` for the two rules that never read it. Under
    ``first_life`` it is the whole question, so a ``None`` there raises rather
    than quietly falling on the wrong side of ``demand_year == build_year`` and
    attributing nothing.

    ``annual_output`` is the demanded year's output and ``lifetime_output`` is
    the whole life's. They are separate arguments rather than one derived from
    the other because their difference is exactly what makes the first two
    rules give different answers.

    ``lifetime_years`` may be fractional — nothing about the arithmetic
    requires a whole number, and truncating it would make ``per_year``
    disagree with ``per_output`` on flat output purely from rounding the
    lifetime, not from any modelling difference between the two rules.
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
    if demand_year is None:
        # Not a defaultable question. `None == build_year` is False, so the
        # silent answer would be zero capital for a demand that never said
        # which year it was asking about -- the whole of an asset's
        # construction dropped on the floor, looking exactly like the honest
        # zero of a year that is not a build year.
        raise ValueError(
            "the 'first_life' capital rule attributes capital in the build year "
            "and nowhere else, so it cannot answer a demand with no year; give "
            "the demand a year, or choose 'per_output' or 'per_year'"
        )
    return capital * demanded_output / annual_output if demand_year == build_year else 0.0
