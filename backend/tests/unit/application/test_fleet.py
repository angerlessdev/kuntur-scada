import pytest

from kuntur.application.fleet import SyncReport, sync_fleet
from kuntur.domain.errors import DomainValidationError
from tests.factories import barrier, camera, ups
from tests.fakes import build_app


def test_the_first_sync_adds_and_the_second_changes_nothing() -> None:
    app = build_app()
    assert sync_fleet(app.uow, [ups(), barrier()]) == SyncReport(added=2, updated=0, retired=0)
    assert sync_fleet(app.uow, [ups(), barrier()]) == SyncReport(added=0, updated=0, retired=0)


def test_a_changed_declaration_updates_the_device() -> None:
    app = build_app(ups())
    assert sync_fleet(app.uow, [ups(name="UPS renovado")]) == SyncReport(added=0, updated=1, retired=0)
    assert app.queries.device("ups-01").device.name == "UPS renovado"


def test_a_device_no_longer_declared_is_retired_not_deleted() -> None:
    app = build_app(ups(), camera())
    assert sync_fleet(app.uow, [ups()]) == SyncReport(added=0, updated=0, retired=1)
    assert [view.device.id for view in app.queries.overview()] == ["ups-01"]
    assert app.queries.device("camara-01").device.active is False


def test_a_repeated_id_is_rejected() -> None:
    with pytest.raises(DomainValidationError):
        sync_fleet(build_app().uow, [ups(), ups()])
