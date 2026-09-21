"""The README has to teach the Model contract, not just run a shipped model.

A model author's first question is what ``apply`` must return. Discovering the
answer from the Runner's validation errors, one raise at a time, is not a
documented API. So: the README carries a worked model, and this executes it.
"""

import re
from pathlib import Path

import pytest

from trailrunner import Demand, Flow, Model, Runner, ValidationError
from trailrunner.orchestration.glossary import Glossary

README = Path(__file__).resolve().parent.parent / "README.md"


def readme_block_defining(name: str) -> str:
    blocks = re.findall(r"```python\n(.*?)```", README.read_text(), flags=re.DOTALL)
    matching = [block for block in blocks if f"class {name}(Model)" in block]
    assert matching, f"the README defines no {name} model"
    return matching[0]


def test_the_readme_shows_how_to_write_a_model():
    namespace: dict = {}
    exec(readme_block_defining("MyBoiler"), namespace)  # noqa: S102 — that is the point
    boiler = namespace["MyBoiler"]()

    heat = [iri for iri in boiler.produces][0]
    demand = Demand(flow=Flow(iri=heat, location="CH", time=2030), amount=100.0, unit="MJ")
    result = Runner(Glossary([boiler])).apply(demand)

    assert result.biosphere, "the README's model should emit something"


def test_the_readme_model_satisfies_the_production_contract():
    """The example must not teach a shape the Runner rejects."""
    namespace: dict = {}
    exec(readme_block_defining("MyBoiler"), namespace)  # noqa: S102
    boiler = namespace["MyBoiler"]()
    heat = list(boiler.produces)[0]

    for amount in (1.0, 250.0, 1e6):
        demand = Demand(flow=Flow(iri=heat), amount=amount, unit="MJ")
        Runner.validate(demand, boiler.apply(demand), model=boiler)


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

    demand = Demand(flow=Flow(iri="https://vocab.sentier.dev/products/heat"), amount=1.0, unit="MJ")
    with pytest.raises(ValidationError):
        Runner(Glossary([Forgetful()])).apply(demand)
