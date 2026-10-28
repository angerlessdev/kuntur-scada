import { ChangeDetectionStrategy, Component, input } from '@angular/core';

import { Health, Severity } from '../core/models';

export type Level = 'critical' | 'warning' | 'unknown' | 'normal';

export function levelOfHealth(health: Health): Level {
  return { DOWN: 'critical', DEGRADED: 'warning', UNKNOWN: 'unknown', OK: 'normal' }[
    health
  ] as Level;
}

export function levelOfSeverity(severity: Severity): Level {
  return severity === 'CRITICAL' ? 'critical' : 'warning';
}

/**
 * The priority shape that goes with every abnormal state, so colour is never the only signal:
 * a diamond for critical, a triangle for warning, a dashed ring for "no data yet". Normal has no mark.
 * It is decorative for assistive technology: the word next to it carries the meaning.
 */
@Component({
  selector: 'kt-mark',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { '[attr.data-level]': 'level()', 'aria-hidden': 'true' },
  template: `
    @switch (level()) {
      @case ('critical') {
        <svg viewBox="0 0 16 16"><path d="M8 0.8 15.2 8 8 15.2 0.8 8z" /></svg>
      }
      @case ('warning') {
        <svg viewBox="0 0 16 16"><path d="M8 1.2 15.3 14.6H0.7z" /></svg>
      }
      @case ('unknown') {
        <svg viewBox="0 0 16 16"><circle cx="8" cy="8" r="6" /></svg>
      }
    }
  `,
  styles: `
    :host {
      display: inline-flex;
      flex: none;
      width: 1rem;
      height: 1rem;
    }
    :host([data-level='normal']) {
      display: none;
    }
    svg {
      width: 100%;
      height: 100%;
      overflow: visible;
    }
    :host([data-level='critical']) path {
      fill: var(--alarm-critical);
    }
    :host([data-level='warning']) path {
      fill: var(--alarm-warning);
      stroke: #5c4100;
      stroke-width: 1;
      stroke-linejoin: round;
    }
    circle {
      fill: none;
      stroke: var(--unknown);
      stroke-width: 2;
      stroke-dasharray: 3 2.2;
    }
  `,
})
export class PriorityMark {
  readonly level = input.required<Level>();
}
