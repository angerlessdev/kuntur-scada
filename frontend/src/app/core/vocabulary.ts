/** The words an operator reads for every code the platform uses. One place, one name per thing. */
import { AlertCode, ClockName, CommandKind, DeviceKind, Health, Severity } from './models';

export const HEALTH: Record<Health, string> = {
  OK: 'Normal',
  DEGRADED: 'Degradado',
  DOWN: 'Sin comunicación',
  UNKNOWN: 'Sin datos aún',
};

export const KIND: Record<DeviceKind, string> = {
  UPS: 'UPS',
  BARRIER: 'Barrera',
  CAMERA: 'Cámara',
};

export const ALERT: Record<AlertCode, string> = {
  DEVICE_UNREACHABLE: 'Sin comunicación',
  UPS_ON_BATTERY: 'UPS en batería',
  UPS_BATTERY_LOW: 'Batería baja',
  UPS_BATTERY_HOT: 'Batería caliente',
  BARRIER_IMPACT: 'Impacto en la barrera',
  CAMERA_CLOCK_DRIFT: 'Reloj desfasado',
};

export const COMMAND: Record<CommandKind, string> = {
  UPS_BATTERY_TEST: 'Probar la batería',
  UPS_SILENCE_ALARM: 'Silenciar la alarma',
  BARRIER_OPEN: 'Abrir la barrera',
  BARRIER_CLOSE: 'Cerrar la barrera',
  CAMERA_REBOOT: 'Reiniciar la cámara',
};

export const COMMANDS_FOR: Record<DeviceKind, readonly CommandKind[]> = {
  UPS: ['UPS_BATTERY_TEST', 'UPS_SILENCE_ALARM'],
  BARRIER: ['BARRIER_OPEN', 'BARRIER_CLOSE'],
  CAMERA: ['CAMERA_REBOOT'],
};

export const CLOCK: Record<ClockName, string> = {
  CALENDAR: 'Antigüedad',
  MECHANICAL: 'Desgaste mecánico',
  BATTERY: 'Envejecimiento de la batería',
};

export const CAUSE: Record<string, string | undefined> = {
  TIMEOUT: 'No respondió a tiempo',
  CONNECTION_REFUSED: 'Conexión rechazada',
  UNREACHABLE: 'Sin ruta de red',
  CONNECTION_LOST: 'Conexión cortada',
  AUTH_FAILED: 'Credenciales rechazadas',
  PROTOCOL_ERROR: 'Respuesta fuera de protocolo',
  INVALID_DATA: 'Valores imposibles',
  DEVICE_FAULT: 'Falla del equipo',
  UNKNOWN: 'Falla sin clasificar',
};

export interface Metric {
  label: string;
  unit: string;
  digits: number;
}

export const METRIC: Record<string, Metric> = {
  load_pct: { label: 'Carga', unit: '%', digits: 0 },
  battery_charge_pct: { label: 'Batería', unit: '%', digits: 0 },
  battery_temp_c: { label: 'Temperatura de batería', unit: '°C', digits: 1 },
  autonomy_min: { label: 'Autonomía', unit: 'min', digits: 0 },
  input_voltage_v: { label: 'Tensión de entrada', unit: 'V', digits: 0 },
  output_voltage_v: { label: 'Tensión de salida', unit: 'V', digits: 0 },
  cycles_total: { label: 'Ciclos', unit: '', digits: 0 },
  impacts_total: { label: 'Impactos', unit: '', digits: 0 },
  motor_temp_c: { label: 'Temperatura del motor', unit: '°C', digits: 1 },
  clock_drift_s: { label: 'Desfase del reloj', unit: 's', digits: 1 },
  storage_free_pct: { label: 'Disco libre', unit: '%', digits: 0 },
  temperature_c: { label: 'Temperatura', unit: '°C', digits: 1 },
};

/**
 * A backend alert rule on one metric (domain/rules.py): the alert is raised past ``raise`` and clears
 * back past ``clear`` (hysteresis), with the rule's own severity.
 */
export interface RuleLimit {
  direction: 'above' | 'below';
  raise: number;
  clear: number;
  severity: Severity;
}

/**
 * Analog indicators: where a value lives and, only when a backend rule watches it, where it becomes
 * an alert. No limit is invented here: a bar changes colour exactly when the rule would raise.
 */
export interface Analog {
  metric: string;
  min: number;
  max: number;
  rule?: RuleLimit;
}

export const ANALOGS: Record<DeviceKind, readonly Analog[]> = {
  UPS: [
    {
      metric: 'battery_temp_c',
      min: 15,
      max: 55,
      rule: { direction: 'above', raise: 40, clear: 37, severity: 'WARNING' },
    },
    {
      metric: 'battery_charge_pct',
      min: 0,
      max: 100,
      rule: { direction: 'below', raise: 20, clear: 30, severity: 'CRITICAL' },
    },
    { metric: 'load_pct', min: 0, max: 100 },
  ],
  BARRIER: [{ metric: 'motor_temp_c', min: 0, max: 80 }],
  CAMERA: [
    {
      metric: 'clock_drift_s',
      min: 0,
      max: 600,
      rule: { direction: 'above', raise: 300, clear: 60, severity: 'WARNING' },
    },
  ],
};
