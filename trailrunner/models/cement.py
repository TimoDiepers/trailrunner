"""Cement: the worked example.

Kiln fuel is not a fixed coefficient. Raw meal arrives from the quarry with
water in it, and every kilogram of that water has to be boiled off before any
limestone calcines, so wet feed costs both drying steam and kiln fuel. Cold
feed costs a little more again. That dependency is the reason a model is
Python code rather than a row in a table.

Two classes live here and both declare the same product. ``CementPlant``
computes; ``MeteredCementPlant`` reads a meter. Their ``Coverage`` time ranges
do not overlap, so ``Glossary.resolve`` picks between them by the year the
demand carries, and the report names which one answered. Nothing in the
library had to learn about measurement for that to work.
"""

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

    Applied to the kiln fuel and the drying steam, and not to electricity.
    Grinding work is set by how fine the cement has to be, not by how wet the
    quarry was.
    """
    moisture_term = MOISTURE_SENSITIVITY * (moisture - REFERENCE_MOISTURE)
    temperature_term = TEMPERATURE_SENSITIVITY * (REFERENCE_TEMPERATURE - temperature)
    return 1.0 + moisture_term + temperature_term
