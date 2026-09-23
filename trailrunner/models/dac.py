"""Direct air capture: the worked example.

Sorbent regeneration heat is not a fixed coefficient. Colder, drier air means
less CO2 and less water reaching the sorbent per unit of air moved, so the heat
and fan work per kilogram captured go up. That dependency is the reason a model
is Python code rather than a row in a table.

Construction is the second reason. A plant capturing CO2 in 2030 was poured and
welded years earlier, and the fleet doing the capturing was not built all at
once. Given a ``Fleet`` table, the model amortizes each running plant's
construction over its capacity and lifetime and demands it **in the year that
plant was actually built** — so the construction inputs land in their own years
and, once a model answers them, meet whatever background those years carry.
"""

from trailrunner.attribution import amortize
from trailrunner.core.flow import Demand, Exchange, Flow
from trailrunner.core.model import Model
from trailrunner.core.result import Result
from trailrunner.params.coverage import Coverage
from trailrunner.params.fleet import Fleet

CO2_CAPTURED = "https://vocab.sentier.dev/products/co2-captured"
HEAT = "https://vocab.sentier.dev/products/heat"
ELECTRICITY = "https://vocab.sentier.dev/products/electricity"
DAC_PLANT = "https://vocab.sentier.dev/products/direct-air-capture-plant"
CO2_AIR = "https://vocab.sentier.dev/flows/co2-from-air"

REFERENCE_TEMPERATURE = 10.0  # degC, the temperature the parquet figures assume
REFERENCE_HUMIDITY = 0.70  # dimensionless, likewise
TEMPERATURE_SENSITIVITY = 0.01  # per degC below reference
HUMIDITY_SENSITIVITY = 0.30  # per unit of relative humidity below reference


def ambient_penalty(temperature: float, humidity: float) -> float:
    """Multiplier on heat and electricity demand for non-reference air.

    Colder or drier than the reference gives a value above 1.0; warmer or
    wetter gives one below. Deliberately a simple linear response: the point is
    that the dependency exists and lives in code, not that this particular
    curve is the right one.
    """
    temperature_term = TEMPERATURE_SENSITIVITY * (REFERENCE_TEMPERATURE - temperature)
    humidity_term = HUMIDITY_SENSITIVITY * (REFERENCE_HUMIDITY - humidity)
    return 1.0 + temperature_term + humidity_term


class DirectAirCapture(Model):
    """Captures CO2 from ambient air, given heat and electricity.

    Pass a ``Fleet`` to also account for the plants doing the capturing. Without
    one the model answers exactly as it did before: operation only, no capital.
    """

    produces = [CO2_CAPTURED]
    coverage = Coverage(time_range=(2020, 2050))
    fleet: Fleet | None = None

    def __init__(self, settings=None, params=None, fleet: Fleet | None = None) -> None:
        super().__init__(settings=settings, params=params)
        if fleet is not None:
            self.fleet = fleet

    def apply(self, demand: Demand) -> Result:
        row = self.params.at(location=demand.flow.location, time=demand.flow.time)
        penalty = ambient_penalty(row["temperature"], row["humidity"])

        heat = row["heat_demand"] * penalty * demand.amount
        electricity = row["electricity_demand"] * penalty * demand.amount
        upstream = Flow(iri=HEAT, location=demand.flow.location, time=demand.flow.time)

        construction, fleet_provenance = self._construction(demand)

        return Result(
            production=[
                Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)
            ],
            technosphere=[
                Demand(flow=upstream, amount=heat, unit=row.unit_of("heat_demand")),
                Demand(
                    flow=Flow(
                        iri=ELECTRICITY,
                        location=demand.flow.location,
                        time=demand.flow.time,
                    ),
                    amount=electricity,
                    unit=row.unit_of("electricity_demand"),
                ),
                *construction,
            ],
            biosphere=[
                Exchange(
                    flow=Flow(
                        iri=CO2_AIR,
                        location=demand.flow.location,
                        time=demand.flow.time,
                    ),
                    amount=-demand.amount,
                    unit=demand.unit,
                )
            ],
            provenance={**row.provenance, **fleet_provenance},
        )

    def _construction(self, demand: Demand) -> tuple[list[Demand], dict]:
        """One construction demand per operating plant, in that plant's build year.

        The demanded capture is what decides how much of the fleet is claimed:
        ``share_of_fleet = amount / total_capacity``. Each plant carries that
        share of its own capacity — ``capacity_i * share_of_fleet`` — as the
        ``demanded_output`` handed to :func:`amortize`, which spreads the
        plant's capital (its own capacity, standing in for what it took to
        build) over that plant's own annual and lifetime output according to
        ``self.settings.attribution.capital``. Under the default rule,
        ``per_output``, this reduces to::

            construction_i = amount * capacity_i / (total_capacity * lifetime_i)

        which, with one lifetime across the fleet, sums to ``amount /
        lifetime`` — one lifetime's worth of capture buys one fleet.
        """
        if self.fleet is None:
            return [], {}

        selection = self.fleet.operating(
            location=demand.flow.location, time=demand.flow.time
        )
        capacity_column = self.fleet.capacity_column
        lifetime_column = self.fleet.lifetime_column
        unit = selection.unit_of(capacity_column)
        rule = self.settings.attribution.capital

        construction = []
        for plant in selection.plants:
            capacity = float(plant[capacity_column])
            lifetime = float(plant[lifetime_column])
            build_year = int(plant["build_year"])
            amount = amortize(
                capacity,
                rule=rule,
                demanded_output=capacity * demand.amount / selection.total_capacity,
                annual_output=capacity,
                lifetime_output=capacity * lifetime,
                lifetime_years=lifetime,
                demand_year=demand.flow.time,
                build_year=build_year,
            )
            construction.append(
                Demand(
                    # The plant's own location and build year, not the demand's:
                    # that displacement in time is the whole point, and a fleet
                    # resolved through the hierarchy may sit somewhere else too.
                    flow=Flow(
                        iri=DAC_PLANT,
                        location=plant.get("location", demand.flow.location),
                        time=build_year,
                    ),
                    amount=amount,
                    unit=unit,
                )
            )

        provenance = {
            **selection.provenance,
            "share_of_fleet": demand.amount / selection.total_capacity,
            "capital_rule": rule,
        }
        return construction, provenance
