import textwrap

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
