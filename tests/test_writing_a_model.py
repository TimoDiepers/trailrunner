"""The docs have to teach the Model contract, not just run a shipped model.

A model author's first question is what ``apply`` must return. Discovering the
answer from the Runner's validation errors, one raise at a time, is not a
documented API. So: "Writing a Model" carries a worked model, and this
executes it.
"""

import re
from pathlib import Path

import pytest

from trailrunner import Demand, Flow, Model, Runner, ValidationError
from trailrunner.orchestration.glossary import Glossary
from trailrunner.core.units import KWH, MJ

GUIDE = Path(__file__).resolve().parent.parent / "docs" / "content" / "writing_a_model.md"


def guide_block_defining(name: str) -> str:
    blocks = re.findall(r"```python\n(.*?)```", GUIDE.read_text(), flags=re.DOTALL)
    matching = [block for block in blocks if f"class {name}(Model)" in block]
    assert matching, f"writing_a_model.md defines no {name} model"
    return matching[0]


def test_the_guide_shows_how_to_write_a_model():
    namespace: dict = {}
    exec(guide_block_defining("GasTurbine"), namespace)  # noqa: S102 — that is the point
    model = namespace["GasTurbine"]()

    product = list(model.produces)[0]
    demand = Demand(flow=Flow(iri=product, location="CH", time=2030), amount=100.0, unit=KWH)
    result = Runner(Glossary([model])).apply(demand)

    assert result.biosphere, "the guide's model should emit something"


def test_the_guide_model_satisfies_the_production_contract():
    """The example must not teach a shape the Runner rejects."""
    namespace: dict = {}
    exec(guide_block_defining("GasTurbine"), namespace)  # noqa: S102
    model = namespace["GasTurbine"]()
    product = list(model.produces)[0]

    for amount in (1.0, 250.0, 1e6):
        demand = Demand(flow=Flow(iri=product), amount=amount, unit=KWH)
        Runner.validate(demand, model.apply(demand), model=model)


def test_apply_documents_the_production_contract():
    """Where a model author will actually look for it."""
    doc = Model.apply.__doc__ or ""
    assert "production" in doc
    assert "cover" in doc


def test_a_model_that_ignores_the_documented_contract_is_rejected():
    class Forgetful(Model):
        produces = ("https://vocab.sentier.dev/products/heat",)

        def apply(self, demand: Demand):
            from trailrunner import Result

            return Result(production=[])

    demand = Demand(flow=Flow(iri="https://vocab.sentier.dev/products/heat"), amount=1.0, unit=MJ)
    with pytest.raises(ValidationError):
        Runner(Glossary([Forgetful()])).apply(demand)
