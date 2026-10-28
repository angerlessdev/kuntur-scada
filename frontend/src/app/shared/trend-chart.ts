import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  ElementRef,
  afterNextRender,
  effect,
  inject,
  input,
  viewChild,
} from '@angular/core';
import { LineChart } from 'echarts/charts';
import { GridComponent, MarkLineComponent, TooltipComponent } from 'echarts/components';
import * as echarts from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';

echarts.use([LineChart, GridComponent, TooltipComponent, MarkLineComponent, CanvasRenderer]);

const LIMIT_COLORS = {
  critical: '--alarm-critical',
  warning: '--alarm-warning',
  clear: '--line-strong',
} as const;

export interface Limit {
  value: number;
  level: 'warning' | 'critical' | 'clear';
}

/**
 * A trend in the high-performance HMI style: a dark grey line on a quiet grid, and the alarm limits as
 * the only colour. Gaps are kept where the device did not answer, instead of drawing a line across.
 */
@Component({
  selector: 'kt-trend',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<div #host class="chart" role="img" [attr.aria-label]="label()"></div>`,
  styles: `
    .chart {
      width: 100%;
      height: 16rem;
    }
  `,
})
export class TrendChart {
  readonly points = input.required<readonly [number, number | null][]>();
  readonly limits = input<readonly Limit[]>([]);
  readonly unit = input('');
  readonly label = input.required<string>();

  private readonly host = viewChild.required<ElementRef<HTMLDivElement>>('host');
  private chart: echarts.ECharts | null = null;

  constructor() {
    const destroyRef = inject(DestroyRef);
    afterNextRender(() => {
      const element = this.host().nativeElement;
      this.chart = echarts.init(element, undefined, { renderer: 'canvas' });
      const resize = new ResizeObserver(() => this.chart?.resize());
      resize.observe(element);
      destroyRef.onDestroy(() => {
        resize.disconnect();
        this.chart?.dispose();
      });
      this.render();
    });
    effect(() => this.render());
  }

  private render(): void {
    const points = this.points();
    const limits = this.limits();
    const unit = this.unit();
    if (!this.chart) return;
    const styles = getComputedStyle(this.host().nativeElement);
    const color = (name: string) => styles.getPropertyValue(name).trim();
    this.chart.setOption(
      {
        animation: false,
        grid: { left: 52, right: 16, top: 16, bottom: 28 },
        textStyle: { fontFamily: color('--font-data') || 'sans-serif' },
        tooltip: {
          trigger: 'axis',
          valueFormatter: (v: unknown) => (v === null ? 'sin dato' : `${v} ${unit}`),
        },
        xAxis: {
          type: 'time',
          axisLine: { lineStyle: { color: color('--line-strong') } },
          axisLabel: { color: color('--ink-muted') },
        },
        yAxis: {
          type: 'value',
          scale: true,
          // Keep every limit in view: a limit off the chart would hide how close the value is to it
          min: (axis: { min: number }) => Math.min(axis.min, ...limits.map((limit) => limit.value)),
          max: (axis: { max: number }) => Math.max(axis.max, ...limits.map((limit) => limit.value)),
          axisLabel: { color: color('--ink-muted'), formatter: `{value} ${unit}` },
          splitLine: { lineStyle: { color: color('--line') } },
        },
        series: [
          {
            type: 'line',
            showSymbol: false,
            connectNulls: false,
            lineStyle: { color: color('--ink'), width: 2 },
            data: points,
            markLine: {
              symbol: 'none',
              silent: true,
              label: { show: false },
              data: limits.map((limit) => ({
                yAxis: limit.value,
                lineStyle: {
                  type: 'dashed',
                  width: limit.level === 'clear' ? 1 : 2,
                  color: color(LIMIT_COLORS[limit.level]),
                },
              })),
            },
          },
        ],
      },
      { notMerge: true },
    );
  }
}
