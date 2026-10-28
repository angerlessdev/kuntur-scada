import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { RouterLink } from '@angular/router';

import { ago, replacementMonth } from '../../core/format';
import { DeviceOverview } from '../../core/models';
import { ALERT, ANALOGS, CLOCK, HEALTH, KIND } from '../../core/vocabulary';
import { AnalogBar } from '../../shared/analog-bar';
import { PriorityMark, levelOfHealth, levelOfSeverity } from '../../shared/priority-mark';

@Component({
  selector: 'kt-device-tile',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, PriorityMark, AnalogBar],
  template: `
    @let device = view().device;
    <a class="tile" [routerLink]="['/equipos', device.id]" [attr.data-level]="level()">
      <span class="title">
        <span class="name">{{ device.name }}</span>
        <span class="kind muted">{{ kind() }}</span>
      </span>
      <span class="state">
        <kt-mark [level]="level()" />
        <span class="health">{{ health() }}</span>
        @if (freshness(); as fresh) {
          <span class="data muted">{{ fresh }}</span>
        }
      </span>
      @for (alert of alertsBesideState(); track alert.id) {
        <span class="alert">
          <kt-mark [level]="severityLevel(alert.severity)" />
          {{ alertName(alert.code) }}
        </span>
      }
      @for (analog of analogs(); track analog.metric) {
        <kt-analog [spec]="analog" [value]="metric(analog.metric)" />
      }
      @if (device.kind === 'BARRIER') {
        <span class="counters data">
          <span
            >Ciclos <strong>{{ count('cycles_total') }}</strong></span
          >
          <span
            >Impactos <strong>{{ count('impacts_total') }}</strong></span
          >
        </span>
      }
      <span class="life" [class.overdue]="view().life.overdue">{{ life() }}</span>
    </a>
  `,
  styles: `
    .tile {
      display: flex;
      flex-direction: column;
      gap: var(--space-3);
      height: 100%;
      padding: var(--space-4);
      background: var(--panel);
      border: 1px solid var(--line);
      border-left: 6px solid var(--line);
      color: inherit;
      text-decoration: none;
    }
    .tile:hover {
      border-color: var(--line-strong);
    }
    .tile[data-level='warning'] {
      border-left-color: var(--alarm-warning);
    }
    .tile[data-level='critical'] {
      border-left-color: var(--alarm-critical);
    }
    .tile[data-level='unknown'] {
      border-left-style: dashed;
      border-left-color: var(--unknown);
    }
    .title {
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      gap: var(--space-2);
    }
    .name {
      font-weight: 600;
      font-size: var(--step-0);
    }
    .kind {
      font-size: var(--step--1);
    }
    .state,
    .alert {
      display: flex;
      align-items: center;
      gap: var(--space-2);
    }
    .state {
      flex-wrap: wrap;
    }
    .health {
      font-weight: 500;
      white-space: nowrap;
    }
    .state .data {
      margin-left: auto;
      font-size: var(--step--1);
      white-space: nowrap;
    }
    .alert {
      font-size: var(--step--1);
      font-weight: 600;
    }
    .counters {
      display: flex;
      gap: var(--space-4);
      font-size: var(--step--1);
      color: var(--ink-muted);
    }
    .counters strong {
      color: var(--ink);
    }
    .life {
      margin-top: auto;
      font-size: var(--step--1);
      color: var(--ink-muted);
      border-top: 1px solid var(--line);
      padding-top: var(--space-2);
    }
    .life.overdue {
      color: var(--alarm-critical);
      font-weight: 600;
    }
  `,
})
export class DeviceTile {
  readonly view = input.required<DeviceOverview>();
  readonly now = input.required<number>();

  protected readonly level = computed(() => levelOfHealth(this.view().health));
  protected readonly health = computed(() => HEALTH[this.view().health]);
  protected readonly kind = computed(() => KIND[this.view().device.kind]);
  protected readonly analogs = computed(() => ANALOGS[this.view().device.kind]);
  /** A lost device already says "Sin comunicación" as its state; the same alert would repeat it. */
  protected readonly alertsBesideState = computed(() =>
    this.view().active_alerts.filter(
      (alert) => !(alert.code === 'DEVICE_UNREACHABLE' && this.view().health === 'DOWN'),
    ),
  );
  protected readonly freshness = computed(() => {
    const reading = this.view().last_reading;
    return reading ? `leído ${ago(reading.taken_at, this.now())}` : null;
  });
  protected readonly life = computed(() => {
    const life = this.view().life;
    if (life.overdue) return `Reemplazo vencido por ${CLOCK[life.governing].toLowerCase()}`;
    if (!life.replacement_date) return 'Sin fecha de reemplazo previsible';
    return `Reemplazo en ${replacementMonth(life.replacement_date)}, por ${CLOCK[life.governing].toLowerCase()}`;
  });

  protected readonly severityLevel = levelOfSeverity;
  protected readonly alertName = (code: keyof typeof ALERT) => ALERT[code];

  protected metric(name: string): number | null {
    return this.view().last_reading?.metrics[name] ?? null;
  }

  protected count(name: string): string {
    const value = this.metric(name);
    return value === null ? 'sin dato' : value.toLocaleString('es-PE');
  }
}
