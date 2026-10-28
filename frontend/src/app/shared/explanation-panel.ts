import { ChangeDetectionStrategy, Component, effect, inject, input, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { Api, problemText } from '../core/api';
import { Alert, Explanation } from '../core/models';
import { SessionStore } from '../core/session';
import { ALERT } from '../core/vocabulary';
import { CommandButton } from './command-button';

/**
 * What is happening, why it probably is and what to check first. Written by Claude when it is
 * configured, by the deterministic template otherwise; the panel always says which one wrote it.
 */
@Component({
  selector: 'kt-explanation',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommandButton],
  template: `
    <h3>{{ title(alert()) }}</h3>
    @if (loading()) {
      <p class="muted">Preparando la explicación…</p>
    } @else if (error(); as message) {
      <p class="problem" role="alert">{{ message }}</p>
    } @else if (explanation(); as it) {
      <p class="summary">{{ it.summary }}</p>
      <h4>Causas probables, de la más probable a la menos</h4>
      <ol>
        @for (cause of it.likely_causes; track $index) {
          <li>{{ cause }}</li>
        }
      </ol>
      <h4>Qué revisar, en este orden</h4>
      <ol>
        @for (check of it.checks; track $index) {
          <li>{{ check }}</li>
        }
      </ol>
      @if (it.suggested_command && session.isOperator() && alert().state === 'ACTIVE') {
        <div class="suggestion">
          <p>Orden sugerida para este equipo:</p>
          <kt-command
            [deviceId]="alert().device_id"
            [deviceName]="deviceName()"
            [kind]="it.suggested_command"
          />
        </div>
      }
      <p class="source muted">
        {{ source(it) }}
        @if (it.fallback_reason) {
          (se usó la plantilla porque {{ it.fallback_reason }})
        }
      </p>
    }
  `,
  styles: `
    :host {
      display: grid;
      gap: var(--space-3);
      align-content: start;
    }
    .summary {
      font-size: var(--step-0);
      font-weight: 500;
      max-width: 62ch;
    }
    h4 {
      margin: 0;
      font-size: var(--step--1);
      font-weight: 600;
      color: var(--ink-muted);
    }
    ol {
      margin: 0;
      padding-left: 1.4rem;
      display: grid;
      gap: var(--space-1);
      max-width: 62ch;
    }
    .suggestion {
      display: grid;
      gap: var(--space-2);
      padding-top: var(--space-2);
      border-top: 1px solid var(--line);
    }
    .source {
      font-size: var(--step--1);
    }
    .problem {
      color: var(--alarm-critical);
    }
  `,
})
export class ExplanationPanel {
  private readonly api = inject(Api);
  protected readonly session = inject(SessionStore);
  readonly alert = input.required<Alert>();
  readonly deviceName = input.required<string>();

  protected readonly explanation = signal<Explanation | null>(null);
  protected readonly loading = signal(false);
  protected readonly error = signal<string | null>(null);

  constructor() {
    effect(() => {
      const alert = this.alert();
      void this.load(alert.id);
    });
  }

  protected title(alert: Alert): string {
    return `${ALERT[alert.code]} en ${this.deviceName()}`;
  }

  protected source(explanation: Explanation): string {
    return explanation.source.startsWith('claude:')
      ? `Explicación escrita por Claude (${explanation.source.slice('claude:'.length)}) con los datos del incidente.`
      : 'Explicación de la plantilla de Kuntur, escrita a partir de cómo falla cada equipo.';
  }

  private async load(alertId: string): Promise<void> {
    this.loading.set(true);
    this.error.set(null);
    try {
      const explanation = await firstValueFrom(this.api.explanation(alertId));
      if (this.alert().id === alertId) this.explanation.set(explanation);
    } catch (error) {
      this.error.set(problemText(error));
    } finally {
      this.loading.set(false);
    }
  }
}
