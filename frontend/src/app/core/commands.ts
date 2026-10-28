import { Injectable, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { Api, problemText } from './api';
import { Command, CommandKind } from './models';

export type Outcome = { ok: true; command: Command } | { ok: false; message: string };

/** Sends commands and remembers the last outcome per device, for every panel that offers them. */
@Injectable({ providedIn: 'root' })
export class CommandSender {
  private readonly api = inject(Api);
  readonly sending = signal<string | null>(null);

  async send(deviceId: string, kind: CommandKind): Promise<Outcome> {
    this.sending.set(`${deviceId}:${kind}`);
    try {
      const command = await firstValueFrom(this.api.send(deviceId, kind));
      return command.status === 'SUCCEEDED'
        ? { ok: true, command }
        : { ok: false, message: command.detail ?? 'El equipo no confirmó la orden.' };
    } catch (error) {
      return { ok: false, message: problemText(error) };
    } finally {
      this.sending.set(null);
    }
  }
}
