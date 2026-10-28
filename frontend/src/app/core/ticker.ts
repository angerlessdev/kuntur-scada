import { Injectable, signal } from '@angular/core';

/** The current time, once a second: what keeps "hace 3 s" honest on every screen. */
@Injectable({ providedIn: 'root' })
export class Ticker {
  readonly now = signal(Date.now());

  constructor() {
    setInterval(() => this.now.set(Date.now()), 1000);
  }
}
