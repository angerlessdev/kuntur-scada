import { TestBed } from '@angular/core/testing';

import { ANALOGS } from '../core/vocabulary';
import { AnalogBar, analogLevel } from './analog-bar';

const BATTERY_TEMPERATURE = ANALOGS.UPS[0];
const BATTERY_CHARGE = ANALOGS.UPS[1];

describe('analogLevel', () => {
  it('changes colour only where a backend rule raises, with that rule severity', () => {
    expect(analogLevel(BATTERY_TEMPERATURE, 38)).toBe('normal');
    expect(analogLevel(BATTERY_TEMPERATURE, 40)).toBe('warning');
    expect(analogLevel(BATTERY_CHARGE, 25)).toBe('normal');
    expect(analogLevel(BATTERY_CHARGE, 20)).toBe('critical');
    expect(analogLevel(BATTERY_CHARGE, null)).toBe('unknown');
  });

  it('never invents a limit for a metric no rule watches', () => {
    const load = ANALOGS.UPS[2];
    expect(load.rule).toBeUndefined();
    expect(analogLevel(load, 99)).toBe('normal');
  });
});

describe('AnalogBar', () => {
  it('shows the value with its unit and exposes it as a meter', () => {
    const fixture = TestBed.createComponent(AnalogBar);
    fixture.componentRef.setInput('spec', BATTERY_TEMPERATURE);
    fixture.componentRef.setInput('value', 41.2);
    fixture.detectChanges();
    const element = fixture.nativeElement as HTMLElement;
    expect(element.dataset['level']).toBe('warning');
    expect(element.textContent).toContain('41.2 °C');
    const meter = element.querySelector('[role="meter"]');
    expect(meter?.getAttribute('aria-valuetext')).toBe('41.2 °C');
    expect(element.querySelectorAll('.limit')).toHaveLength(1);
  });

  it('says there is no data instead of drawing a pointer', () => {
    const fixture = TestBed.createComponent(AnalogBar);
    fixture.componentRef.setInput('spec', BATTERY_TEMPERATURE);
    fixture.componentRef.setInput('value', null);
    fixture.detectChanges();
    const element = fixture.nativeElement as HTMLElement;
    expect(element.textContent).toContain('sin dato');
    expect(element.querySelector('.pointer')).toBeNull();
  });
});
