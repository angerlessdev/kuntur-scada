import { METRIC } from './vocabulary';

const LOCALE = 'es-PE';
const time = new Intl.DateTimeFormat(LOCALE, {
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hourCycle: 'h23',
});
const dateTime = new Intl.DateTimeFormat(LOCALE, {
  day: 'numeric',
  month: 'short',
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23',
});
const monthYear = new Intl.DateTimeFormat(LOCALE, { month: 'short', year: 'numeric' });
const day = new Intl.DateTimeFormat(LOCALE, { day: 'numeric', month: 'long', year: 'numeric' });

export function clockTime(iso: string): string {
  return time.format(new Date(iso));
}

export function shortDateTime(iso: string): string {
  return dateTime.format(new Date(iso));
}

export function longDate(iso: string): string {
  return day.format(new Date(`${iso}T12:00:00`));
}

export function replacementMonth(iso: string): string {
  return monthYear.format(new Date(`${iso}T12:00:00`));
}

/** "hace 40 s", "hace 3 min", "hace 2 h", "hace 5 días": how fresh something is, at a glance. */
export function ago(iso: string, now: number = Date.now()): string {
  const seconds = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000));
  if (seconds < 5) return 'hace un instante';
  if (seconds < 60) return `hace ${seconds} s`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `hace ${minutes} min`;
  const hours = Math.round(minutes / 60);
  if (hours < 48) return `hace ${hours} h`;
  return `hace ${Math.round(hours / 24)} días`;
}

/** How long something lasted or has lasted: "45 s", "12 min", "3 h 20 min". */
export function duration(fromIso: string, toIso: string | null, now: number = Date.now()): string {
  const end = toIso ? new Date(toIso).getTime() : now;
  const seconds = Math.max(0, Math.round((end - new Date(fromIso).getTime()) / 1000));
  if (seconds < 60) return `${seconds} s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest ? `${hours} h ${rest} min` : `${hours} h`;
}

export function metricValue(metric: string, value: number): string {
  const spec = METRIC[metric];
  const digits = spec?.digits ?? 1;
  const number = value.toLocaleString(LOCALE, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
  return spec?.unit ? `${number} ${spec.unit}` : number;
}
