import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

import { metricValue } from '../core/format';
import { Analog, METRIC } from '../core/vocabulary';
import { Level, levelOfSeverity } from './priority-mark';

function percent(spec: Analog, value: number): number {
  return Math.min(100, Math.max(0, ((value - spec.min) / (spec.max - spec.min)) * 100));
}

export function analogLevel(spec: Analog, value: number | null): Level {
  if (value === null) return 'unknown';
  const rule = spec.rule;
  if (!rule) return 'normal';
  const crossed = rule.direction === 'above' ? value >= rule.raise : value <= rule.raise;
  return crossed ? levelOfSeverity(rule.severity) : 'normal';
}

/**
 * A moving analog indicator: where the value sits between its limits, with the normal band shaded and
 * the alarm limit marked. An operator reads "how close to trouble" without parsing a number.
 */
@Component({
  selector: 'kt-analog',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { '[attr.data-level]': 'level()' },
  template: `
    <div class="head">
      <span>{{ label() }}</span>
      <span class="data value">{{ text() }}</span>
    </div>
    <div
      class="track"
      role="meter"
      [attr.aria-label]="label()"
      [attr.aria-valuemin]="spec().min"
      [attr.aria-valuemax]="spec().max"
      [attr.aria-valuenow]="value()"
      [attr.aria-valuetext]="text()"
    >
      <span class="band" [style.left.%]="band().left" [style.width.%]="band().width"></span>
      @for (limit of limits(); track limit) {
        <span class="limit" [style.left.%]="limit"></span>
      }
      @if (position() !== null) {
        <span class="pointer" [style.left.%]="position()"></span>
      }
    </div>
  `,
  styles: `
    :host {
      display: block;
    }
    .head {
      display: flex;
      justify-content: space-between;
      gap: var(--space-2);
      font-size: var(--step--1);
      color: var(--ink-muted);
    }
    .value {
      color: var(--ink);
      font-weight: 600;
    }
    :host([data-level='critical']) .value {
      color: var(--alarm-critical);
    }
    .track {
      position: relative;
      height: 0.6rem;
      margin-top: 0.2rem;
      background: var(--panel-raised);
      border: 1px solid var(--line);
    }
    .band {
      position: absolute;
      top: 0;
      bottom: 0;
      background: #c9ced3;
    }
    .limit {
      position: absolute;
      top: -3px;
      bottom: -3px;
      width: 2px;
      margin-left: -1px;
      background: var(--alarm-critical);
    }
    .pointer {
      position: absolute;
      top: -4px;
      bottom: -4px;
      width: 4px;
      margin-left: -2px;
      background: var(--ink);
    }
    :host([data-level='warning']) .pointer {
      background: var(--alarm-warning);
      outline: 1px solid #5c4100;
    }
    :host([data-level='critical']) .pointer {
      background: var(--alarm-critical);
    }
  `,
})
export class AnalogBar {
  readonly spec = input.required<Analog>();
  readonly value = input.required<number | null>();

  protected readonly label = computed(
    () => METRIC[this.spec().metric]?.label ?? this.spec().metric,
  );
  protected readonly level = computed(() => analogLevel(this.spec(), this.value()));
  protected readonly text = computed(() => {
    const value = this.value();
    return value === null ? 'sin dato' : metricValue(this.spec().metric, value);
  });
  protected readonly position = computed(() => {
    const value = this.value();
    return value === null ? null : percent(this.spec(), value);
  });
  /** The calm range: from the end of the scale to where the alert would clear. */
  protected readonly band = computed(() => {
    const spec = this.spec();
    const rule = spec.rule;
    const low = percent(spec, rule?.direction === 'below' ? rule.clear : spec.min);
    const high = percent(spec, rule?.direction === 'above' ? rule.clear : spec.max);
    return { left: low, width: Math.max(0, high - low) };
  });
  protected readonly limits = computed(() => {
    const spec = this.spec();
    return spec.rule ? [percent(spec, spec.rule.raise)] : [];
  });
}
