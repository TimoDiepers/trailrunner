"""Cement: the worked example.

Kiln fuel is not a fixed coefficient. Raw meal arrives from the quarry with
water in it, and every kilogram of that water has to be boiled off before any
limestone calcines, so wet feed costs kiln fuel. Cold feed
costs a little more again. That dependency is the reason a model is
Python code rather than a row in a table.

Two classes live here and both declare the same product. ``CementPlant``
computes; ``MeteredCementPlant`` reads a meter. Their ``Coverage`` time ranges
do not overlap, so ``Glossary.resolve`` picks between them by the year the
demand carries, and the report names which one answered. Nothing in the
library had to learn about measurement for that to work.
"""

from dataclasses import replace

from trailrunner.attribution import amortize, output_over_a_year
from trailrunner.core.flow import Demand, Exchange, Flow, Property
from trailrunner.core.model import Model
from trailrunner.core.result import Result
from trailrunner.core.settings import ALLOCATION_RULES
from trailrunner.params.coverage import Coverage
from trailrunner.params.fleet import Fleet
from trailrunner.core.units import KG, PA
from trailrunner.core.time import in_year, when, year_of, year_range

# Real BONSAI vocabulary concepts, verified live against
# https://vocab.sentier.dev on 2026-09-24 and cached by
# dev/warm_pyst_cache.py. An IRI that is not a concept relaxes nothing,
# because skos:broader never has anything to walk -- see the comment in
# trailrunner/models/dac.py for what that failure looks like.
CEMENT = "https://vocab.sentier.dev/products/bonsai/2025.1/BONSAI2025.1/fi_37440"  # "Portland cement, aluminous cement, slag cement and similar hydraulic cements, except in the form of clinkers"
LIMESTONE = "https://vocab.sentier.dev/products/bonsai/2025.1/BONSAI2025.1/fi_15200"  # "Gypsum; anhydrite; limestone flux; limestone and other calcareous stone, of a kind used for the manufacture of lime or cement"
NATURAL_GAS = "https://vocab.sentier.dev/products/bonsai/2025.1/BONSAI2025.1/fi_12020"  # "Natural gas, liquefied or in the gaseous state"
ELECTRICITY = "https://vocab.sentier.dev/products/bonsai/2025.1/BONSAI2025.1/fi_17100"  # "electricity"
# The lime the works takes as a minor constituent. Nothing in this repository
# produces it, which is the point: the showcase relaxes it up the taxonomy
# until something answers. The first skos:broader step reaches fi_3742, spelled
# identically and produced by nobody; the second reaches fi_374, "Plaster, lime
# and cement" -- an average over binders that includes cement itself. A lime
# demand answered by a category containing the product the works is making is
# the right answer available and a poor answer in substance, which is exactly
# the kind of concession that has to be recorded rather than absorbed.
LIME = "https://vocab.sentier.dev/products/bonsai/2025.1/BONSAI2025.1/fi_37420"  # "Quicklime, slaked lime and hydraulic lime"
# Invented, like dac.py's DAC_PLANT and for the same reason: BONSAI's product
# classification does not carry capital-good infrastructure at this
# granularity. The concepts endpoint answers 404, so this can never relax.
CEMENT_KILN = "https://vocab.sentier.dev/products/cement-kiln"
# Calcination CO2 is geogenic rather than fossil, but every inventory
# convention in use counts it as fossil, and co2-fossil is the IRI
# assessment/dynamic.py and assessment/static.py already characterize.
# Writing it anywhere else would drop it silently out of every score.
CO2_FOSSIL = "https://vocab.sentier.dev/flows/co2-fossil"
# The burner pressure the kiln asks its gas at, named by the sentier
# vocabulary's (QUDT-derived) quantity kind and given in Pa. A supplier answers
# it exactly only if it declares the same name and unit -- see
# natural_gas.PRESSURE.
PRESSURE = "https://vocab.sentier.dev/units/quantity-kind/Pressure"

CLINKER_CALCINATION_CO2 = 0.53  # kg CO2 per kg clinker, from CaCO3 -> CaO + CO2
LIMESTONE_PER_CLINKER = 1.5  # kg raw limestone per kg clinker
GAS_CO2_PER_MJ = 0.056  # kg CO2 per MJ of natural gas burned

REFERENCE_MOISTURE = 0.04  # mass fraction, the raw meal the parquet figures assume
REFERENCE_TEMPERATURE = 10.0  # degC, likewise
MOISTURE_SENSITIVITY = 2.0  # per unit of mass fraction above reference
TEMPERATURE_SENSITIVITY = 0.004  # per degC below reference


def moisture_penalty(moisture: float, temperature: float) -> float:
    """Multiplier on thermal demand for feed that is not at reference.

    Wetter or colder than the reference gives a value above 1.0; drier or
    warmer gives one below. Deliberately a simple linear response: the point is
    that the dependency exists and lives in code, not that this particular
    curve is the right one.

    Applied to the kiln fuel, and to nothing else. Grinding work is set by how
    fine the cement has to be, not by how wet the quarry was, and the lime the
    works blends in is a recipe quantity rather than a thermal one.
    """
    moisture_term = MOISTURE_SENSITIVITY * (moisture - REFERENCE_MOISTURE)
    temperature_term = TEMPERATURE_SENSITIVITY * (REFERENCE_TEMPERATURE - temperature)
    return 1.0 + moisture_term + temperature_term


class CementPlant(Model):
    """Grinds cement, calcines its own clinker, fires its own kiln.

    Monofunctional: one product, so there is nothing to partition and no
    allocation rule changes the answer. Co-production is demonstrated
    separately, in ``examples/coproduction.ipynb``.

    Pass a ``Fleet`` to also account for the kilns doing the calcining.
    Without one the model answers operation only, no capital.

    Pass ``burner_pressure`` (Pa) to ask for the kiln's gas at that
    pressure. Without one the gas demand names no pressure, and any supplier
    answers it.
    """

    produces = [CEMENT]
    coverage = Coverage(time_range=year_range(2026, 2050), units=frozenset({KG}))
    fleet: Fleet | None = None
    burner_pressure: float | None = None

    supports = ALLOCATION_RULES
    """Every rule, because this model is monofunctional.

    The same reasoning ``DirectAirCapture.supports`` carries: with a single
    product ``allocate`` short-circuits and ``substitute`` mints no credits,
    so the answer is identical under all five rules. Declaring only ``none``
    would make the Runner refuse this model at the first node of any
    non-``none`` run, for a problem it does not have.
    """

    def __init__(
        self,
        settings=None,
        params=None,
        fleet: Fleet | None = None,
        burner_pressure: float | None = None,
    ) -> None:
        super().__init__(settings=settings, params=params)
        if fleet is not None:
            self.fleet = fleet
        if burner_pressure is not None:
            self.burner_pressure = burner_pressure

    def apply(self, demand: Demand) -> Result:
        row = self.params.at(location=demand.flow.location, **when(demand.flow))
        penalty = moisture_penalty(row["moisture"], row["temperature"])

        clinker = row["clinker_factor"] * demand.amount
        limestone = LIMESTONE_PER_CLINKER * clinker
        fuel = row["fuel_demand"] * clinker * penalty
        lime = row["lime_demand"] * demand.amount
        electricity = row["electricity_demand"] * demand.amount

        construction, fleet_provenance = self._construction(demand)

        def here(iri: str) -> Flow:
            return Flow(iri=iri, location=demand.flow.location, **when(demand.flow))

        return Result(
            production=[
                Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)
            ],
            technosphere=[
                Demand(flow=here(LIMESTONE), amount=limestone, unit=KG),
                Demand(
                    flow=self._gas(here(NATURAL_GAS)),
                    amount=fuel,
                    unit=row.unit_of("fuel_demand"),
                ),
                Demand(flow=here(LIME), amount=lime, unit=row.unit_of("lime_demand")),
                Demand(
                    flow=here(ELECTRICITY),
                    amount=electricity,
                    unit=row.unit_of("electricity_demand"),
                ),
                *construction,
            ],
            biosphere=[
                # Two exchanges, not one sum. A reader can see which kilogram
                # came from the rock and which from the flame -- and the
                # measured beat lands on the fact that a stack meter cannot.
                Exchange(
                    flow=here(CO2_FOSSIL),
                    amount=CLINKER_CALCINATION_CO2 * clinker,
                    unit=KG,
                ),
                Exchange(
                    flow=here(CO2_FOSSIL), amount=GAS_CO2_PER_MJ * fuel, unit=KG
                ),
            ],
            provenance={**row.provenance, "source": "modelled", **fleet_provenance},
        )

    def _gas(self, flow: Flow) -> Flow:
        """The kiln's gas, at the burner's pressure if the plant names one."""
        if self.burner_pressure is None:
            return flow
        return replace(flow, context=(Property(PRESSURE, self.burner_pressure, PA),))

    def _construction(self, demand: Demand) -> tuple[list[Demand], dict]:
        """One construction demand per operating kiln, in that kiln's build year.

        The demanded cement is what decides how much of the fleet is claimed:
        ``share_of_fleet = amount / total_output``, where ``total_output`` is the
        fleet's capacity over one year, converted into the demand's unit. Each kiln carries that
        share of its own capacity -- ``capacity_i * share_of_fleet`` -- as the
        ``demanded_output`` handed to :func:`amortize`, which spreads the
        kiln's capital (its own capacity, standing in for what it took to
        build) over that kiln's own annual and lifetime output according to
        ``self.settings.attribution.capital``. Under the default rule,
        ``per_output``, this reduces to::

            construction_i = capacity_i * amount / (total_output * lifetime_i)

        which, with one lifetime across the fleet, sums to the capacity that
        makes ``amount / lifetime`` a year -- one lifetime's worth of cement
        buys one fleet.

        Under ``first_life`` the answer is zero for every kiln whose build
        year is not the demanded year, so a study year with no construction in
        it demands no construction at all. That is the rule, not a missing
        fleet. ``demand.flow.time`` may be ``None`` -- a demand that is not
        time-specific -- and :func:`amortize` refuses that under ``first_life``
        rather than letting ``None != build_year`` quietly zero the capital.
        """
        if self.fleet is None:
            return [], {}

        selection = self.fleet.operating(
            location=demand.flow.location, time=year_of(demand.flow)
        )
        capacity_column = self.fleet.capacity_column
        lifetime_column = self.fleet.lifetime_column
        unit = selection.unit_of(capacity_column)
        rule = self.settings.attribution.capital

        # Capacity is a rate in its own unit (t/yr); the demand is an amount
        # (kg). Each kiln's year of output, in the demand's unit, is what the
        # demand is a share of. The fleet's own total_capacity stays in the
        # capacity unit; the conversion happens here, in the model.
        annual = [
            output_over_a_year(float(kiln[capacity_column]), unit, demand.unit)
            for kiln in selection.plants
        ]
        total_output = sum(annual)

        construction = []
        for kiln, annual_output in zip(selection.plants, annual):
            capacity = float(kiln[capacity_column])
            lifetime = float(kiln[lifetime_column])
            build_year = int(kiln["build_year"])
            amount = amortize(
                capacity,  # the capital, in the capacity unit the demand is made in
                rule=rule,
                demanded_output=annual_output * demand.amount / total_output,
                annual_output=annual_output,
                lifetime_output=annual_output * lifetime,
                lifetime_years=lifetime,
                demand_year=year_of(demand.flow),
                build_year=build_year,
            )
            construction.append(
                Demand(
                    # The kiln's own location and build year, not the demand's:
                    # that displacement in time is the whole point, and a fleet
                    # resolved through the hierarchy may sit somewhere else too.
                    flow=Flow(
                        iri=CEMENT_KILN,
                        location=kiln.get("location", demand.flow.location),
                        **in_year(build_year),
                    ),
                    amount=amount,
                    unit=unit,
                )
            )

        provenance = {
            **selection.provenance,
            "share_of_fleet": demand.amount / total_output,
            "capital_rule": rule,
        }
        return construction, provenance


class MeteredCementPlant(Model):
    """The same plant, in the years it was measured rather than modelled.

    This computes nothing. It reads one row of metered data and returns it,
    which is enough to make it a model: what makes something a model here is
    that it answers a demand, not that it calculates one.

    What a meter at the plant boundary can and cannot tell you is the whole
    point of the class. It gives one stack figure, calcination and combustion
    together and indistinguishable, so this returns a single biosphere
    exchange where :class:`CementPlant` returns two. The gas, lime and
    electricity it also weighs are *inputs*: their emissions happen off site,
    so they go out as technosphere demands and get answered by whoever
    supplies them, exactly as the computed model's do.

    The row is normalised per 1000 kg of cement, so it scales with the demand.
    A meter reading is not a fixed quantity of anything.
    """

    produces = [CEMENT]
    coverage = Coverage(time_range=year_range(2018, 2025), units=frozenset({KG}))

    supports = ALLOCATION_RULES
    """Monofunctional, like :class:`CementPlant`, and for the same reason."""

    REFERENCE_OUTPUT = 1000.0  # kg of cement the metered row is normalised to

    def apply(self, demand: Demand) -> Result:
        row = self.params.at(location=demand.flow.location, **when(demand.flow))
        scale = demand.amount / self.REFERENCE_OUTPUT

        def here(iri: str) -> Flow:
            return Flow(iri=iri, location=demand.flow.location, **when(demand.flow))

        return Result(
            production=[
                Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)
            ],
            technosphere=[
                Demand(
                    flow=here(NATURAL_GAS),
                    amount=row["metered_fuel"] * scale,
                    unit=row.unit_of("metered_fuel"),
                ),
                Demand(
                    flow=here(LIME),
                    amount=row["metered_lime"] * scale,
                    unit=row.unit_of("metered_lime"),
                ),
                Demand(
                    flow=here(ELECTRICITY),
                    amount=row["metered_electricity"] * scale,
                    unit=row.unit_of("metered_electricity"),
                ),
            ],
            biosphere=[
                Exchange(
                    flow=here(CO2_FOSSIL),
                    amount=row["metered_co2"] * scale,
                    unit=row.unit_of("metered_co2"),
                )
            ],
            provenance={**row.provenance, "source": "measured"},
        )
