import { Injectable, signal } from '@angular/core';

import { LiveMessage } from './models';

export type LiveState = 'offline' | 'connecting' | 'live';

const UNAUTHENTICATED = 4401;
const MAX_BACKOFF_MS = 30_000;

/**
 * The live channel. The token goes in the first message, not the URL (URLs end up in logs). When the
 * connection drops it comes back on its own, waiting a little longer each time, up to 30 s.
 */
@Injectable({ providedIn: 'root' })
export class LiveChannel {
  readonly state = signal<LiveState>('offline');
  private socket: WebSocket | null = null;
  private token: string | null = null;
  private attempts = 0;
  private retry: ReturnType<typeof setTimeout> | null = null;
  private readonly listeners = new Set<(message: LiveMessage) => void>();
  private onRejected: (() => void) | null = null;

  connect(token: string, onRejected: () => void): void {
    this.token = token;
    this.onRejected = onRejected;
    this.open();
  }

  disconnect(): void {
    this.token = null;
    if (this.retry) clearTimeout(this.retry);
    this.retry = null;
    this.socket?.close(1000);
    this.socket = null;
    this.state.set('offline');
  }

  listen(listener: (message: LiveMessage) => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  private open(): void {
    if (!this.token) return;
    this.state.set('connecting');
    const scheme = location.protocol === 'https:' ? 'wss' : 'ws';
    const socket = new WebSocket(`${scheme}://${location.host}/api/v1/live`);
    this.socket = socket;
    socket.onopen = () => socket.send(JSON.stringify({ token: this.token }));
    socket.onmessage = (event: MessageEvent<string>) => {
      const message = JSON.parse(event.data) as LiveMessage;
      if (message.type === 'hello') {
        this.attempts = 0;
        this.state.set('live');
        return;
      }
      this.listeners.forEach((listener) => listener(message));
    };
    socket.onclose = (event: CloseEvent) => {
      if (this.socket !== socket) return; // an older socket closing after a reconnect
      this.socket = null;
      this.state.set('offline');
      if (event.code === UNAUTHENTICATED) {
        this.onRejected?.();
        return;
      }
      if (this.token) this.scheduleReconnect();
    };
  }

  private scheduleReconnect(): void {
    const delay = Math.min(MAX_BACKOFF_MS, 1000 * 2 ** this.attempts);
    this.attempts += 1;
    this.retry = setTimeout(() => this.open(), delay);
  }
}
