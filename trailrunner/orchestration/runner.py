"""Calls a model and checks that it honoured its contract."""

from trailrunner.core.errors import NoProducer, ValidationError
from trailrunner.core.flow import Demand
from trailrunner.core.model import Model
from trailrunner.core.result import Result
from trailrunner.orchestration.glossary import Glossary


class Runner:
    """Synchronous. The single place where Result validation happens.

    It is a separate object so that a concurrent implementation can replace it
    behind the same interface without the Orchestrator changing.
    """

    def __init__(self, glossary: Glossary) -> None:
        self.glossary = glossary

    def apply(self, demand: Demand, model: Model | None = None) -> Result:
        if model is None:
            model = self.glossary.resolve(demand.flow)
        if model is None:
            raise NoProducer(
                f"no model produces {demand.flow.iri} at "
                f"location={demand.flow.location!r} time={demand.flow.time!r}"
            )
        result = model.apply(demand)
        self.validate(demand, result, model=model)
        return result

    @staticmethod
    def validate(demand: Demand, result: Result, model: Model | None = None) -> None:
        origin = type(model).__name__ if model is not None else "model"

        if not isinstance(result, Result):
            raise ValidationError(f"{origin} returned {type(result).__name__}, expected Result")

        matching = [e for e in result.production if e.flow.iri == demand.flow.iri]
        if not matching:
            raise ValidationError(
                f"{origin} did not produce the demanded product {demand.flow.iri}; "
                f"produced {[e.flow.iri for e in result.production]}"
            )

        mismatched = [e.unit for e in matching if e.unit != demand.unit]
        if mismatched:
            raise ValidationError(
                f"{origin} produced {demand.flow.iri} in {mismatched[0]!r} "
                f"but the demand is in {demand.unit!r}"
            )

        for exchange in result.production:
            if exchange.amount <= 0:
                raise ValidationError(
                    f"{origin} produced a non-positive amount "
                    f"({exchange.amount}) of {exchange.flow.iri}"
                )

        for exchange in (*result.production, *result.technosphere, *result.biosphere):
            if not exchange.unit:
                raise ValidationError(f"{origin} returned {exchange.flow.iri} without a unit")
