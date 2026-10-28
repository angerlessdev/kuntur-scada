import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  input,
  output,
  signal,
} from '@angular/core';

import { CommandSender, Outcome } from '../core/commands';
import { CommandKind } from '../core/models';
import { COMMAND } from '../core/vocabulary';

type Step = 'idle' | 'confirm' | 'sending';

/**
 * One command, confirmed before it leaves: field equipment moves, so a stray click must not.
 * The outcome stays on screen in the same words the audit log will use.
 */
@Component({
  selector: 'kt-command',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @switch (step()) {
      @case ('idle') {
        <button class="button" type="button" (click)="step.set('confirm')">{{ label() }}</button>
      }
      @case ('confirm') {
        <div class="confirm" role="group" [attr.aria-label]="'Confirmar: ' + label()">
          <p>{{ label() }} en {{ deviceName() }}. La orden queda registrada a tu nombre.</p>
          <div class="actions">
            <button class="button primary" type="button" (click)="send()">Enviar la orden</button>
            <button class="button" type="button" (click)="step.set('idle')">Cancelar</button>
          </div>
        </div>
      }
      @case ('sending') {
        <button class="button" type="button" disabled>Enviando…</button>
      }
    }
    @if (outcome(); as result) {
      <p class="outcome" [class.failed]="!result.ok" role="status">
        @if (result.ok) {
          Orden cumplida: {{ result.command.detail }}
        } @else {
          La orden falló: {{ result.message }}
        }
      </p>
    }
  `,
  styles: `
    :host {
      display: block;
    }
    .confirm {
      padding: var(--space-3);
      border: 1px solid var(--select);
      background: var(--select-wash);
    }
    .confirm p {
      margin-bottom: var(--space-2);
    }
    .actions {
      display: flex;
      flex-wrap: wrap;
      gap: var(--space-2);
    }
    .outcome {
      margin-top: var(--space-2);
      font-size: var(--step--1);
    }
    .outcome.failed {
      color: var(--alarm-critical);
      font-weight: 600;
    }
  `,
})
export class CommandButton {
  private readonly sender = inject(CommandSender);
  readonly deviceId = input.required<string>();
  readonly deviceName = input.required<string>();
  readonly kind = input.required<CommandKind>();
  readonly sent = output<Outcome>();

  protected readonly step = signal<Step>('idle');
  protected readonly outcome = signal<Outcome | null>(null);
  protected readonly label = computed(() => COMMAND[this.kind()]);

  protected async send(): Promise<void> {
    this.step.set('sending');
    const outcome = await this.sender.send(this.deviceId(), this.kind());
    this.outcome.set(outcome);
    this.step.set('idle');
    this.sent.emit(outcome);
  }
}
