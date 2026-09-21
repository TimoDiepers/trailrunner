"""Direct air capture: the worked example.

Sorbent regeneration heat is not a fixed coefficient. Colder, drier air means
less CO2 and less water reaching the sorbent per unit of air moved, so the heat
and fan work per kilogram captured go up. That dependency is the reason a model
is Python code rather than a row in a table.
"""

from trailrunner.core.flow import Demand, Exchange, Flow
from trailrunner.core.model import Model
from trailrunner.core.result import Result
from trailrunner.params.coverage import Coverage

CO2_CAPTURED = "https://vocab.sentier.dev/products/co2-captured"
HEAT = "https://vocab.sentier.dev/products/heat"
ELECTRICITY = "https://vocab.sentier.dev/products/electricity"
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
    """Captures CO2 from ambient air, given heat and electricity."""

    produces = [CO2_CAPTURED]
    coverage = Coverage(time_range=(2020, 2050))

    def apply(self, demand: Demand) -> Result:
        row = self.params.at(location=demand.flow.location, time=demand.flow.time)
        penalty = ambient_penalty(row["temperature"], row["humidity"])

        heat = row["heat_demand"] * penalty * demand.amount
        electricity = row["electricity_demand"] * penalty * demand.amount
        upstream = Flow(iri=HEAT, location=demand.flow.location, time=demand.flow.time)

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
            provenance=dict(row.provenance),
        )
