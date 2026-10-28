import pytest

from kuntur.adapters.events import InMemoryEventBus
from kuntur.domain.events import DomainEvent
from tests.factories import T0, at


def test_every_handler_gets_every_event_in_order() -> None:
    bus = InMemoryEventBus()
    first: list[DomainEvent] = []
    second: list[DomainEvent] = []
    bus.subscribe(first.append)
    bus.subscribe(second.append)
    events = [DomainEvent(T0), DomainEvent(at(1))]
    bus.publish(events)
    assert first == second == events


def test_a_broken_handler_does_not_silence_the_others(caplog: pytest.LogCaptureFixture) -> None:
    bus = InMemoryEventBus()
    received: list[DomainEvent] = []

    def broken(event: DomainEvent) -> None:
        raise RuntimeError("listener roto")

    bus.subscribe(broken)
    bus.subscribe(received.append)
    bus.publish([DomainEvent(T0)])
    assert received == [DomainEvent(T0)]
    assert "Event handler failed" in caplog.text


def test_unsubscribing_stops_delivery_and_is_idempotent() -> None:
    bus = InMemoryEventBus()
    received: list[DomainEvent] = []
    unsubscribe = bus.subscribe(received.append)
    unsubscribe()
    unsubscribe()
    bus.publish([DomainEvent(T0)])
    assert received == []
