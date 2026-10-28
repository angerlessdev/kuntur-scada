import { DecimalPipe } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  computed,
  effect,
  inject,
  input,
  signal,
} from '@angular/core';
import { RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { Api, problemText } from '../../core/api';
import { FleetStore } from '../../core/fleet';
import { ago, clockTime, duration, longDate, metricValue, shortDateTime } from '../../core/format';
import { LiveChannel } from '../../core/live';
import { Alert, Command, DeviceOverview, Reading } from '../../core/models';
import { SessionStore } from '../../core/session';
import { Ticker } from '../../core/ticker';
import {
  ALERT,
  ANALOGS,
  CAUSE,
  CLOCK,
  COMMAND,
  COMMANDS_FOR,
  HEALTH,
  KIND,
  METRIC,
} from '../../core/vocabulary';
import { CommandButton } from '../../shared/command-button';
import { ExplanationPanel } from '../../shared/explanation-panel';
import { PriorityMark, levelOfHealth, levelOfSeverity } from '../../shared/priority-mark';
import { Limit, TrendChart } from '../../shared/trend-chart';

const HISTORY = 180;

@Component({
  selector: 'kt-device-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DecimalPipe, RouterLink, PriorityMark, TrendChart, ExplanationPanel, CommandButton],
  templateUrl: './device.page.html',
  styleUrl: './device.page.css',
})
export class DevicePage {
  private readonly api = inject(Api);
  private readonly fleet = inject(FleetStore);
  protected readonly session = inject(SessionStore);
  protected readonly ticker = inject(Ticker);

  readonly id = input.required<string>();

  protected readonly view = signal<DeviceOverview | null>(null);
  protected readonly readings = signal<readonly Reading[]>([]);
  protected readonly alerts = signal<readonly Alert[]>([]);
  protected readonly commands = signal<readonly Command[]>([]);
  protected readonly error = signal<string | null>(null);
  protected readonly metric = signal<string | null>(null);
  protected readonly explained = signal<string | null>(null);

  /** The live fleet's version of this device wins over the snapshot loaded with the page. */
  protected readonly current = computed(() => this.fleet.devices().get(this.id()) ?? this.view());
  protected readonly level = computed(() => levelOfHealth(this.current()?.health ?? 'UNKNOWN'));
  protected readonly metricNames = computed(() => {
    const names = new Set<string>();
    for (const reading of this.readings())
      Object.keys(reading.metrics).forEach((name) => names.add(name));
    return [...names].filter((name) => METRIC[name]);
  });
  protected readonly chosenMetric = computed(() => {
    const kind = this.current()?.device.kind;
    return (
      this.metric() ?? (kind ? ANALOGS[kind][0]?.metric : null) ?? this.metricNames()[0] ?? null
    );
  });
  protected readonly points = computed<[number, number | null][]>(() => {
    const metric = this.chosenMetric();
    if (!metric) return [];
    return this.readings().map((r) => [new Date(r.taken_at).getTime(), r.metrics[metric] ?? null]);
  });
  protected readonly limits = computed<Limit[]>(() => {
    const kind = this.current()?.device.kind;
    const spec = kind ? ANALOGS[kind].find((a) => a.metric === this.chosenMetric()) : undefined;
    if (!spec?.rule) return [];
    const level = spec.rule.severity === 'CRITICAL' ? 'critical' : 'warning';
    return [
      { value: spec.rule.raise, level },
      { value: spec.rule.clear, level: 'clear' },
    ];
  });
  protected readonly recent = computed(() => [...this.readings()].slice(-8).reverse());
  protected readonly active = computed(() => this.alerts().filter((a) => a.state === 'ACTIVE'));
  protected readonly resolved = computed(() =>
    this.alerts()
      .filter((a) => a.state === 'RESOLVED')
      .slice(0, 5),
  );
  protected readonly allowed = computed(() => {
    const view = this.current();
    return view && view.device.active ? COMMANDS_FOR[view.device.kind] : [];
  });

  protected readonly words = { ALERT, CAUSE, CLOCK, COMMAND, HEALTH, KIND, METRIC };
  protected readonly format = { ago, clockTime, duration, longDate, metricValue, shortDateTime };
  protected readonly severityLevel = levelOfSeverity;

  constructor() {
    const live = inject(LiveChannel);
    const stop = live.listen((message) => {
      if (message.type === 'reading' && message.device_id === this.id()) {
        this.readings.update((list) => [...list, message.reading].slice(-HISTORY));
      }
      if (
        (message.type === 'alert_raised' || message.type === 'alert_resolved') &&
        message.alert.device_id === this.id()
      ) {
        this.alerts.update((list) => [
          message.alert,
          ...list.filter((a) => a.id !== message.alert.id),
        ]);
      }
      if (message.type === 'command_finished' && message.command.device_id === this.id()) {
        this.commands.update((list) => [
          message.command,
          ...list.filter((c) => c.id !== message.command.id),
        ]);
      }
    });
    inject(DestroyRef).onDestroy(stop);
    effect(() => void this.load(this.id()));
  }

  protected toggleExplanation(alert: Alert): void {
    this.explained.update((id) => (id === alert.id ? null : alert.id));
  }

  protected async refreshCommands(): Promise<void> {
    this.commands.set(await firstValueFrom(this.api.commands({ deviceId: this.id(), limit: 10 })));
  }

  private async load(id: string): Promise<void> {
    this.error.set(null);
    this.metric.set(null);
    try {
      const [view, readings, alerts, commands] = await Promise.all([
        firstValueFrom(this.api.device(id)),
        firstValueFrom(this.api.readings(id, HISTORY)),
        firstValueFrom(this.api.alerts({ deviceId: id, limit: 30 })),
        firstValueFrom(this.api.commands({ deviceId: id, limit: 10 })),
      ]);
      this.view.set(view);
      this.readings.set(readings);
      this.alerts.set(alerts);
      this.commands.set(commands);
    } catch (error) {
      this.error.set(problemText(error));
    }
  }
}
