import textwrap
from pathlib import Path

import pytest

from trailrunner.cli import main

HEAT = "https://vocab.sentier.dev/products/heat"
CO2 = "https://vocab.sentier.dev/flows/co2-fossil"


@pytest.fixture
def models_file(tmp_path):
    """A module the CLI loads by path, exposing one model."""
    path = tmp_path / "mymodels.py"
    path.write_text(
        textwrap.dedent(
            f'''
            from trailrunner import Demand, Exchange, Flow, Model, Result
            from trailrunner.core.settings import ALLOCATION_RULES

            HEAT = "{HEAT}"
            CO2 = "{CO2}"


            class Boiler(Model):
                produces = [HEAT]
                # Monofunctional (one product): every rule is a no-op for it,
                # the same reasoning trailrunner.models.dac/electricity/... use
                # for their own supports = ALLOCATION_RULES.
                supports = ALLOCATION_RULES

                def apply(self, demand):
                    return Result(
                        production=[Exchange(flow=demand.flow, amount=demand.amount, unit=demand.unit)],
                        biosphere=[Exchange(
                            flow=Flow(iri=CO2, location=demand.flow.location, time=demand.flow.time),
                            amount=0.05 * demand.amount, unit="kg")],
                    )

            MODELS = [Boiler()]
            '''
        )
    )
    return path


def test_a_run_exits_zero_and_prints_the_summary(models_file, capsys):
    code = main([
        "run", HEAT, "--amount", "100", "--unit", "MJ",
        "--location", "CH", "--year", "2030", "--models", str(models_file),
    ])
    out = capsys.readouterr().out
    assert code == 0
    # report.summary() pluralizes correctly ("1 node", not "1 nodes") -- see
    # tests/test_report_text.py's "0 nodes"/"2 nodes" checks for the same rule.
    assert "1 node," in out


def test_the_tree_is_printed(models_file, capsys):
    main(["run", HEAT, "--amount", "100", "--unit", "MJ", "--models", str(models_file)])
    assert "[model: Boiler]" in capsys.readouterr().out


def test_the_log_is_written_when_asked(models_file, tmp_path):
    out = tmp_path / "log.parquet"
    main([
        "run", HEAT, "--amount", "100", "--unit", "MJ",
        "--models", str(models_file), "--out", str(out),
    ])
    assert out.exists()


def test_an_unresolved_demand_is_reported_not_fatal(models_file, capsys):
    code = main([
        "run", "https://vocab.sentier.dev/products/unobtainium",
        "--amount", "1", "--unit", "kg", "--models", str(models_file),
    ])
    assert code == 0
    assert "no_model_found" in capsys.readouterr().out


def test_a_missing_models_file_exits_nonzero_with_a_message(capsys):
    code = main(["run", HEAT, "--amount", "1", "--unit", "MJ", "--models", "/nope.py"])
    assert code == 2
    assert "nope.py" in capsys.readouterr().err


def test_the_allocation_flag_reaches_the_settings(models_file, capsys):
    main([
        "run", HEAT, "--amount", "100", "--unit", "MJ",
        "--models", str(models_file), "--allocation", "economic",
    ])
    assert "allocation=economic" in capsys.readouterr().out


def test_an_unknown_allocation_is_rejected_before_anything_runs(models_file, capsys):
    code = main([
        "run", HEAT, "--amount", "100", "--unit", "MJ",
        "--models", str(models_file), "--allocation", "vibes",
    ])
    assert code == 2
    assert "vibes" in capsys.readouterr().err


def test_the_method_flag_prints_a_score(models_file, method_parquet_file, capsys):
    code = main([
        "run", HEAT, "--amount", "100", "--unit", "MJ",
        "--location", "GLO", "--year", "2030", "--models", str(models_file),
        "--method", str(method_parquet_file),
    ])
    out = capsys.readouterr().out
    assert code == 0
    # 100 MJ * 0.05 kg CO2/MJ * 1.0 kg CO2eq/kg
    assert "5" in out and "kg CO2eq" in out


def test_the_dynamic_flag_reports_the_cumulative_unit(models_file, capsys):
    """The headline is an integral, so it must be labelled as one.

    ``W·yr/m2``, not ``W/m2``: the CLI prints ``dynamic.cumulative_unit`` and
    printing ``dynamic.unit`` there would be wrong by a dimension. Pinned here
    because 'correct by inspection' is how it was wrong before.
    """
    pytest.importorskip("dynamic_characterization")
    code = main([
        "run", HEAT, "--amount", "100", "--unit", "MJ",
        "--location", "GLO", "--year", "2030", "--models", str(models_file),
        "--dynamic", "radiative_forcing", "--horizon", "20",
    ])
    out = capsys.readouterr().out
    assert code == 0
    assert "radiative_forcing over 20 years:" in out
    assert "W·yr/m2" in out


SHOWCASE = Path(__file__).resolve().parent.parent / "examples" / "showcase_models.py"
CEMENT = "https://vocab.sentier.dev/products/bonsai/2025.1/BONSAI2025.1/fi_37440"
CEMENT_RUN = [
    "run", CEMENT, "--amount", "1000", "--unit", "kg",
    "--location", "DK", "--year", "2030", "--models", str(SHOWCASE),
]


def test_without_a_context_tolerance_the_kilns_4_bar_gas_is_a_coverage_miss(capsys):
    assert main(CEMENT_RUN) == 0
    out = capsys.readouterr().out
    assert "fi_12020 @DK/2030 (pressure=4 bar)  [cutoff: coverage_excluded]" in out


def test_a_context_tolerance_lets_5_bar_gas_answer_it_as_a_proxy(capsys):
    assert main([*CEMENT_RUN, "--context-tolerance", "pressure=0:1"]) == 0
    out = capsys.readouterr().out
    assert "[proxy: context: pressure 4 bar -> 5 bar]" in out
    assert "1 proxy" in out


def test_a_context_tolerance_that_forbids_the_side_leaves_the_cutoff(capsys):
    assert main([*CEMENT_RUN, "--context-tolerance", "pressure=1:0"]) == 0
    out = capsys.readouterr().out
    # Tier 1's reason wins: widening the coverage is what would fix it.
    assert "(pressure=4 bar)  [cutoff: coverage_excluded]" in out
    assert "0 proxies" in out


@pytest.mark.parametrize("bad", ["pressure", "pressure=1", "=0:1", "pressure=a:b", "pressure=-1:0"])
def test_a_malformed_context_tolerance_is_rejected_before_anything_runs(bad, capsys):
    assert main([*CEMENT_RUN, "--context-tolerance", bad]) == 2
    assert "context tolerance" in capsys.readouterr().err


def test_proxy_order_parses_entries_and_combinations():
    from trailrunner.cli import parse_proxy_order

    assert parse_proxy_order(None) == ("context",)
    assert parse_proxy_order("context.pressure,context.pressure+context.temperature") == (
        "context.pressure",
        ("context.pressure", "context.temperature"),
    )


@pytest.mark.parametrize(
    "order, message",
    [
        ("location", "not a context dimension"),
        ("context.temperature", "no context_tolerance for 'temperature'"),
    ],
)
def test_a_bad_proxy_order_is_rejected_before_anything_runs(order, message, capsys):
    code = main([*CEMENT_RUN, "--context-tolerance", "pressure=0:1", "--proxy-order", order])
    assert code == 2
    assert message in capsys.readouterr().err


def test_a_context_tolerance_given_twice_is_rejected(capsys):
    code = main([
        *CEMENT_RUN,
        "--context-tolerance", "pressure=0:1",
        "--context-tolerance", "pressure=0:2",
    ])
    assert code == 2
    assert "more than once" in capsys.readouterr().err


def test_a_named_condition_in_the_proxy_order_relaxes_it(capsys):
    code = main([
        *CEMENT_RUN,
        "--context-tolerance", "pressure=0:1",
        "--proxy-order", "context.pressure",
    ])
    assert code == 0
    assert "[proxy: context: pressure 4 bar -> 5 bar]" in capsys.readouterr().out
