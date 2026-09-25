import pytest

from trailrunner.core.flow import Demand, Flow
from trailrunner.orchestration.queue import Queue, QueueItem
from trailrunner.core.units import KG


def item(iri: str, amount: float = 1.0, depth: int = 0) -> QueueItem:
    return QueueItem(demand=Demand(flow=Flow(iri=iri), amount=amount, unit=KG), depth=depth)


def test_default_queue_is_first_in_first_out():
    queue = Queue()
    queue.push(item("a"))
    queue.push(item("b"))
    queue.push(item("c"))
    assert [queue.pop().demand.flow.iri for _ in range(3)] == ["a", "b", "c"]


def test_queue_is_falsy_when_empty_and_reports_its_length():
    queue = Queue()
    assert not queue
    assert len(queue) == 0
    queue.push(item("a"))
    assert queue
    assert len(queue) == 1


def test_popping_an_empty_queue_raises():
    with pytest.raises(IndexError):
        Queue().pop()


def test_priority_callable_orders_pops_smallest_first():
    queue = Queue(priority=lambda demand: -demand.amount)
    queue.push(item("small", amount=1.0))
    queue.push(item("big", amount=100.0))
    queue.push(item("medium", amount=10.0))
    assert [queue.pop().demand.flow.iri for _ in range(3)] == ["big", "medium", "small"]


def test_priority_ties_are_broken_by_insertion_order():
    queue = Queue(priority=lambda demand: 0.0)
    queue.push(item("first"))
    queue.push(item("second"))
    assert [queue.pop().demand.flow.iri for _ in range(2)] == ["first", "second"]


def test_queue_item_carries_depth_parent_and_path():
    entry = QueueItem(
        demand=Demand(flow=Flow(iri="a"), amount=1.0, unit=KG),
        depth=2,
        parent=7,
        path=("root", "a"),
    )
    assert (entry.depth, entry.parent, entry.path) == (2, 7, ("root", "a"))


def test_queue_item_defaults():
    entry = QueueItem(demand=Demand(flow=Flow(iri="a"), amount=1.0, unit=KG))
    assert (entry.depth, entry.parent, entry.path) == (0, None, ())
