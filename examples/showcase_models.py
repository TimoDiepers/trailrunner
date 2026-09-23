"""The DAC, grid-electricity and pipeline-transport models, wired to the
example parameter parquet files.

Exposes ``MODELS`` -- the list ``trailrunner run --models
examples/showcase_models.py`` loads, and the same list the showcase notebook
(``examples/showcase.ipynb``) uses, so a demand run from the CLI and one run
from the notebook walk the same supply chain. The parquet files themselves
are built by ``dev/build_showcase_params.py`` from the exact rows
``examples/dac.ipynb`` already demonstrates -- nothing here invents a number.

No trailpack import: ``ParameterSet.from_parquet`` reads plain pyarrow
parquet files with an embedded ``datapackage.json``, so this module (and a
``trailrunner run`` that loads it) needs nothing beyond trailrunner's own
``pyarrow`` dependency.
"""

from pathlib import Path

from trailrunner import LocationHierarchy, ParameterSet
from trailrunner.models.dac import DirectAirCapture
from trailrunner.models.electricity import GasPower, GridElectricity
from trailrunner.models.natural_gas_pipeline_transport import (
    NaturalGasOffshorePipelineTransport,
)

_HERE = Path(__file__).parent

# Same fallback chain examples/dac.ipynb uses: Switzerland and France both
# fall back to Europe, Europe falls back to the global root.
_HIERARCHY = LocationHierarchy({"CH": "RER", "FR": "RER", "RER": "GLO"})

_dac_params = ParameterSet.from_parquet(_HERE / "dac_params.parquet", hierarchy=_HIERARCHY)
_grid_params = ParameterSet.from_parquet(
    _HERE / "grid_electricity_params.parquet", hierarchy=_HIERARCHY
)
_gas_params = ParameterSet.from_parquet(_HERE / "gas_power_params.parquet", hierarchy=_HIERARCHY)
_pipeline_params = ParameterSet.from_parquet(
    _HERE / "pipeline_transport_params.parquet", hierarchy=_HIERARCHY
)

MODELS = [
    DirectAirCapture(params=_dac_params),
    GridElectricity(params=_grid_params),
    GasPower(params=_gas_params),
    NaturalGasOffshorePipelineTransport(params=_pipeline_params),
]
