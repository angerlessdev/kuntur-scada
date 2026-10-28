/** The API's DTOs, as the backend sends them (see backend/src/kuntur/adapters/api/schemas.py). */

export type Health = 'OK' | 'DEGRADED' | 'DOWN' | 'UNKNOWN';
export type DeviceKind = 'UPS' | 'BARRIER' | 'CAMERA';
export type Severity = 'WARNING' | 'CRITICAL';
export type AlertState = 'ACTIVE' | 'RESOLVED';
export type Role = 'VIEWER' | 'OPERATOR';
export type ReadingStatus = 'OK' | 'PARTIAL' | 'FAILED';
export type ClockName = 'CALENDAR' | 'MECHANICAL' | 'BATTERY';
export type CommandStatus = 'PENDING' | 'SUCCEEDED' | 'FAILED';
export type CommandKind =
  'UPS_BATTERY_TEST' | 'UPS_SILENCE_ALARM' | 'BARRIER_OPEN' | 'BARRIER_CLOSE' | 'CAMERA_REBOOT';
export type AlertCode =
  | 'DEVICE_UNREACHABLE'
  | 'UPS_ON_BATTERY'
  | 'UPS_BATTERY_LOW'
  | 'UPS_BATTERY_HOT'
  | 'BARRIER_IMPACT'
  | 'CAMERA_CLOCK_DRIFT';

export interface Device {
  id: string;
  name: string;
  kind: DeviceKind;
  site: string;
  installed_on: string;
  active: boolean;
}

export interface Reading {
  device_id: string;
  taken_at: string;
  status: ReadingStatus;
  metrics: Record<string, number>;
  cause: string | null;
  detail: string | null;
}

export interface Alert {
  id: string;
  device_id: string;
  code: AlertCode;
  severity: Severity;
  message: string;
  raised_at: string;
  state: AlertState;
  resolved_at: string | null;
}

export interface LifeClock {
  name: ClockName;
  consumed_pct: number;
  end_date: string | null;
}

export interface RemainingLife {
  replacement_date: string | null;
  governing: ClockName;
  overdue: boolean;
  clocks: LifeClock[];
}

export interface DeviceOverview {
  device: Device;
  health: Health;
  last_reading: Reading | null;
  active_alerts: Alert[];
  life: RemainingLife;
}

export interface Command {
  id: string;
  device_id: string;
  kind: CommandKind;
  requested_by: string;
  requested_at: string;
  status: CommandStatus;
  finished_at: string | null;
  detail: string | null;
}

export interface Explanation {
  alert_id: string;
  summary: string;
  likely_causes: string[];
  checks: string[];
  suggested_command: CommandKind | null;
  source: string;
  generated_at: string;
  fallback_reason: string | null;
}

export interface Session {
  access_token: string;
  token_type: 'bearer';
  expires_at: string;
  username: string;
  role: Role;
}

/** RFC 9457 problem details: every error the API returns. */
export interface Problem {
  type: string;
  title: string;
  status: number;
  detail?: string;
  instance: string;
}

export type LiveMessage =
  | { type: 'hello'; username: string; role: Role }
  | { type: 'reading'; device_id: string; kind: DeviceKind; health: Health; reading: Reading }
  | { type: 'alert_raised'; alert: Alert }
  | { type: 'alert_resolved'; alert: Alert }
  | { type: 'command_finished'; command: Command };
