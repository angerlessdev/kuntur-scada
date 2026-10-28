import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';

import { FleetStore } from '../../core/fleet';
import { Ticker } from '../../core/ticker';
import { DeviceTile } from './device-tile';

@Component({
  selector: 'kt-fleet-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DeviceTile],
  template: `
    <header class="head">
      <h1>Flota</h1>
      @if (store.loaded()) {
        <p class="muted">{{ summary() }}</p>
      }
    </header>
    @if (store.error(); as error) {
      <p class="problem" role="alert">{{ error }}</p>
    }
    @if (!store.loaded()) {
      <p class="muted">Leyendo la flota…</p>
    } @else if (store.sites().length === 0) {
      <p class="muted">No hay equipos declarados. Agrega los equipos en config/fleet.json.</p>
    }
    @for (site of store.sites(); track site.name) {
      <section [attr.aria-label]="site.name">
        <h2>{{ site.name }}</h2>
        <div class="grid">
          @for (view of site.devices; track view.device.id) {
            <kt-device-tile [view]="view" [now]="ticker.now()" />
          }
        </div>
      </section>
    }
  `,
  styles: `
    :host {
      display: grid;
      gap: var(--space-5);
    }
    .head {
      display: flex;
      flex-wrap: wrap;
      align-items: baseline;
      gap: var(--space-2) var(--space-4);
    }
    section {
      display: grid;
      gap: var(--space-3);
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(15.5rem, 1fr));
      gap: var(--space-3);
    }
    .problem {
      color: var(--alarm-critical);
      font-weight: 600;
    }
  `,
})
export class FleetPage {
  protected readonly store = inject(FleetStore);
  protected readonly ticker = inject(Ticker);

  protected readonly summary = computed(() => {
    const views = [...this.store.devices().values()];
    const abnormal = views.filter((view) => view.health !== 'OK').length;
    const sites = this.store.sites().length;
    const fleet = `${views.length} equipos en ${sites} ${sites === 1 ? 'estación' : 'estaciones'}`;
    return abnormal ? `${fleet}; ${abnormal} fuera de lo normal` : `${fleet}, todos normales`;
  });
}
