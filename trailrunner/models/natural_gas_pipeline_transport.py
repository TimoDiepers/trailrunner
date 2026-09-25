"""Long-distance offshore pipeline transport of natural gas.

The functional unit is 1 t of gas transported, over the distance the demand
states in its context (``distance``, any length unit): 1 t over 1 km is the
ecoinvent dataset's 1 tkm, number for number. The route length is the
demander's to state -- ``NaturalGasSupply`` knows it per consumer -- and the
per-tkm parameters below are applied to tonnes × km. What *does* vary by
origin country is which of two regional tiers it belongs to -- countries in the
former Soviet Union, the Middle East, Africa, Asia or Latin America consume
noticeably more compressor energy and leak noticeably more gas per km than
Europe or North America (ESU-services, Bussa et al. 2025, Tab. 4.4/4.6).
That tier split, not a per-country distance figure, is what a route twice
as remote does not simply scale into -- a route in a high-leakage region
loses gas (and the substances carried with it) at roughly ten times the
rate of a low-leakage one, so the amounts have to be derived from the
tier's rate and the generic gas composition rather than stored as one
number per country. That derivation is the reason this is a model and not
a lookup table.

See `dev/reverse-engineering of BAFU pipeline transport datasets/build_pipeline_trailpack.py`
for the full source trail (including the one formula -- gas-turbine
combustion energy -- that couldn't be independently re-derived from
primitives and is taken from the source report's worked example instead)
and `.../validate_pipeline_model.py` for the cross-check against the
parsed ecoinvent corpus.
"""

from dataclasses import replace

from trailrunner.core.errors import ValidationError
from trailrunner.core.flow import Demand, Exchange, Flow
from trailrunner.core.model import Model
from trailrunner.core.result import Result
from trailrunner.core.settings import ALLOCATION_RULES
from trailrunner.params.coverage import Coverage
from trailrunner.core.units import KG, KILOMETRE, M3, MJ, NUM, TONNE, default_catalog, symbol
from trailrunner.core.time import when

TRANSPORT = "https://vocab.sentier.dev/products/natural-gas-transport-offshore-pipeline-long-distance"
PIPELINE_INFRASTRUCTURE = "https://vocab.sentier.dev/products/pipeline-natural-gas-long-distance-high-capacity-offshore"
NATURAL_GAS_AT_PRODUCTION = "https://vocab.sentier.dev/products/natural-gas-at-production"
NATURAL_GAS_BURNED_IN_GAS_TURBINE = "https://vocab.sentier.dev/products/natural-gas-burned-in-gas-turbine"
FREIGHT_LORRY = "https://vocab.sentier.dev/products/transport-freight-lorry-16t-32t"
MINERAL_OIL_DISPOSAL = "https://vocab.sentier.dev/products/disposal-used-mineral-oil-10-percent-water-hazardous-waste-incineration"

# "ch4-fossil" for the same reason CARBON_DIOXIDE_FOSSIL below is "co2-fossil",
# and it matters more here: leaked methane is the whole climate story of gas
# transport, and under the old "flows/methane-fossil" spelling it missed both
# the GWP100 table and dynamic.py's characterization, so the showcase's gas
# supply chain would have reported its leakage as uncharacterized.
METHANE_FOSSIL = "https://vocab.sentier.dev/flows/ch4-fossil"
ETHANE = "https://vocab.sentier.dev/flows/ethane"
PROPANE = "https://vocab.sentier.dev/flows/propane"
BUTANE = "https://vocab.sentier.dev/flows/butane"
# Same spelling as electricity.py's CO2_FOSSIL and assessment/dynamic.py's
# characterization table -- this used to be "flows/carbon-dioxide-fossil", a
# different IRI for the same substance. The showcase runs this model
# alongside the background pack in one inventory, and a split spelling meant
# one of the two CO2 amounts silently went uncharacterized in the static
# assessment and was silently dropped from the dynamic curve. Settled on
# "co2-fossil": it is the side assessment/dynamic.py actually characterizes.
CARBON_DIOXIDE_FOSSIL = "https://vocab.sentier.dev/flows/co2-fossil"
MERCURY = "https://vocab.sentier.dev/flows/mercury"
NMVOC = "https://vocab.sentier.dev/flows/nmvoc-unspecified-origin"
HALON_1211 = "https://vocab.sentier.dev/flows/methane-bromochlorodifluoro-halon-1211"
HFC_23 = "https://vocab.sentier.dev/flows/methane-trifluoro-hfc-23"

# (biosphere flow IRI, trailpack composition column) -- Tab. 3.1's generic
# composition, applied identically regardless of location, per the source
# report's own simplification.
_COMPOSITION_FLOWS = (
    (METHANE_FOSSIL, "ch4_frac"),
    (ETHANE, "c2h6_frac"),
    (PROPANE, "c3h8_frac"),
    (BUTANE, "c4h10_frac"),
    (CARBON_DIOXIDE_FOSSIL, "co2_frac"),
    (MERCURY, "hg_frac"),
    (NMVOC, "nmvoc_frac"),
)

DISTANCE = "distance"
"""The context condition carrying how far the gas travels."""

HIGH_TIER_LOCATIONS = frozenset({"AZ", "DZ", "ID", "IR", "LY", "MY", "QA", "RU"})
LOW_TIER_LOCATIONS = frozenset({"GB", "IT", "NL", "NO", "UA", "US"})
DOCUMENTED_LOCATIONS = HIGH_TIER_LOCATIONS | LOW_TIER_LOCATIONS


def leaked_volume_nm3_per_tkm(leakage_rate_per_1000km: float, gas_density_kg_per_nm3: float) -> float:
    """Nm3 of gas that escapes per tkm of pipeline transport.

    1 tkm moves 1000 kg one km, so the leaked mass per tkm equals
    ``leakage_rate_per_1000km`` numerically (rate is per 1000 km, distance
    here is 1 km, mass is 1000 kg: the two factors of 1000 cancel); dividing
    by density converts that mass to a volume. A pure function so the
    arithmetic can be checked in isolation from the Model/Result plumbing,
    mirroring ``dac.ambient_penalty``.
    """
    return leakage_rate_per_1000km / gas_density_kg_per_nm3


class NaturalGasOffshorePipelineTransport(Model):
    """Transports tonnes of natural gas over a stated distance by offshore pipeline."""

    produces = [TRANSPORT]
    coverage = Coverage(locations=DOCUMENTED_LOCATIONS, units=frozenset({TONNE}))

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
        distance = demand.flow.get_context(DISTANCE)
        if distance is None:
            raise ValidationError(
                f"{type(self).__name__} moves tonnes of gas over a distance, and the "
                f"demand for {demand.flow.iri} states none; add "
                f"Property({DISTANCE!r}, <km>, KILOMETRE) to the flow's context"
            )
        km = default_catalog().try_convert(distance.value, distance.unit, KILOMETRE)
        if km is None:
            raise ValidationError(
                f"{type(self).__name__} was given a distance in "
                f"{symbol(distance.unit)}, which is not a length"
            )
        row = self.params.at(location=demand.flow.location, **when(demand.flow))
        tkm = demand.amount * km
        location = demand.flow.location

        def flow(iri: str) -> Flow:
            return Flow(iri=iri, location=location, **when(demand.flow))

        leaked_nm3 = leaked_volume_nm3_per_tkm(row["leakage_rate_per_1000km"], row["gas_density_kg_per_nm3"]) * tkm

        technosphere = [
            Demand(flow=flow(PIPELINE_INFRASTRUCTURE), amount=row["infra_factor"] * tkm, unit=NUM),
            Demand(flow=flow(NATURAL_GAS_AT_PRODUCTION), amount=leaked_nm3, unit=M3),
            Demand(
                flow=flow(NATURAL_GAS_BURNED_IN_GAS_TURBINE),
                amount=row["gas_turbine_mj_per_tkm"] * tkm,
                unit=MJ,
            ),
            # lorry_factor is lorry tkm per pipeline tkm, so the same distance
            # carries lorry_factor × tonnes.
            Demand(
                flow=replace(flow(FREIGHT_LORRY), context=(distance,)),
                amount=row["lorry_factor"] * demand.amount,
                unit=TONNE,
            ),
            Demand(
                flow=flow(MINERAL_OIL_DISPOSAL),
                amount=row["mineral_oil_disposal_factor"] * tkm,
                unit=KG,
            ),
        ]

        biosphere = [
            Exchange(flow=flow(iri), amount=leaked_nm3 * row[column], unit=KG)
            for iri, column in _COMPOSITION_FLOWS
            if row[column] is not None
        ]
        biosphere.append(Exchange(flow=flow(HALON_1211), amount=row["halon1211_rate_kg_per_tkm"] * tkm, unit=KG))
        biosphere.append(Exchange(flow=flow(HFC_23), amount=row["hfc23_rate_kg_per_tkm"] * tkm, unit=KG))

        return Result(
            production=[Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)],
            technosphere=technosphere,
            biosphere=biosphere,
            provenance=dict(row.provenance)
            | {"tier": row["tier"], "leaked_volume_nm3": leaked_nm3, "tkm": tkm},
        )
