import { HttpClient, HttpErrorResponse, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import {
  Alert,
  AlertState,
  Command,
  CommandKind,
  DeviceOverview,
  Explanation,
  Problem,
  Reading,
  Session,
} from './models';

const BASE = '/api/v1';

/** The platform's HTTP API. Same origin: the dev server and nginx proxy /api to the backend. */
@Injectable({ providedIn: 'root' })
export class Api {
  private readonly http = inject(HttpClient);

  signIn(username: string, password: string): Observable<Session> {
    return this.http.post<Session>(`${BASE}/auth/token`, { username, password });
  }

  devices(): Observable<DeviceOverview[]> {
    return this.http.get<DeviceOverview[]>(`${BASE}/devices`);
  }

  device(id: string): Observable<DeviceOverview> {
    return this.http.get<DeviceOverview>(`${BASE}/devices/${encodeURIComponent(id)}`);
  }

  readings(id: string, limit = 180): Observable<Reading[]> {
    const params = new HttpParams().set('limit', limit);
    return this.http.get<Reading[]>(`${BASE}/devices/${encodeURIComponent(id)}/readings`, {
      params,
    });
  }

  alerts(
    filter: { state?: AlertState; deviceId?: string; limit?: number } = {},
  ): Observable<Alert[]> {
    let params = new HttpParams().set('limit', filter.limit ?? 200);
    if (filter.state) params = params.set('state', filter.state);
    if (filter.deviceId) params = params.set('device_id', filter.deviceId);
    return this.http.get<Alert[]>(`${BASE}/alerts`, { params });
  }

  explanation(alertId: string): Observable<Explanation> {
    return this.http.get<Explanation>(`${BASE}/alerts/${encodeURIComponent(alertId)}/explanation`);
  }

  send(deviceId: string, kind: CommandKind): Observable<Command> {
    return this.http.post<Command>(`${BASE}/devices/${encodeURIComponent(deviceId)}/commands`, {
      kind,
    });
  }

  commands(filter: { deviceId?: string; limit?: number } = {}): Observable<Command[]> {
    let params = new HttpParams().set('limit', filter.limit ?? 200);
    if (filter.deviceId) params = params.set('device_id', filter.deviceId);
    return this.http.get<Command[]>(`${BASE}/commands`, { params });
  }
}

/** What to tell the operator when a call fails: the API's own words when it sent a problem. */
export function problemText(error: unknown): string {
  if (error instanceof HttpErrorResponse) {
    if (error.status === 0) return 'No hay conexión con el servidor de Kuntur.';
    const problem = error.error as Partial<Problem> | null;
    if (problem?.detail) return problem.detail;
    if (problem?.title) return problem.title;
  }
  return 'Algo falló al hablar con el servidor.';
}
