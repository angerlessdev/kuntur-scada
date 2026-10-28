import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { FleetStore } from './fleet';
import { Alert, DeviceOverview, Reading } from './models';

function overview(id: string, site: string, name: string): DeviceOverview {
  return {
    device: { id, name, kind: 'UPS', site, installed_on: '2023-03-10', active: true },
    health: 'OK',
    last_reading: null,
    active_alerts: [],
    life: { replacement_date: '2028-07-19', governing: 'BATTERY', overdue: false, clocks: [] },
  };
}

function alert(
  id: string,
  severity: Alert['severity'],
  raisedAt: string,
  deviceId = 'ups-norte-01',
): Alert {
  const code = severity === 'CRITICAL' ? 'DEVICE_UNREACHABLE' : 'UPS_BATTERY_HOT';
  return {
    id,
    device_id: deviceId,
    code,
    severity,
    message: 'x',
    raised_at: raisedAt,
    state: 'ACTIVE',
    resolved_at: null,
  };
}

describe('FleetStore', () => {
  let store: FleetStore;
  let http: HttpTestingController;

  beforeEach(async () => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    store = TestBed.inject(FleetStore);
    http = TestBed.inject(HttpTestingController);
    const loading = store.refresh();
    http
      .expectOne('/api/v1/devices')
      .flush([
        overview('ups-sur-01', 'Estación Sur', 'UPS Sur'),
        overview('ups-norte-01', 'Estación Norte', 'UPS Norte'),
      ]);
    http.expectOne((request) => request.url === '/api/v1/alerts').flush([]);
    await loading;
  });

  afterEach(() => http.verify());

  it('groups the fleet by site, in alphabetical order', () => {
    expect(store.sites().map((site) => site.name)).toEqual(['Estación Norte', 'Estación Sur']);
    expect(store.loaded()).toBe(true);
  });

  it('applies a live reading to its device', () => {
    const reading: Reading = {
      device_id: 'ups-norte-01',
      taken_at: '2026-01-15T13:00:00Z',
      status: 'FAILED',
      metrics: {},
      cause: 'TIMEOUT',
      detail: null,
    };
    store.apply({
      type: 'reading',
      device_id: 'ups-norte-01',
      kind: 'UPS',
      health: 'DEGRADED',
      reading,
    });
    const view = store.devices().get('ups-norte-01');
    expect(view?.health).toBe('DEGRADED');
    expect(view?.last_reading).toEqual(reading);
  });

  it('orders active alerts by urgency, then by age, and forgets resolved ones', () => {
    store.apply({ type: 'alert_raised', alert: alert('a1', 'WARNING', '2026-01-15T12:00:00Z') });
    store.apply({ type: 'alert_raised', alert: alert('a2', 'CRITICAL', '2026-01-15T12:30:00Z') });
    store.apply({ type: 'alert_raised', alert: alert('a3', 'CRITICAL', '2026-01-15T12:10:00Z') });
    expect(store.active().map((a) => a.id)).toEqual(['a3', 'a2', 'a1']);
    expect(store.counts()).toEqual({ critical: 2, warning: 1 });
    expect(store.arrived()?.id).toBe('a3');

    store.apply({
      type: 'alert_resolved',
      alert: { ...alert('a2', 'CRITICAL', '2026-01-15T12:30:00Z'), state: 'RESOLVED' },
    });
    expect(store.active().map((a) => a.id)).toEqual(['a3', 'a1']);
    expect(
      store
        .devices()
        .get('ups-norte-01')
        ?.active_alerts.map((a) => a.id),
    ).toEqual(['a1', 'a3']);
  });

  it('ignores news about devices it does not know', () => {
    store.apply({
      type: 'alert_raised',
      alert: alert('a9', 'CRITICAL', '2026-01-15T12:00:00Z', 'fantasma'),
    });
    expect(store.devices().has('fantasma')).toBe(false);
  });
});
