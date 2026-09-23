from trailrunner.core.flow import Demand, Exchange, Flow
from trailrunner.core.result import Result
from trailrunner.orchestration.log import Log
from trailrunner.orchestration.report import Report

CAPTURED = "https://vocab.sentier.dev/products/co2-captured"
HEAT = "https://vocab.sentier.dev/products/heat"
GAS = "https://vocab.sentier.dev/products/natural-gas"
CO2 = Flow(iri="https://vocab.sentier.dev/flows/co2-fossil", location="CH", time=2030)


def built_report() -> Report:
    """Root -> heat -> an unresolved gas demand, with one biosphere flow."""
    log = Log()
    root_demand = Demand(
        flow=Flow(iri=CAPTURED, location="CH", time=2030), amount=1000.0, unit="kg"
    )
    heat_demand = Demand(flow=Flow(iri=HEAT, location="CH", time=2030), amount=5000.0, unit="MJ")
    gas_demand = Demand(flow=Flow(iri=GAS, location="CH", time=2030), amount=125.0, unit="kg")

    root = log.write(
        root_demand,
        Result(
            production=[Exchange(flow=root_demand.flow, amount=1000.0, unit="kg")],
            technosphere=[heat_demand],
            biosphere=[Exchange(flow=CO2, amount=12.0, unit="kg")],
        ),
        model="DirectAirCapture",
        resolution={"tier": "model", "model": "DirectAirCapture"},
    )
    log.write(
        heat_demand,
        Result(production=[Exchange(flow=heat_demand.flow, amount=5000.0, unit="MJ")]),
        depth=1,
        parent=root,
        model="GasBoiler",
        resolution={"tier": "generalising", "relaxations": ["location: CH -> RER"]},
    )
    log.unresolved(gas_demand, reason="no_model_found", depth=2, parent=1)
    return Report.from_log(log)


def test_tree_shows_every_node_in_traversal_order():
    tree = built_report().tree()
    assert tree.index("co2-captured") < tree.index("heat") < tree.index("natural-gas")


def test_tree_tags_an_exact_match_with_its_model():
    assert "[model: DirectAirCapture]" in built_report().tree()


def test_tree_tags_a_generalised_node_with_what_was_relaxed():
    tree = built_report().tree()
    assert "[proxy: location: CH -> RER]" in tree


def test_tree_tags_an_unresolved_demand_with_its_reason():
    assert "[cutoff: no_model_found]" in built_report().tree()


def test_tree_indents_children_under_their_parent():
    lines = {
        line.strip().split()[2]: len(line) - len(line.lstrip())
        for line in built_report().tree().splitlines()
    }
    assert lines["co2-captured"] < lines["heat"] < lines["natural-gas"]


def test_tree_shows_the_amount_and_unit_of_each_demand():
    tree = built_report().tree()
    assert "1000" in tree and "kg" in tree
    assert "5000" in tree and "MJ" in tree


def test_summary_counts_nodes_and_inventory_entries():
    summary = built_report().summary()
    assert "2 nodes" in summary
    assert "1 inventory entry" in summary


def test_summary_breaks_unresolved_down_by_reason():
    assert "no_model_found: 1" in built_report().summary()


def test_summary_reports_proxies():
    summary = built_report().summary()
    assert "1 proxy" in summary


def test_summary_says_when_the_traversal_was_truncated():
    log = Log()
    assert "truncated" in Report.from_log(log, truncated=True).summary()
    assert "truncated" not in Report.from_log(log).summary()


def test_summary_of_an_empty_report_does_not_crash():
    assert "0 nodes" in Report.from_log(Log()).summary()


def test_tree_tags_a_unit_process_borrow_as_incomplete():
    """basis=unit_process means the upstream is missing, not just deferred --
    the tree must say so distinctly from a cumulative (complete) borrow."""
    log = Log()
    demand = Demand(flow=Flow(iri=GAS, location="GLO"), amount=1.0, unit="kg")
    log.write(
        demand,
        Result(production=[Exchange(flow=demand.flow, amount=1.0, unit="kg")]),
        resolution={
            "tier": "background",
            "kind": "linear_background",
            "dataset": "natural gas, at consumer",
            "basis": "unit_process",
            "complete": False,
        },
    )
    tree = Report.from_log(log).tree()
    assert "unit_process" in tree
    assert "incomplete" in tree


def test_tree_tags_a_cumulative_borrow_as_complete_and_distinctly():
    log = Log()
    demand = Demand(flow=Flow(iri=GAS, location="GLO"), amount=1.0, unit="kg")
    log.write(
        demand,
        Result(production=[Exchange(flow=demand.flow, amount=1.0, unit="kg")]),
        resolution={
            "tier": "background",
            "kind": "linear_background",
            "dataset": "clinker, at plant (cumulative)",
            "basis": "cumulative",
            "complete": True,
        },
    )
    tree = Report.from_log(log).tree()
    assert "cumulative" in tree
    assert "incomplete" not in tree


def test_an_unrecognised_tier_is_never_labelled_an_exact_match():
    """tree() and proxies must agree: whatever summary() counts as a proxy,
    tree() must not print as a model."""
    log = Log()
    demand = Demand(flow=Flow(iri=HEAT, location="CH", time=2030), amount=1.0, unit="MJ")
    log.write(
        demand,
        Result(production=[Exchange(flow=demand.flow, amount=1.0, unit="MJ")]),
        model="Mystery",
        resolution={"tier": "linear_background"},
    )
    report = Report.from_log(log)
    assert "[model" not in report.tree()
    assert "linear_background" in report.tree()
    assert len(report.proxies) == 1


def test_summary_breaks_incomplete_borrows_out_of_the_proxy_count():
    """summary() is the one-line trust check; an incomplete borrow must be
    visible there, not only in report.proxies or report.tree()."""
    log = Log()
    unit_process_demand = Demand(flow=Flow(iri=GAS, location="GLO"), amount=1.0, unit="kg")
    cumulative_demand = Demand(
        flow=Flow(iri="https://vocab.sentier.dev/products/clinker", location="GLO"),
        amount=1.0,
        unit="kg",
    )
    log.write(
        unit_process_demand,
        Result(production=[Exchange(flow=unit_process_demand.flow, amount=1.0, unit="kg")]),
        resolution={
            "tier": "background",
            "kind": "linear_background",
            "dataset": "natural gas, at consumer",
            "basis": "unit_process",
            "complete": False,
        },
    )
    log.write(
        cumulative_demand,
        Result(production=[Exchange(flow=cumulative_demand.flow, amount=1.0, unit="kg")]),
        resolution={
            "tier": "background",
            "kind": "linear_background",
            "dataset": "clinker, at plant (cumulative)",
            "basis": "cumulative",
            "complete": True,
        },
    )
    summary = Report.from_log(log).summary()
    assert "2 proxies (1 incomplete)" in summary


def test_summary_says_nothing_extra_when_no_proxy_is_incomplete():
    summary = built_report().summary()
    assert "incomplete" not in summary


def test_a_resolution_without_a_tier_is_treated_as_an_exact_match():
    """The absent-tier default is 'model' in both views, not just one."""
    log = Log()
    demand = Demand(flow=Flow(iri=HEAT, location="CH", time=2030), amount=1.0, unit="MJ")
    log.write(
        demand,
        Result(production=[Exchange(flow=demand.flow, amount=1.0, unit="MJ")]),
        model="Boiler",
        resolution={"model": "Boiler"},
    )
    report = Report.from_log(log)
    assert "[model: Boiler]" in report.tree()
    assert report.proxies == {}


def test_tree_and_summary_agree_on_an_unrecognised_basis():
    """``complete`` is the one authority on whether a borrow's upstream is
    there. Re-deriving the tag from ``basis`` instead let ``tree()`` print a
    bare ``[background]`` for a basis it did not recognise while
    ``summary()`` counted the same node as incomplete -- two views of one
    node disagreeing."""
    log = Log()
    demand = Demand(flow=Flow(iri=GAS, location="GLO"), amount=1.0, unit="kg")
    log.write(
        demand,
        Result(production=[Exchange(flow=demand.flow, amount=1.0, unit="kg")]),
        resolution={
            "tier": "background",
            "kind": "linear_background",
            "dataset": "something, at plant",
            "basis": "estimated",
            "complete": False,
        },
    )
    report = Report.from_log(log)
    assert "incomplete" in report.tree()
    assert "1 proxy (1 incomplete)" in report.summary()


def test_tree_prints_a_name_when_one_is_given_for_the_iri():
    """A flow is keyed on its IRI; a reader wants what the vocabulary calls it."""
    tree = built_report().tree(labels={CAPTURED: "Carbon dioxide", HEAT: "Steam and hot water"})

    assert "1000 kg Carbon dioxide @CH/2030" in tree
    assert "5000 MJ Steam and hot water @CH/2030" in tree


def test_tree_names_a_cutoff_as_readily_as_a_node():
    """The cutoff list is part of the answer, so it reads like the rest of it."""
    tree = built_report().tree(labels={GAS: "Natural gas, liquefied or in the gaseous state"})

    assert "125 kg Natural gas, liquefied or in the gaseous state @CH/2030" in tree


def test_an_iri_the_mapping_has_no_name_for_falls_back_to_the_last_segment():
    """Every invented IRI lands here, which is what makes a partial map useful."""
    tree = built_report().tree(labels={CAPTURED: "Carbon dioxide"})

    assert "Carbon dioxide" in tree
    assert "natural-gas" in tree


def test_tree_takes_a_callable_as_readily_as_a_mapping():
    """A cache read off disk is a dict; a live lookup is a function."""
    tree = built_report().tree(labels=lambda iri: "Named" if iri == HEAT else None)

    assert "5000 MJ Named @CH/2030" in tree
    assert "co2-captured" in tree


def test_a_label_lookup_that_raises_does_not_break_the_tree():
    """Labels are presentation: nothing here may cost a reader their report."""

    def explode(iri):
        raise RuntimeError("the vocabulary is down")

    tree = built_report().tree(labels=explode)

    assert "co2-captured" in tree
    assert "natural-gas" in tree


def test_no_labels_prints_exactly_what_it_printed_before():
    assert built_report().tree(labels=None) == built_report().tree()
