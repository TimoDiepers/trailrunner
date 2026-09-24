"""The cement, grid-electricity and pipeline-transport models, wired to the
example parameter parquet files.

Exposes ``MODELS`` -- the list ``trailrunner run --models
examples/showcase_models.py`` loads, and the same list the showcase notebook
(``examples/showcase.ipynb``) uses, so a demand run from the CLI and one run
from the notebook walk the same supply chain. The parquet files themselves
are built by ``dev/build_showcase_params.py`` from the exact rows
``examples/dac.ipynb`` already demonstrates for the grid and gas models,
plus two illustrative cement tables the showcase itself needs.

No trailpack import: ``ParameterSet.from_parquet`` reads plain pyarrow
parquet files with an embedded ``datapackage.json``, so this module (and a
``trailrunner run`` that loads it) needs nothing beyond trailrunner's own
``pyarrow`` dependency.
"""

from pathlib import Path

from trailrunner import LocationHierarchy, ParameterSet
from trailrunner.models.cement import CementPlant, MeteredCementPlant
from trailrunner.models.electricity import GasPower, GridElectricity
from trailrunner.models.natural_gas import NaturalGasExtraction, NaturalGasSupply
from trailrunner.models.natural_gas_pipeline_transport import (
    NaturalGasOffshorePipelineTransport,
)

_HERE = Path(__file__).parent

# The fallback chain examples/dac.ipynb uses, plus Denmark, where the
# showcase's cement works sits. Each country falls back to Europe, and
# Europe to the global root.
_HIERARCHY = LocationHierarchy({"CH": "RER", "DK": "RER", "FR": "RER", "RER": "GLO"})

_cement_params = ParameterSet.from_parquet(
    _HERE / "cement_params.parquet", hierarchy=_HIERARCHY
)
_cement_metered_params = ParameterSet.from_parquet(
    _HERE / "cement_metered_params.parquet", hierarchy=_HIERARCHY
)
_grid_params = ParameterSet.from_parquet(
    _HERE / "grid_electricity_params.parquet", hierarchy=_HIERARCHY
)
_gas_params = ParameterSet.from_parquet(_HERE / "gas_power_params.parquet", hierarchy=_HIERARCHY)
_pipeline_params = ParameterSet.from_parquet(
    _HERE / "pipeline_transport_params.parquet", hierarchy=_HIERARCHY
)
_gas_supply_params = ParameterSet.from_parquet(
    _HERE / "natural_gas_supply_params.parquet", hierarchy=_HIERARCHY
)
_gas_extraction_params = ParameterSet.from_parquet(
    _HERE / "natural_gas_extraction_params.parquet", hierarchy=_HIERARCHY
)

MODELS = [
    # Two models, one product IRI, disjoint Coverage year ranges: a demand
    # for a past year reaches the meter, one for a future year reaches the
    # calculation, and Glossary.resolve does the choosing.
    #
    # The kiln's burners take gas at 4 bar and NaturalGasSupply delivers at 5,
    # so tier 1 alone leaves the kiln's gas a coverage_excluded cutoff. Allow
    # pressure to be met higher (`--context-tolerance pressure=0:1` on the
    # CLI, ProxySettings(context_tolerance=...) in Python) and tier 2 answers
    # it, on the record. The gas plant's gas names no pressure and needs none.
    CementPlant(params=_cement_params, burner_pressure=4.0),
    MeteredCementPlant(params=_cement_metered_params),
    GridElectricity(params=_grid_params),
    GasPower(params=_gas_params),
    # The gas chain: the kiln and the gas plant both burn fi_12020, so
    # NaturalGasSupply answers that, converts it to wellhead volume and route
    # length, and hands the two on to the field and to the pipeline model --
    # which was registered here long before anything demanded tkm from it.
    NaturalGasSupply(params=_gas_supply_params),
    NaturalGasOffshorePipelineTransport(params=_pipeline_params),
    NaturalGasExtraction(params=_gas_extraction_params),
]
