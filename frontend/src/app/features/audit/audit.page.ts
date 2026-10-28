import { ChangeDetectionStrategy, Component, DestroyRef, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { Api, problemText } from '../../core/api';
import { FleetStore } from '../../core/fleet';
import { shortDateTime } from '../../core/format';
import { LiveChannel } from '../../core/live';
import { Command } from '../../core/models';
import { COMMAND } from '../../core/vocabulary';

const STATUS = { SUCCEEDED: 'Cumplida', FAILED: 'Falló', PENDING: 'En curso' } as const;

@Component({
  selector: 'kt-audit-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink],
  template: `
    <header class="head">
      <h1>Auditoría de órdenes</h1>
      <p class="muted">
        Cada orden queda registrada antes de llegar al equipo, con su autor y cómo terminó.
      </p>
    </header>
    @if (error(); as message) {
      <p class="problem" role="alert">{{ message }}</p>
    }
    <div class="panel">
      @if (commands().length === 0) {
        <p class="muted empty">Nadie ha enviado órdenes todavía.</p>
      } @else {
        <table>
          <thead>
            <tr>
              <th scope="col">Pedida</th>
              <th scope="col">Equipo</th>
              <th scope="col">Orden</th>
              <th scope="col">Por</th>
              <th scope="col">Resultado</th>
            </tr>
          </thead>
          <tbody>
            @for (command of commands(); track command.id) {
              <tr [attr.data-status]="command.status">
                <td class="data">{{ time(command.requested_at) }}</td>
                <td>
                  <a [routerLink]="['/equipos', command.device_id]">{{
                    fleet.deviceName(command.device_id)
                  }}</a>
                </td>
                <td>{{ order(command) }}</td>
                <td>{{ command.requested_by }}</td>
                <td>
                  <strong>{{ status(command) }}</strong>
                  @if (command.detail) {
                    <span class="muted">: {{ command.detail }}</span>
                  }
                </td>
              </tr>
            }
          </tbody>
        </table>
      }
    </div>
  `,
  styles: `
    :host {
      display: grid;
      gap: var(--space-4);
    }
    .head {
      display: grid;
      gap: var(--space-1);
    }
    .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      overflow-x: auto;
    }
    .empty {
      padding: var(--space-4);
    }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: var(--step--1);
    }
    th {
      text-align: left;
      color: var(--ink-muted);
      font-weight: 600;
      border-bottom: 1px solid var(--line-strong);
      padding: var(--space-3) var(--space-4);
    }
    td {
      padding: var(--space-3) var(--space-4);
      border-bottom: 1px solid var(--line);
    }
    tr[data-status='FAILED'] strong {
      color: var(--alarm-critical);
    }
    .problem {
      color: var(--alarm-critical);
      font-weight: 600;
    }
  `,
})
export class AuditPage {
  private readonly api = inject(Api);
  protected readonly fleet = inject(FleetStore);
  protected readonly commands = signal<readonly Command[]>([]);
  protected readonly error = signal<string | null>(null);

  constructor() {
    const stop = inject(LiveChannel).listen((message) => {
      if (message.type === 'command_finished') {
        this.commands.update((list) => [
          message.command,
          ...list.filter((c) => c.id !== message.command.id),
        ]);
      }
    });
    inject(DestroyRef).onDestroy(stop);
    void this.load();
  }

  protected time(iso: string): string {
    return shortDateTime(iso);
  }

  protected order(command: Command): string {
    return COMMAND[command.kind];
  }

  protected status(command: Command): string {
    return STATUS[command.status];
  }

  private async load(): Promise<void> {
    try {
      this.commands.set(await firstValueFrom(this.api.commands({ limit: 200 })));
    } catch (error) {
      this.error.set(problemText(error));
    }
  }
}
