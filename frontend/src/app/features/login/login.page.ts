import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { Api, problemText } from '../../core/api';
import { SessionStore } from '../../core/session';
import { Wordmark } from '../../shared/wordmark';

@Component({
  selector: 'kt-login-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, Wordmark],
  template: `
    <main class="login">
      <form class="card" (ngSubmit)="signIn()" #form="ngForm" aria-labelledby="login-title">
        <kt-wordmark />
        <h1 id="login-title">Ingresa a la sala de control</h1>
        <label>
          Usuario
          <input name="username" autocomplete="username" required [(ngModel)]="username" />
        </label>
        <label>
          Contraseña
          <input
            name="password"
            type="password"
            autocomplete="current-password"
            required
            [(ngModel)]="password"
          />
        </label>
        @if (error()) {
          <p class="error" role="alert">{{ error() }}</p>
        }
        <button class="button primary" type="submit" [disabled]="busy() || form.invalid">
          {{ busy() ? 'Ingresando…' : 'Ingresar' }}
        </button>
        <p class="hint muted">
          Un visitante solo puede mirar. Las órdenes a los equipos requieren una cuenta de operador.
        </p>
      </form>
    </main>
  `,
  styles: `
    .login {
      min-height: 100vh;
      display: grid;
      place-items: center;
      padding: var(--space-4);
    }
    .card {
      display: grid;
      gap: var(--space-4);
      width: min(24rem, 100%);
      padding: var(--space-6) var(--space-5);
      background: var(--panel);
      border: 1px solid var(--line);
      border-top: 4px solid var(--select);
    }
    label {
      display: grid;
      gap: var(--space-1);
      font-weight: 500;
    }
    input {
      min-height: 2.75rem;
      padding: 0 var(--space-3);
      border: 1px solid var(--line-strong);
      border-radius: var(--radius-control);
      background: var(--panel-raised);
    }
    .error {
      color: var(--alarm-critical);
      font-weight: 600;
    }
    .hint {
      font-size: var(--step--1);
    }
  `,
})
export class LoginPage {
  private readonly api = inject(Api);
  private readonly session = inject(SessionStore);
  private readonly router = inject(Router);

  protected username = '';
  protected password = '';
  protected readonly busy = signal(false);
  protected readonly error = signal<string | null>(null);

  protected async signIn(): Promise<void> {
    this.busy.set(true);
    this.error.set(null);
    try {
      this.session.start(await firstValueFrom(this.api.signIn(this.username, this.password)));
      await this.router.navigate(['/flota']);
    } catch (error) {
      this.error.set(problemText(error));
      this.password = '';
    } finally {
      this.busy.set(false);
    }
  }
}
