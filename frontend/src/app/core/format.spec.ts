import { ago, duration, metricValue } from './format';

const NOW = new Date('2026-01-15T13:00:00Z').getTime();

describe('ago', () => {
  it('reads "just now" for the freshest readings, then seconds, minutes, hours and days', () => {
    expect(ago('2026-01-15T12:59:58Z', NOW)).toBe('hace un instante');
    expect(ago('2026-01-15T12:59:20Z', NOW)).toBe('hace 40 s');
    expect(ago('2026-01-15T12:57:00Z', NOW)).toBe('hace 3 min');
    expect(ago('2026-01-15T11:00:00Z', NOW)).toBe('hace 2 h');
    expect(ago('2026-01-10T13:00:00Z', NOW)).toBe('hace 5 días');
  });

  it('never goes negative when the device clock runs ahead', () => {
    expect(ago('2026-01-15T13:00:30Z', NOW)).toBe('hace un instante');
  });
});

describe('duration', () => {
  it('measures until now for active alerts and until the end for resolved ones', () => {
    expect(duration('2026-01-15T12:59:15Z', null, NOW)).toBe('45 s');
    expect(duration('2026-01-15T12:48:00Z', null, NOW)).toBe('12 min');
    expect(duration('2026-01-15T09:40:00Z', '2026-01-15T13:00:00Z')).toBe('3 h 20 min');
    expect(duration('2026-01-15T10:00:00Z', '2026-01-15T12:00:00Z')).toBe('2 h');
  });
});

describe('metricValue', () => {
  it('uses the metric unit and its decimals', () => {
    expect(metricValue('battery_temp_c', 36.14)).toBe('36.1 °C');
    expect(metricValue('battery_charge_pct', 87.6)).toBe('88 %');
    expect(metricValue('cycles_total', 1650109)).toBe('1,650,109');
  });

  it('falls back to one decimal for metrics it does not know', () => {
    expect(metricValue('desconocida', 2.345)).toBe('2.3');
  });
});
