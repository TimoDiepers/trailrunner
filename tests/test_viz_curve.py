import pytest

pytest.importorskip("plotly")
pytest.importorskip("dynamic_characterization")

from trailrunner.assessment import assess_dynamic  # noqa: E402
from trailrunner.core.flow import Demand, Exchange, Flow  # noqa: E402
from trailrunner.core.result import Result  # noqa: E402
from trailrunner.orchestration.log import Log  # noqa: E402
from trailrunner.orchestration.report import Report  # noqa: E402
from trailrunner.viz import curve  # noqa: E402

from .conftest import CO2_IRI  # noqa: E402
from trailrunner.core.units import KG

CAPTURED = "https://vocab.sentier.dev/products/co2-captured"


def test_curve_draws_the_series_and_its_cumulative_integral():
    log = Log()
    demand = Demand(flow=Flow(iri=CAPTURED, location="CH", time=2030), amount=1.0, unit=KG)
    log.write(
        demand,
        Result(
            production=[Exchange(flow=demand.flow, amount=1.0, unit=KG)],
            biosphere=[
                Exchange(flow=Flow(iri=CO2_IRI, location="CH", time=2030), amount=10.0, unit=KG)
            ],
        ),
        model="DirectAirCapture",
    )
    figure = curve(assess_dynamic(Report.from_log(log), horizon=20))
    assert len(figure.data) == 2
    # The marginal axis is W/m2; the cumulative one is its integral.
    assert figure.layout.yaxis.title.text.startswith("W/m2")
    assert figure.layout.yaxis2.title.text.startswith("W")
    assert figure.layout.yaxis2.title.text != figure.layout.yaxis.title.text


def test_the_bars_are_one_per_year_not_one_per_emission():
    """Two emissions in the same year make one bar, not two overlapping ones."""
    log = Log()
    for year in (2030, 2030):
        demand = Demand(flow=Flow(iri=CAPTURED, location="CH", time=year), amount=1.0, unit=KG)
        log.write(
            demand,
            Result(
                production=[Exchange(flow=demand.flow, amount=1.0, unit=KG)],
                biosphere=[
                    Exchange(flow=Flow(iri=CO2_IRI, location="CH", time=year), amount=5.0, unit=KG)
                ],
            ),
            model="DirectAirCapture",
        )
    figure = curve(assess_dynamic(Report.from_log(log), horizon=10))
    dates = list(figure.data[0].x)
    assert len(dates) == len(set(dates))
