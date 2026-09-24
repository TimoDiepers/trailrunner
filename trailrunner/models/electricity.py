"""Electricity: a grid mix that differs by place and year, and one plant behind it.

The grid is the second worked example, and it exists for a different reason than
the DAC one. Nothing here is nonlinear; what varies is *composition*. A kilowatt
hour in Switzerland is mostly hydro, the same kilowatt hour in Europe is half
fossil, and both mixes move over the decade. A single emission factor per kWh
would flatten all of that into one number that is wrong in both places, so the
mix is resolved per (location, time) and split into one demand per source — and
the sources are ordinary products, traversed by their own models.

Only the gas share has a model here. Wind and hydro are left unmodelled on
purpose: they surface as cutoff leaves with a reason, which is what the
unresolved list is for.
"""

from trailrunner.core.errors import ValidationError
from trailrunner.core.flow import Demand, Exchange, Flow
from trailrunner.core.model import Model
from trailrunner.core.result import Result
from trailrunner.core.settings import ALLOCATION_RULES
from trailrunner.params.coverage import Coverage
from trailrunner.core.units import KWH, MJ
from trailrunner.core.time import when, year_range

# Real BONSAI vocabulary concepts (verified live against
# https://vocab.sentier.dev; see dev/warm_pyst_cache.py and
# .superpowers/sdd/2026-09-22-phase-4-surfaces-and-showcase/step-0-report.md).
# The plain "electricity"/"natural-gas" IRIs these two constants used to hold
# were invented, not vocabulary concepts -- the concepts endpoint answered
# 404 for both.
ELECTRICITY = "https://vocab.sentier.dev/products/bonsai/2025.1/BONSAI2025.1/fi_17100"  # "electricity"
NATURAL_GAS = "https://vocab.sentier.dev/products/bonsai/2025.1/BONSAI2025.1/fi_12020"  # "Natural gas, liquefied or in the gaseous state"
# ELECTRICITY_GAS/WIND/HYDRO are this model's own per-source split of the grid
# mix, not products the vocabulary defines at this granularity -- out of
# scope for this pass; left as the invented IRIs they always were.
ELECTRICITY_GAS = "https://vocab.sentier.dev/products/electricity-natural-gas"
ELECTRICITY_WIND = "https://vocab.sentier.dev/products/electricity-wind"
ELECTRICITY_HYDRO = "https://vocab.sentier.dev/products/electricity-hydro"
CO2_FOSSIL = "https://vocab.sentier.dev/flows/co2-fossil"

SOURCES = {
    "share_gas": ELECTRICITY_GAS,
    "share_wind": ELECTRICITY_WIND,
    "share_hydro": ELECTRICITY_HYDRO,
}
"""Parameter column -> product IRI it is a share of.

A mapping rather than a hard-coded sequence of lines so that adding a source
means adding a column and one entry, not editing ``apply``.
"""

SHARE_TOLERANCE = 1e-6
"""How far the shares may miss 1.0 and still be accepted.

Small enough to catch a mix that is genuinely incomplete, large enough to let
interpolation between two years' rows round the way floats do.
"""

KWH_TO_MJ = 3.6

ELECTRICITY_UNIT = KWH
"""The unit this module reasons in.

``GasPower`` converts to MJ of fuel with a fixed factor, so a demand in any
other unit would be silently misread by that factor. It is rejected instead.
"""


class GridElectricity(Model):
    """Low-voltage grid electricity, split into the sources that generated it.

    Two things come out of the parameter row. The *mix* decides which products
    are demanded, and the *grid loss* decides how much: what the consumer takes
    off the grid is less than what was generated, so the generation demanded
    upstream is ``amount / (1 - grid_loss)``.
    """

    produces = [ELECTRICITY]
    coverage = Coverage(time_range=year_range(2000, 2050))

    supports = ALLOCATION_RULES
    """Every rule, because this model is monofunctional.

    Monofunctionality is a fact about the model, not a value judgement: with a
    single product there is nothing to partition, so ``allocate`` takes its
    no-op short-circuit and ``substitute`` mints no credits, and the answer is
    the same under all five rules. Declaring only ``none`` would have made the
    Runner's gate refuse this model at the first node of any non-``none`` run,
    for a co-production problem it does not have.
    """

    def apply(self, demand: Demand) -> Result:
        row = self.params.at(location=demand.flow.location, **when(demand.flow))
        shares = {iri: float(row[column]) for column, iri in SOURCES.items()}

        # A mix that does not add up is a hole in the data, and a hole that is
        # cheap to paper over: renormalizing would hand back a plausible answer
        # built on a number nobody wrote down. The complaint names the row so
        # the fix goes to the parquet file, not to this model.
        total = sum(shares.values())
        if abs(total - 1.0) > SHARE_TOLERANCE:
            raise ValidationError(
                f"grid mix for location={demand.flow.location!r} "
                f"time={demand.flow.time!r} sums to {total}, not 1.0; "
                f"shares {shares}"
            )

        grid_loss = float(row["grid_loss"])
        generated = demand.amount / (1 - grid_loss)

        return Result(
            production=[
                Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)
            ],
            # A zero share is a source this grid does not use. Pushing it as a
            # zero-amount demand would put an empty node — or a cutoff leaf
            # asking for nothing — into every report.
            technosphere=[
                Demand(
                    flow=Flow(
                        iri=iri, location=demand.flow.location, **when(demand.flow)
                    ),
                    amount=share * generated,
                    unit=demand.unit,
                )
                for iri, share in shares.items()
                if share > 0
            ],
            provenance={**row.provenance, "shares": shares, "grid_loss": grid_loss},
        )


class GasPower(Model):
    """A gas plant: fuel in at the row's efficiency, fossil CO2 out.

    The fuel itself is left unmodelled — it leaves as a technosphere demand and
    is reported as a cutoff, so the combustion CO2 here is the plant's direct
    emission only, not a cradle-to-gate figure.
    """

    produces = [ELECTRICITY_GAS]
    coverage = Coverage(time_range=year_range(2000, 2050), units=frozenset({ELECTRICITY_UNIT}))

    supports = ALLOCATION_RULES
    """Every rule, because this model is monofunctional.

    Monofunctionality is a fact about the model, not a value judgement: with a
    single product there is nothing to partition, so ``allocate`` takes its
    no-op short-circuit and ``substitute`` mints no credits, and the answer is
    the same under all five rules. Declaring only ``none`` would have made the
    Runner's gate refuse this model at the first node of any non-``none`` run,
    for a co-production problem it does not have.
    """

    def apply(self, demand: Demand) -> Result:
        row = self.params.at(location=demand.flow.location, **when(demand.flow))
        fuel = demand.amount * KWH_TO_MJ / float(row["efficiency"])
        here = dict(location=demand.flow.location, **when(demand.flow))

        return Result(
            production=[
                Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)
            ],
            technosphere=[
                Demand(flow=Flow(iri=NATURAL_GAS, **here), amount=fuel, unit=MJ)
            ],
            biosphere=[
                Exchange(
                    flow=Flow(iri=CO2_FOSSIL, **here),
                    amount=fuel * float(row["co2_factor"]),
                    unit=row.unit_of("co2_factor"),
                )
            ],
            provenance=dict(row.provenance),
        )
