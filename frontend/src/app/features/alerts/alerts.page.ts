import {
  ChangeDetectionStrategy,
  Component,
  computed,
  effect,
  inject,
  signal,
} from '@angular/core';
import { RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { Api, problemText } from '../../core/api';
import { FleetStore } from '../../core/fleet';
import { duration, shortDateTime } from '../../core/format';
import { Alert } from '../../core/models';
import { Ticker } from '../../core/ticker';
import { ALERT } from '../../core/vocabulary';
import { ExplanationPanel } from '../../shared/explanation-panel';
import { PriorityMark, levelOfSeverity } from '../../shared/priority-mark';

type View = 'active' | 'history';

@Component({
  selector: 'kt-alerts-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, PriorityMark, ExplanationPanel],
  template: `
    <header class="head">
      <h1>Alertas</h1>
      <div class="tabs" role="tablist" aria-label="Qué alertas ver">
        <button
          role="tab"
          type="button"
          [attr.aria-selected]="view() === 'active'"
          (click)="show('active')"
        >
          Activas ({{ fleet.active().length }})
        </button>
        <button
          role="tab"
          type="button"
          [attr.aria-selected]="view() === 'history'"
          (click)="show('history')"
        >
          Historial
        </button>
      </div>
    </header>
    @if (error(); as message) {
      <p class="problem" role="alert">{{ message }}</p>
    }
    <div class="layout">
      <div class="list" role="tabpanel">
        @if (shown().length === 0) {
          <p class="muted empty">
            {{
              view() === 'active'
                ? 'Sin alertas activas: toda la flota está en lo normal.'
                : 'Todavía no hay alertas resueltas.'
            }}
          </p>
        }
        <ul>
          @for (alert of shown(); track alert.id) {
            <li>
              <button
                type="button"
                class="row"
                [class.selected]="alert.id === selected()?.id"
                (click)="selectedId.set(alert.id)"
              >
                <kt-mark [level]="severityLevel(alert.severity)" />
                <span class="what">
                  <strong>{{ name(alert) }}</strong>
                  <span>{{ fleet.deviceName(alert.device_id) }}</span>
                </span>
                <span class="when data muted">
                  {{ when(alert) }}
                  <span>{{ alert.state === 'ACTIVE' ? 'lleva' : 'duró' }} {{ lasted(alert) }}</span>
                </span>
              </button>
            </li>
          }
        </ul>
      </div>
      <aside class="detail" aria-live="polite">
        @if (selected(); as alert) {
          <p class="message muted">{{ alert.message }}</p>
          <kt-explanation [alert]="alert" [deviceName]="fleet.deviceName(alert.device_id)" />
          <a [routerLink]="['/equipos', alert.device_id]">Ver el equipo</a>
        } @else {
          <p class="muted">Elige una alerta para ver qué pasa y qué revisar.</p>
        }
      </aside>
    </div>
  `,
  styles: `
    :host {
      display: grid;
      gap: var(--space-4);
    }
    .head {
      display: flex;
      flex-wrap: wrap;
      justify-content: space-between;
      align-items: center;
      gap: var(--space-3);
    }
    .tabs {
      display: flex;
      border: 1px solid var(--line-strong);
      border-radius: var(--radius-control);
    }
    .tabs button {
      min-height: 2.5rem;
      padding: 0 var(--space-4);
      border: 0;
      background: var(--panel-raised);
      cursor: pointer;
    }
    .tabs button[aria-selected='true'] {
      background: var(--select);
      color: #fff;
    }
    .layout {
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(0, 1.2fr);
      gap: var(--space-4);
      align-items: start;
    }
    @media (max-width: 60rem) {
      .layout {
        grid-template-columns: minmax(0, 1fr);
      }
    }
    .list,
    .detail {
      background: var(--panel);
      border: 1px solid var(--line);
    }
    .detail {
      display: grid;
      gap: var(--space-3);
      padding: var(--space-4);
      position: sticky;
      top: var(--space-4);
    }
    ul {
      list-style: none;
      margin: 0;
      padding: 0;
    }
    li + li {
      border-top: 1px solid var(--line);
    }
    .row {
      display: grid;
      grid-template-columns: auto 1fr auto;
      align-items: center;
      gap: var(--space-3);
      width: 100%;
      padding: var(--space-3) var(--space-4);
      border: 0;
      background: transparent;
      text-align: left;
      cursor: pointer;
    }
    .row.selected {
      background: var(--select-wash);
      box-shadow: inset 4px 0 0 var(--select);
    }
    .what,
    .when {
      display: grid;
    }
    .when {
      text-align: right;
      font-size: var(--step--1);
    }
    .empty {
      padding: var(--space-4);
    }
    .message {
      font-size: var(--step--1);
    }
    .problem {
      color: var(--alarm-critical);
      font-weight: 600;
    }
  `,
})
export class AlertsPage {
  private readonly api = inject(Api);
  protected readonly fleet = inject(FleetStore);
  private readonly ticker = inject(Ticker);

  protected readonly view = signal<View>('active');
  protected readonly history = signal<readonly Alert[]>([]);
  protected readonly selectedId = signal<string | null>(null);
  protected readonly error = signal<string | null>(null);

  protected readonly shown = computed(() =>
    this.view() === 'active' ? this.fleet.active() : this.history(),
  );
  protected readonly selected = computed<Alert | null>(() => {
    const id = this.selectedId();
    return this.shown().find((alert) => alert.id === id) ?? this.shown()[0] ?? null;
  });
  protected readonly severityLevel = levelOfSeverity;

  constructor() {
    effect(() => {
      if (this.view() === 'history') void this.loadHistory();
    });
  }

  protected show(view: View): void {
    this.view.set(view);
    this.selectedId.set(null);
  }

  protected name(alert: Alert): string {
    return ALERT[alert.code];
  }

  protected when(alert: Alert): string {
    return shortDateTime(alert.raised_at);
  }

  protected lasted(alert: Alert): string {
    return duration(alert.raised_at, alert.resolved_at, this.ticker.now());
  }

  private async loadHistory(): Promise<void> {
    try {
      this.history.set(await firstValueFrom(this.api.alerts({ state: 'RESOLVED', limit: 200 })));
      this.error.set(null);
    } catch (error) {
      this.error.set(problemText(error));
    }
  }
}
