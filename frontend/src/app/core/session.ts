import { Injectable, computed, signal } from '@angular/core';

import { Session } from './models';

const KEY = 'kuntur.session';

/**
 * The signed-in user. Kept in sessionStorage: it survives a reload but not the closing of the tab,
 * which suits a shared control-room workstation. Storage can be unavailable; the app still works.
 */
@Injectable({ providedIn: 'root' })
export class SessionStore {
  readonly session = signal<Session | null>(restore());
  readonly token = computed(() => this.session()?.access_token ?? null);
  readonly username = computed(() => this.session()?.username ?? null);
  readonly isOperator = computed(() => this.session()?.role === 'OPERATOR');

  start(session: Session): void {
    try {
      sessionStorage.setItem(KEY, JSON.stringify(session));
    } catch {
      // private mode or blocked storage: the session simply ends with the tab
    }
    this.session.set(session);
  }

  end(): void {
    try {
      sessionStorage.removeItem(KEY);
    } catch {
      // nothing to clean
    }
    this.session.set(null);
  }
}

function restore(): Session | null {
  try {
    const raw = sessionStorage.getItem(KEY);
    if (!raw) return null;
    const session = JSON.parse(raw) as Session;
    return new Date(session.expires_at).getTime() > Date.now() ? session : null;
  } catch {
    return null;
  }
}
