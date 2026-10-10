<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

export interface TrendDataPoint {
  period: string
  seriesA_count: number
  seriesA_value: string | null
  seriesB_count: number
  seriesB_value: string | null
  seriesC_count?: number
  seriesC_value?: string | null
  total_count?: number
}

const props = withDefaults(defineProps<{
  periods: TrendDataPoint[]
  seriesALabel: string
  seriesAColor?: string
  seriesBLabel: string
  seriesBColor?: string
  seriesCLabel?: string
  seriesCColor?: string
  currency: string
  emptyMessage?: string
  notice?: string
}>(), {
  seriesAColor: '#10b981',
  seriesBColor: '#f59e0b',
  seriesCColor: '#64748b',
  emptyMessage: 'No activity in this date range.',
  notice: '',
})

const selected = ref<number | null>(null)
const container = ref<HTMLElement | null>(null)
const width = ref(920)
let observer: ResizeObserver | undefined

onMounted(() => {
  observer = new ResizeObserver(entries => {
    if (entries[0]) {
      width.value = Math.max(280, entries[0].contentRect.width)
    }
  })
  if (container.value) observer.observe(container.value)
})

onBeforeUnmount(() => observer?.disconnect())

const displayMoney = (val: string | null) => {
  if (val === null || val === undefined) return 'No value'
  return `${props.currency} ${Number(val).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

const hasData = computed(() => {
  return props.periods.some(p => p.seriesA_value !== null || p.seriesB_value !== null || (p.seriesC_value !== null && p.seriesC_value !== undefined))
})

const chartPoints = computed(() => {
  const vals: number[] = []
  props.periods.forEach(p => {
    if (p.seriesA_value !== null) vals.push(Number(p.seriesA_value))
    if (p.seriesB_value !== null) vals.push(Number(p.seriesB_value))
    if (p.seriesC_value !== null && p.seriesC_value !== undefined) vals.push(Number(p.seriesC_value))
  })
  const known = vals.filter(v => Number.isFinite(v))
  const low = Math.min(0, ...known)
  const high = Math.max(0, ...known)
  const span = high - low || 1
  const y = (v: number) => 190 - ((v - low) / span) * 155
  const baseline = y(0)

  const leftMargin = 70
  const rightMargin = 20
  const chartWidth = Math.max(100, width.value - leftMargin - rightMargin)
  const count = Math.max(1, props.periods.length)
  const slotWidth = chartWidth / count

  const bars = props.periods.map((p, idx) => {
    const slotX = leftMargin + idx * slotWidth
    const hasC = Boolean(props.seriesCLabel && (p.seriesC_count || p.seriesC_value))
    const barCount = hasC ? 3 : 2
    const barWidth = Math.max(2, Math.min(22, (slotWidth * 0.75) / barCount))
    const gap = 3

    const totalGroupWidth = barCount * barWidth + (barCount - 1) * gap
    const startX = slotX + (slotWidth - totalGroupWidth) / 2

    const aVal = p.seriesA_value !== null ? Number(p.seriesA_value) : null
    const bVal = p.seriesB_value !== null ? Number(p.seriesB_value) : null
    const cVal = p.seriesC_value !== null && p.seriesC_value !== undefined ? Number(p.seriesC_value) : null

    const calcBar = (val: number | null, index: number) => {
      if (val === null) return null
      const barY = y(val)
      return {
        x: startX + index * (barWidth + gap),
        y: Math.min(barY, baseline),
        width: barWidth,
        height: Math.max(2, Math.abs(barY - baseline)),
        value: val,
      }
    }

    const showLabel = idx % Math.max(1, Math.ceil(props.periods.length / (width.value < 500 ? 3 : 7))) === 0

    return {
      period: p.period,
      slotX,
      slotCenterX: slotX + slotWidth / 2,
      showLabel,
      barA: calcBar(aVal, 0),
      barB: calcBar(bVal, 1),
      barC: hasC ? calcBar(cVal, 2) : null,
      raw: p,
    }
  })

  return { baseline, high, low, bars }
})

const compact = (n: number) => new Intl.NumberFormat(undefined, { notation: 'compact', maximumFractionDigits: 1 }).format(n)
const formatPeriod = (period: string) => {
  try {
    return new Intl.DateTimeFormat('en-GB', { month: 'short', year: 'numeric', timeZone: 'UTC' }).format(new Date(`${period}-01T00:00:00Z`))
  } catch {
    return period
  }
}
</script>

<template>
  <div ref="container" class="direction-trend">
    <div class="legend-bar">
      <div class="legend-item">
        <span class="dot" :style="{ backgroundColor: seriesAColor }"></span>
        <span class="label">{{ seriesALabel }}</span>
      </div>
      <div class="legend-item">
        <span class="dot" :style="{ backgroundColor: seriesBColor }"></span>
        <span class="label">{{ seriesBLabel }}</span>
      </div>
      <div v-if="seriesCLabel" class="legend-item">
        <span class="dot" :style="{ backgroundColor: seriesCColor }"></span>
        <span class="label">{{ seriesCLabel }}</span>
      </div>
    </div>

    <div v-if="hasData" class="chart-wrapper">
      <svg :viewBox="`0 0 ${width} 240`" role="img" :aria-label="`Monthly breakdown between ${seriesALabel} and ${seriesBLabel}`">
        <line x1="70" :x2="width - 20" y1="35" y2="35" class="grid-line" />
        <line x1="70" :x2="width - 20" y1="190" y2="190" class="grid-line" />
        <line x1="70" :x2="width - 20" :y1="chartPoints.baseline" :y2="chartPoints.baseline" class="baseline-line" />
        <text x="60" y="39" text-anchor="end">{{ compact(chartPoints.high) }}</text>
        <text x="60" y="194" text-anchor="end">{{ compact(chartPoints.low) }}</text>

        <g v-for="(group, i) in chartPoints.bars" :key="group.period">
          <!-- Hover zone for month -->
          <rect
            :x="group.slotX"
            y="25"
            :width="width / chartPoints.bars.length"
            height="175"
            class="hover-zone"
            :class="{ active: selected === i }"
            @mouseenter="selected = i"
            @mouseleave="selected = null"
            @focus="selected = i"
            @blur="selected = null"
            tabindex="0"
          >
            <title>
              {{ formatPeriod(group.period) }} | {{ seriesALabel }}: {{ displayMoney(group.raw.seriesA_value) }} ({{ group.raw.seriesA_count }}) | {{ seriesBLabel }}: {{ displayMoney(group.raw.seriesB_value) }} ({{ group.raw.seriesB_count }})
            </title>
          </rect>

          <!-- Bar A -->
          <rect
            v-if="group.barA"
            :x="group.barA.x"
            :y="group.barA.y"
            :width="group.barA.width"
            :height="group.barA.height"
            :fill="seriesAColor"
            rx="2"
            class="series-bar"
          />

          <!-- Bar B -->
          <rect
            v-if="group.barB"
            :x="group.barB.x"
            :y="group.barB.y"
            :width="group.barB.width"
            :height="group.barB.height"
            :fill="seriesBColor"
            rx="2"
            class="series-bar"
          />

          <!-- Bar C (Unclassified) -->
          <rect
            v-if="group.barC"
            :x="group.barC.x"
            :y="group.barC.y"
            :width="group.barC.width"
            :height="group.barC.height"
            :fill="seriesCColor"
            rx="2"
            class="series-bar"
          />

          <!-- X axis label -->
          <text v-if="group.showLabel" :x="group.slotCenterX" y="221" text-anchor="middle">
            {{ formatPeriod(group.period) }}
          </text>
        </g>
      </svg>

      <p class="chart-caption" aria-live="polite">
        <template v-if="selected !== null && periods[selected]">
          <strong>{{ formatPeriod(periods[selected].period) }}:</strong>
          <span class="caption-item" :style="{ color: seriesAColor }">{{ seriesALabel }}: {{ displayMoney(periods[selected].seriesA_value) }} ({{ periods[selected].seriesA_count }})</span>
          ·
          <span class="caption-item" :style="{ color: seriesBColor }">{{ seriesBLabel }}: {{ displayMoney(periods[selected].seriesB_value) }} ({{ periods[selected].seriesB_count }})</span>
          <template v-if="seriesCLabel && (periods[selected].seriesC_count || periods[selected].seriesC_value)">
            ·
            <span class="caption-item" :style="{ color: seriesCColor }">{{ seriesCLabel }}: {{ displayMoney(periods[selected].seriesC_value ?? null) }} ({{ periods[selected].seriesC_count ?? 0 }})</span>
          </template>
        </template>
        <template v-else>
          Monthly comparisons in {{ currency }}. Hover or focus a month column to inspect figures.
        </template>
      </p>

      <details class="monthly-details">
        <summary>View monthly breakdown table</summary>
        <div class="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Month</th>
                <th>{{ seriesALabel }}</th>
                <th>{{ seriesALabel }} Count</th>
                <th>{{ seriesBLabel }}</th>
                <th>{{ seriesBLabel }} Count</th>
                <th v-if="seriesCLabel">{{ seriesCLabel }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="p in periods" :key="p.period">
                <td>{{ formatPeriod(p.period) }}</td>
                <td :style="{ color: seriesAColor }">{{ displayMoney(p.seriesA_value) }}</td>
                <td>{{ p.seriesA_count }}</td>
                <td :style="{ color: seriesBColor }">{{ displayMoney(p.seriesB_value) }}</td>
                <td>{{ p.seriesB_count }}</td>
                <td v-if="seriesCLabel" :style="{ color: seriesCColor }">{{ displayMoney(p.seriesC_value ?? null) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </details>
    </div>
    <div v-else class="empty-chart">
      <p>{{ emptyMessage }}</p>
    </div>

    <p v-if="notice" class="chart-notice">{{ notice }}</p>
  </div>
</template>

<style scoped>
.direction-trend {
  width: 100%;
}
.legend-bar {
  display: flex;
  align-items: center;
  gap: 1.25rem;
  margin-bottom: 1rem;
  font-size: 0.8rem;
}
.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
  color: var(--text-secondary);
}
.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
}
svg {
  width: 100%;
  display: block;
  overflow: visible;
}
svg text {
  fill: var(--text-secondary);
  font: 11px var(--font-sans);
}
.grid-line {
  stroke: var(--border-subtle);
  stroke-dasharray: 3 5;
}
.baseline-line {
  stroke: var(--border-medium);
}
.series-bar {
  opacity: 0.85;
  transition: opacity 0.15s ease;
}
.hover-zone {
  fill: transparent;
  cursor: pointer;
}
.hover-zone:hover,
.hover-zone:focus {
  fill: var(--bg-subtle);
  opacity: 0.35;
  outline: none;
}
.hover-zone:hover ~ .series-bar,
.hover-zone:focus ~ .series-bar {
  opacity: 1;
}
.chart-caption {
  min-height: 1.5em;
  font-size: 0.8rem;
  color: var(--text-secondary);
  margin: 0.5rem 0 1rem;
}
.caption-item {
  font-weight: 500;
}
.monthly-details {
  margin-top: 0.75rem;
}
summary {
  cursor: pointer;
  color: var(--text-secondary);
  font-size: 0.8rem;
  user-select: none;
}
summary:hover {
  color: var(--text-primary);
}
.table-scroll {
  overflow-x: auto;
  margin-top: 0.75rem;
}
table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.78rem;
}
th, td {
  text-align: left;
  padding: 0.6rem 0.75rem;
  border-bottom: 1px solid var(--border-subtle);
}
th {
  color: var(--text-secondary);
  font-weight: 500;
  background: var(--bg-subtle);
}
.empty-chart {
  padding: 2.5rem 1rem;
  text-align: center;
  color: var(--text-muted);
  font-size: 0.85rem;
  background: var(--bg-card);
  border: 1px dashed var(--border-subtle);
  border-radius: 6px;
}
.chart-notice {
  font-size: 0.72rem;
  color: var(--text-muted);
  line-height: 1.5;
  margin-top: 0.75rem;
}
</style>
