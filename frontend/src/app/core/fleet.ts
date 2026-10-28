import { Injectable, computed, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { Api, problemText } from './api';
import { Alert, DeviceOverview, LiveMessage } from './models';

export interface Site {
  name: string;
  devices: DeviceOverview[];
}

const SEVERITY_ORDER = { CRITICAL: 0, WARNING: 1 } as const;

/**
 * The fleet as the screens see it: loaded once, then kept current by the live channel. Remaining-life
 * dates do not change by the second, so a slow refresh is enough for them.
 */
@Injectable({ providedIn: 'root' })
export class FleetStore {
  private readonly api = inject(Api);
  readonly devices = signal<ReadonlyMap<string, DeviceOverview>>(new Map());
  readonly alerts = signal<readonly Alert[]>([]);
  readonly loaded = signal(false);
  readonly error = signal<string | null>(null);
  /** The newest alert that arrived live: the banner pulses once for it. */
  readonly arrived = signal<Alert | null>(null);

  readonly sites = computed<Site[]>(() => {
    const bySite = new Map<string, DeviceOverview[]>();
    for (const view of this.devices().values()) {
      const list = bySite.get(view.device.site) ?? [];
      list.push(view);
      bySite.set(view.device.site, list);
    }
    return [...bySite.entries()]
      .sort(([a], [b]) => a.localeCompare(b, 'es'))
      .map(([name, devices]) => ({
        name,
        devices: devices.sort((a, b) => a.device.name.localeCompare(b.device.name, 'es')),
      }));
  });

  /** Active alerts, the most urgent first: critical before warning, then the oldest first. */
  readonly active = computed(() =>
    [...this.alerts()]
      .filter((alert) => alert.state === 'ACTIVE')
      .sort(
        (a, b) =>
          SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity] ||
          a.raised_at.localeCompare(b.raised_at),
      ),
  );

  readonly counts = computed(() => {
    const active = this.active();
    return {
      critical: active.filter((alert) => alert.severity === 'CRITICAL').length,
      warning: active.filter((alert) => alert.severity === 'WARNING').length,
    };
  });

  async refresh(): Promise<void> {
    try {
      const [devices, alerts] = await Promise.all([
        firstValueFrom(this.api.devices()),
        firstValueFrom(this.api.alerts({ state: 'ACTIVE' })),
      ]);
      this.devices.set(new Map(devices.map((view) => [view.device.id, view])));
      this.alerts.set(alerts);
      this.error.set(null);
    } catch (error) {
      this.error.set(problemText(error));
    } finally {
      this.loaded.set(true);
    }
  }

  apply(message: LiveMessage): void {
    switch (message.type) {
      case 'reading':
        this.patch(message.device_id, (view) => ({
          ...view,
          health: message.health,
          last_reading: message.reading,
        }));
        break;
      case 'alert_raised':
        this.alerts.update((alerts) => [
          ...alerts.filter((a) => a.id !== message.alert.id),
          message.alert,
        ]);
        this.patch(message.alert.device_id, (view) => ({
          ...view,
          active_alerts: [...view.active_alerts, message.alert],
        }));
        this.arrived.set(message.alert);
        break;
      case 'alert_resolved':
        this.alerts.update((alerts) => alerts.filter((a) => a.id !== message.alert.id));
        this.patch(message.alert.device_id, (view) => ({
          ...view,
          active_alerts: view.active_alerts.filter((a) => a.id !== message.alert.id),
        }));
        break;
      default:
        break;
    }
  }

  deviceName(id: string): string {
    return this.devices().get(id)?.device.name ?? id;
  }

  private patch(id: string, change: (view: DeviceOverview) => DeviceOverview): void {
    const view = this.devices().get(id);
    if (!view) return;
    const next = new Map(this.devices());
    next.set(id, change(view));
    this.devices.set(next);
  }
}
