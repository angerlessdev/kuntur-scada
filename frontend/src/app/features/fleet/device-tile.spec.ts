import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { Alert, DeviceOverview } from '../../core/models';
import { DeviceTile } from './device-tile';

const NOW = new Date('2026-01-15T13:00:00Z').getTime();

function view(changes: Partial<DeviceOverview> = {}): DeviceOverview {
  return {
    device: {
      id: 'barrera-norte-02',
      name: 'Barrera salida Norte',
      kind: 'BARRIER',
      site: 'Estación Norte',
      installed_on: '2019-11-04',
      active: true,
    },
    health: 'OK',
    last_reading: {
      device_id: 'barrera-norte-02',
      taken_at: '2026-01-15T12:59:58Z',
      status: 'OK',
      metrics: { cycles_total: 3920176, impacts_total: 388, motor_temp_c: 38.3 },
      cause: null,
      detail: null,
    },
    active_alerts: [],
    life: { replacement_date: '2026-12-25', governing: 'MECHANICAL', overdue: false, clocks: [] },
    ...changes,
  };
}

function render(overview: DeviceOverview): HTMLElement {
  TestBed.configureTestingModule({ providers: [provideRouter([])] });
  const fixture = TestBed.createComponent(DeviceTile);
  fixture.componentRef.setInput('view', overview);
  fixture.componentRef.setInput('now', NOW);
  fixture.detectChanges();
  return fixture.nativeElement as HTMLElement;
}

describe('DeviceTile', () => {
  it('reads at a glance: state, freshness, counters and the replacement date with its reason', () => {
    const text = render(view()).textContent ?? '';
    expect(text).toContain('Normal');
    expect(text).toContain('leído hace un instante');
    expect(text).toContain('3,920,176');
    expect(text).toContain('Reemplazo en dic. 2026, por desgaste mecánico');
  });

  it('marks an abnormal device with a shape and a word, not only a colour', () => {
    const element = render(view({ health: 'DEGRADED' }));
    expect(element.querySelector('.tile')?.getAttribute('data-level')).toBe('warning');
    expect(element.querySelector('kt-mark')?.getAttribute('data-level')).toBe('warning');
    expect(element.textContent).toContain('Degradado');
  });

  it('does not repeat "Sin comunicación" as both the state and an alert', () => {
    const lost: Alert = {
      id: 'a1',
      device_id: 'barrera-norte-02',
      code: 'DEVICE_UNREACHABLE',
      severity: 'CRITICAL',
      message: 'Sin comunicación',
      raised_at: '2026-01-15T12:58:00Z',
      state: 'ACTIVE',
      resolved_at: null,
    };
    const element = render(view({ health: 'DOWN', active_alerts: [lost] }));
    expect(element.textContent?.match(/Sin comunicación/g)).toHaveLength(1);
  });

  it('flags an overdue replacement', () => {
    const element = render(view({ life: { ...view().life, overdue: true } }));
    expect(element.querySelector('.life.overdue')?.textContent).toContain('Reemplazo vencido');
  });
});
