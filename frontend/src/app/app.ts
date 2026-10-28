import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  computed,
  effect,
  inject,
  signal,
} from '@angular/core';
import { Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

import { FleetStore } from './core/fleet';
import { ago } from './core/format';
import { LiveChannel } from './core/live';
import { SessionStore } from './core/session';
import { Ticker } from './core/ticker';
import { ALERT } from './core/vocabulary';
import { PriorityMark } from './shared/priority-mark';
import { Wordmark } from './shared/wordmark';

const REFRESH_MS = 60_000;

@Component({
  selector: 'app-root',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterOutlet, RouterLink, RouterLinkActive, PriorityMark, Wordmark],
  templateUrl: './app.html',
  styleUrl: './app.css',
})
export class App {
  protected readonly session = inject(SessionStore);
  protected readonly fleet = inject(FleetStore);
  protected readonly live = inject(LiveChannel);
  private readonly ticker = inject(Ticker);
  private readonly router = inject(Router);

  /** True for a moment when a new alarm arrives: the banner pulses once, then stays still. */
  protected readonly pulse = signal(false);

  protected readonly latest = computed(() => {
    const active = this.fleet.active();
    const newest = [...active].sort((a, b) => b.raised_at.localeCompare(a.raised_at))[0];
    if (!newest) return null;
    return `${ALERT[newest.code]} en ${this.fleet.deviceName(newest.device_id)}, ${ago(newest.raised_at, this.ticker.now())}`;
  });

  protected readonly liveText = computed(
    () =>
      ({
        live: 'En vivo',
        connecting: 'Conectando…',
        offline: 'Sin conexión en vivo; reintentando',
      })[this.live.state()],
  );

  constructor() {
    const destroyRef = inject(DestroyRef);
    destroyRef.onDestroy(this.live.listen((message) => this.fleet.apply(message)));

    effect(() => {
      const token = this.session.token();
      if (!token) {
        this.live.disconnect();
        return;
      }
      void this.fleet.refresh();
      this.live.connect(token, () => this.signOut());
    });

    let pulseTimer: ReturnType<typeof setTimeout> | undefined;
    effect(() => {
      if (!this.fleet.arrived()) return;
      this.pulse.set(true);
      clearTimeout(pulseTimer);
      pulseTimer = setTimeout(() => this.pulse.set(false), 1600);
    });

    const refresh = setInterval(() => {
      if (this.session.token()) void this.fleet.refresh();
    }, REFRESH_MS);
    destroyRef.onDestroy(() => clearInterval(refresh));
  }

  protected signOut(): void {
    this.session.end();
    void this.router.navigate(['/ingresar']);
  }
}
