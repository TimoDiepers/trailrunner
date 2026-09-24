"""Natural gas from the field to the burner tip: the market, and the well.

The cement kiln and the gas plant both ask for the same thing -- MJ of
``fi_12020``, "Natural gas, liquefied or in the gaseous state" -- and before
this module nobody produced it, so the tour's largest single input was a
cutoff leaf. What sat unreachable behind that leaf was
``natural_gas_pipeline_transport``, a model reverse-engineered from real
BAFU/ecoinvent datasets: it was registered in the showcase all along and
never once asked, because it produces *transport* (tkm) and nothing in the
chain demanded transport.

``NaturalGasSupply`` is the missing hop, and its only job is unit and
geography bookkeeping: MJ of delivered gas become Nm3 at the wellhead
through an energy content, and Nm3 become tkm of pipeline through a density
and a route length. Both of those demands are placed at the *origin*, not at
the consumer, which is what makes the pipeline model's own tier split do
anything: Danish gas comes down the Norwegian shelf (low-leakage tier) and
European gas comes a great deal further from Russia (high-leakage tier), and
the same MJ therefore leak a different amount of methane depending on who
burns them.

``NaturalGasExtraction`` closes the chain with the two elementary flows a
gas field cannot avoid having: the CO2 of its own flaring, venting and
compressor fuel, and the gas taken out of the ground. It is deliberately
that and nothing else. A field model worth the name would have produced
water, well construction and a dozen more substances; this one exists so the
chain terminates in a resource rather than in a cutoff, and its parameters
say so.
"""

from trailrunner.core.errors import ValidationError
from trailrunner.core.flow import Demand, Exchange, Flow
from trailrunner.core.model import Model
from trailrunner.core.result import Result
from trailrunner.core.settings import ALLOCATION_RULES
from trailrunner.models.natural_gas_pipeline_transport import (
    NATURAL_GAS_AT_PRODUCTION,
    TRANSPORT,
)
from trailrunner.params.coverage import Coverage

NATURAL_GAS = "https://vocab.sentier.dev/products/bonsai/2025.1/BONSAI2025.1/fi_12020"  # "Natural gas, liquefied or in the gaseous state"
"""Same IRI as ``electricity.NATURAL_GAS`` and ``cement.NATURAL_GAS``.

Spelled out here rather than imported from either, because what this model
produces is a fact about this model, not a dependency on whoever burns it.
"""

CO2_FOSSIL = "https://vocab.sentier.dev/flows/co2-fossil"
NATURAL_GAS_IN_GROUND = "https://vocab.sentier.dev/flows/natural-gas-in-ground"
"""The resource taken out of the reservoir, as an elementary flow.

An invented IRI, like ``electricity.ELECTRICITY_GAS``: the vocabulary's
resource branch is out of scope for this pass. Nothing characterizes it, so
it surfaces in an assessment's ``uncharacterized`` list -- which is the
correct answer for a resource under a climate method, and visible rather
than dropped.
"""

MJ = "MJ"
"""The unit this model reasons in.

Energy content is MJ/Nm3, so a demand in kg or Nm3 would be divided by a
factor that does not apply to it. It is rejected instead.
"""

NM3 = "Nm3"
"""Likewise for extraction: the emission factors below are per Nm3."""

KG_PER_TONNE = 1000.0


class NaturalGasSupply(Model):
    """Delivered natural gas: gas at the wellhead, plus the pipeline leg.

    Monofunctional and emission-free by construction. Nothing is burned here
    -- the combustion CO2 belongs to whoever burns it, the leakage to the
    pipeline, the flaring to the field -- so this model contributes no
    biosphere flows at all, only the two demands that carry the gas from
    where it is to where it was asked for.
    """

    produces = [NATURAL_GAS]
    coverage = Coverage(time_range=(2000, 2050))

    supports = ALLOCATION_RULES
    """Every rule, because this model is monofunctional.

    Monofunctionality is a fact about the model, not a value judgement: with a
    single product there is nothing to partition, so ``allocate`` takes its
    no-op short-circuit and ``substitute`` mints no credits, and the answer is
    the same under all five rules.
    """

    def apply(self, demand: Demand) -> Result:
        if demand.unit != MJ:
            raise ValidationError(
                f"{type(self).__name__} was asked for {demand.unit!r} of "
                f"{demand.flow.iri}; it converts energy to volume through an "
                f"MJ/Nm3 energy content and only {MJ} can be read that way"
            )

        row = self.params.at(location=demand.flow.location, time=demand.flow.time)
        origin = row["origin"]

        volume_nm3 = demand.amount / float(row["energy_content_mj_per_nm3"])
        tonnes = volume_nm3 * float(row["gas_density_kg_per_nm3"]) / KG_PER_TONNE
        tkm = tonnes * float(row["transport_distance_km"])

        # At the origin, not at the consumer: a route's leakage tier is a
        # property of where the pipeline runs, and asking for transport
        # "in Denmark" would hand the Norwegian leg to whatever Danish row
        # happened to exist -- or to no row at all.
        there = dict(location=origin, time=demand.flow.time)

        return Result(
            production=[
                Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)
            ],
            technosphere=[
                Demand(
                    flow=Flow(iri=NATURAL_GAS_AT_PRODUCTION, **there),
                    amount=volume_nm3,
                    unit=NM3,
                ),
                Demand(flow=Flow(iri=TRANSPORT, **there), amount=tkm, unit="tkm"),
            ],
            provenance=dict(row.provenance)
            | {"origin": origin, "volume_nm3": volume_nm3, "transport_tkm": tkm},
        )


class NaturalGasExtraction(Model):
    """A gas field, as two elementary flows and nothing else.

    The CO2 is everything the field burns, flares and vents to get the gas up
    and into the pipeline; the resource flow is the gas itself leaving the
    reservoir, which is more than what ships because the field runs on some
    of it. Both are illustrative per-Nm3 factors, and both are the whole
    model: there is no technosphere here, so the traversal ends at this node.
    """

    produces = [NATURAL_GAS_AT_PRODUCTION]
    coverage = Coverage(time_range=(2000, 2050))

    supports = ALLOCATION_RULES
    """Every rule, because this model is monofunctional. See NaturalGasSupply."""

    def apply(self, demand: Demand) -> Result:
        if demand.unit != NM3:
            raise ValidationError(
                f"{type(self).__name__} was asked for {demand.unit!r} of "
                f"{demand.flow.iri}; its factors are per {NM3} and only "
                f"{NM3} can be read that way"
            )

        row = self.params.at(location=demand.flow.location, time=demand.flow.time)
        here = dict(location=demand.flow.location, time=demand.flow.time)

        return Result(
            production=[
                Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)
            ],
            biosphere=[
                Exchange(
                    flow=Flow(iri=CO2_FOSSIL, **here),
                    amount=demand.amount * float(row["co2_kg_per_nm3"]),
                    unit=row.unit_of("co2_kg_per_nm3"),
                ),
                Exchange(
                    flow=Flow(iri=NATURAL_GAS_IN_GROUND, **here),
                    amount=demand.amount * float(row["extracted_nm3_per_nm3"]),
                    unit=NM3,
                ),
            ],
            provenance=dict(row.provenance),
        )
