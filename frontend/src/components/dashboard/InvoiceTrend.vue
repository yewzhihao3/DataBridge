<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import type { AnalyticsPeriod } from '@/types/api'

const props = defineProps<{ periods: AnalyticsPeriod[]; currency: string }>()
const selected = ref<number | null>(null)
const container = ref<HTMLElement | null>(null)
const width = ref(920)
let observer: ResizeObserver | undefined
onMounted(() => {
  observer = new ResizeObserver(entries => { width.value = Math.max(280, entries[0].contentRect.width) })
  if (container.value) observer.observe(container.value)
})
onBeforeUnmount(() => observer?.disconnect())
const displayMoney = (value: string | null) => value === null ? 'No known value' : `${props.currency} ${Number(value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
const points = computed(() => {
  const values = props.periods.map(p => p.invoice_value === null ? null : Number(p.invoice_value))
  const known = values.filter((v): v is number => v !== null && Number.isFinite(v))
  const low = Math.min(0, ...known)
  const high = Math.max(0, ...known)
  const span = high - low || 1
  const y = (v: number) => 190 - ((v - low) / span) * 155
  const baseline = y(0)
  const step = (width.value - 105) / Math.max(1, values.length)
  return { baseline, high, low, bars: props.periods.map((period, i) => ({
    ...period, x: 80 + step * (i + 0.5), y: y(values[i] ?? 0),
    height: values[i] === null ? 0 : Math.max(2, Math.abs(y(values[i]!) - baseline)),
    width: Math.max(1, Math.min(42, step * 0.65)),
    value: values[i], showLabel: i % Math.max(1, Math.ceil(values.length / (width.value < 500 ? 3 : 7))) === 0,
  })) }
})
const compact = (n: number) => new Intl.NumberFormat(undefined, { notation: 'compact', maximumFractionDigits: 1 }).format(n)
const label = (period: string) => new Intl.DateTimeFormat('en-GB', { month: 'short', year: 'numeric', timeZone: 'UTC' }).format(new Date(`${period}-01T00:00:00Z`))
</script>

<template>
  <div ref="container" class="trend">
    <svg :viewBox="`0 0 ${width} 240`" role="img" aria-label="Monthly invoice value. Exact values and invoice counts are available in the table below.">
      <line x1="70" :x2="width - 15" y1="35" y2="35" class="grid" />
      <line x1="70" :x2="width - 15" y1="190" y2="190" class="grid" />
      <line x1="70" :x2="width - 15" :y1="points.baseline" :y2="points.baseline" class="baseline" />
      <text x="60" y="39" text-anchor="end">{{ compact(points.high) }}</text>
      <text x="60" y="194" text-anchor="end">{{ compact(points.low) }}</text>
      <g v-for="(bar, i) in points.bars" :key="bar.period">
        <rect v-if="bar.value !== null" :x="bar.x - bar.width / 2" :y="Math.min(bar.y, points.baseline)" :width="bar.width" :height="bar.height" rx="2"
          tabindex="0" role="img" :aria-label="`${label(bar.period)}: ${displayMoney(bar.invoice_value)}, ${bar.invoice_count} invoices`"
          @mouseenter="selected = i" @mouseleave="selected = null" @focus="selected = i" @blur="selected = null">
          <title>{{ label(bar.period) }}: {{ displayMoney(bar.invoice_value) }} · {{ bar.invoice_count }} invoices ({{ bar.invoices_with_total }} with totals)</title>
        </rect>
        <text v-if="bar.showLabel" :x="bar.x" y="221" text-anchor="middle">{{ label(bar.period) }}</text>
      </g>
    </svg>
    <p class="chart-caption" aria-live="polite">
      <template v-if="selected !== null && periods[selected]">{{ label(periods[selected].period) }} · {{ displayMoney(periods[selected].invoice_value) }} · {{ periods[selected].invoice_count }} invoices</template>
      <template v-else>Monthly values in {{ currency }} · Hover or focus a bar for invoice counts.</template>
    </p>
    <details>
      <summary>View monthly values</summary>
      <div class="table-scroll"><table>
        <thead><tr><th>Month</th><th>Invoices</th><th>With totals</th><th>Invoice value</th></tr></thead>
        <tbody><tr v-for="period in periods" :key="period.period"><td>{{ label(period.period) }}</td><td>{{ period.invoice_count }}</td><td>{{ period.invoices_with_total }}</td><td>{{ displayMoney(period.invoice_value) }}</td></tr></tbody>
      </table></div>
    </details>
  </div>
</template>

<style scoped>
svg { width: 100%; display: block; overflow: visible; }
svg text { fill: var(--text-secondary); font: 12px var(--font-sans); }
.grid { stroke: var(--border-subtle); stroke-dasharray: 3 5; }
.baseline { stroke: var(--border-medium); }
rect { fill: var(--accent-brand); opacity: .8; }
rect:hover, rect:focus { opacity: 1; outline: 2px solid var(--text-secondary); }
.chart-caption { min-height: 1.5em; font-size: .8rem; color: var(--text-secondary); margin: .25rem 0 1rem; }
summary { cursor: pointer; color: var(--text-secondary); font-size: .8rem; }
.table-scroll { overflow-x: auto; margin-top: 1rem; }
table { width: 100%; border-collapse: collapse; font-size: .8rem; }
th, td { text-align: left; padding: .65rem; border-bottom: 1px solid var(--border-subtle); }
th { color: var(--text-secondary); font-weight: 500; }
</style>
