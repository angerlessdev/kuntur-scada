import { ChangeDetectionStrategy, Component } from '@angular/core';

/** The condor's wing over the name: kuntur is "condor" in Quechua. */
@Component({
  selector: 'kt-wordmark',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <svg viewBox="0 0 48 24" aria-hidden="true">
      <path d="M1 15c7-1 12-6 16-13l5 6 5-6c4 7 9 12 16 13-7 2-12 1-16-3l-5 7-5-7c-4 4-9 5-16 3z" />
    </svg>
    <span class="name">Kuntur</span>
    <span class="product">SCADA</span>
  `,
  styles: `
    :host {
      display: inline-flex;
      align-items: center;
      gap: var(--space-2);
      color: var(--ink);
    }
    svg {
      width: 2.5rem;
      height: 1.25rem;
      fill: var(--select);
    }
    .name {
      font-weight: 600;
      font-size: var(--step-1);
      letter-spacing: 0.01em;
    }
    .product {
      font-family: var(--font-data);
      font-size: var(--step--1);
      color: var(--ink-muted);
      padding-top: 0.2rem;
    }
  `,
})
export class Wordmark {}
