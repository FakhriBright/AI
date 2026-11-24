<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { getMarketCandles } from '../services/api'
import { formatPrice, formatDateTimeUtc } from '../utils/formatters'
import {
  LAYERS,
  STALE_AFTER_MS,
  chartStore,
  applyOverlayPayload,
  clearAiDrawings,
  highlightLatest,
  highlightedTimeframes,
  loadLayerPrefs,
  resetForSymbol,
  saveLayerPrefs,
  visibleOverlays,
} from '../utils/chartOverlays'

const props = defineProps({
  symbol: {
    type: String,
    default: 'EURUSDm',
  },
  keyLevels: {
    type: Object,
    default: () => ({}),
  },
  selectedScenario: {
    type: Object,
    default: null,
  },
  // Deterministic overlays from GET /analysis (chart_overlays); no extra request.
  overlayPayload: {
    type: Object,
    default: null,
  },
  generatedAt: {
    type: String,
    default: null,
  },
})

const OVERLAY_COLORS = {
  bullish: '#10b981',
  bearish: '#ef4444',
  neutral: '#94a3b8',
  info: '#3b82f6',
  warning: '#f59e0b',
  entry: '#3b82f6',
  stop: '#ef4444',
  target: '#10b981',
}
const FADED_STATUSES = new Set(['mitigated', 'taken', 'broken', 'expired', 'invalidated'])
const DASHED_STATUSES = new Set(['candidate', 'waiting', 'potential'])

const layerPrefs = ref(loadLayerPrefs())
const now = ref(Date.now())
let clockTimer = null

const isStale = computed(() => {
  const ts = Date.parse(chartStore.generatedAt || '')
  return Number.isFinite(ts) && now.value - ts > STALE_AFTER_MS
})
const offTimeframeHighlights = computed(() => highlightedTimeframes(activeTf.value))
const hasAiDrawings = computed(
  () => Object.keys(chartStore.annotations).length > 0 || chartStore.highlightIds.length > 0
)

function setAllLayers(on) {
  layerPrefs.value = {
    ...layerPrefs.value,
    layers: Object.fromEntries(LAYERS.map((l) => [l.id, on])),
  }
}

function handleHighlightLatest() {
  highlightLatest(activeTf.value)
}

const canvasRef = ref(null)
const chartContainerRef = ref(null)
const activeTf = ref('M5')
const timeframes = ['M1', 'M5', 'M15', 'M30', 'H1', 'H4', 'D1']

const candles = ref([])
const isLoading = ref(false)
const error = ref('')

const hoveredCandle = ref(null)
const mousePos = ref({ x: -1, y: -1 })

async function fetchCandles() {
  isLoading.value = true
  error.value = ''
  hoveredCandle.value = null

  try {
    const res = await getMarketCandles(props.symbol, activeTf.value, 80)
    if (res?.candles && Array.isArray(res.candles)) {
      candles.value = res.candles
    } else {
      candles.value = []
    }
  } catch (err) {
    error.value = err.message || 'Failed to fetch candles'
    candles.value = []
  } finally {
    isLoading.value = false
    renderChart()
  }
}

function handleTimeframeChange(tf) {
  if (activeTf.value === tf) return
  activeTf.value = tf
  fetchCandles()
}

watch(
  () => props.symbol,
  (symbol) => {
    // Never carry drawings of the previous symbol over.
    resetForSymbol(symbol)
    applyOverlayPayload(props.overlayPayload, symbol)
    fetchCandles()
  }
)

watch(
  () => props.overlayPayload,
  (payload) => {
    applyOverlayPayload(payload, props.symbol)
  }
)

// A new analysis snapshot means new closed candles: refresh the candles so
// overlays and candles describe the same data.
watch(
  () => props.generatedAt,
  (next, prev) => {
    if (next && prev && next !== prev) fetchCandles()
  }
)

watch(
  layerPrefs,
  (prefs) => {
    saveLayerPrefs(prefs)
    renderChart()
  },
  { deep: true }
)

watch(
  () => [chartStore.engine, chartStore.annotations, chartStore.highlightIds, isStale.value],
  () => {
    renderChart()
  }
)

watch(
  () => [props.keyLevels, props.selectedScenario],
  () => {
    renderChart()
  },
  { deep: true }
)

function renderChart() {
  const canvas = canvasRef.value
  if (!canvas) return
  const ctx = canvas.getContext('2d')
  if (!ctx) return

  const container = chartContainerRef.value
  const dpr = window.devicePixelRatio || 1
  const width = container ? container.clientWidth : 800
  const height = 440

  canvas.width = width * dpr
  canvas.height = height * dpr
  canvas.style.width = `${width}px`
  canvas.style.height = `${height}px`

  ctx.scale(dpr, dpr)

  const isDark = document.documentElement.getAttribute('data-theme') === 'dark'

  // Dynamic canvas surface background
  ctx.fillStyle = isDark ? '#131b2e' : '#ffffff'
  ctx.fillRect(0, 0, width, height)

  const candleList = candles.value
  if (!candleList || candleList.length === 0) {
    ctx.fillStyle = isDark ? '#94a3b8' : '#64748b'
    ctx.font = '13px sans-serif'
    ctx.textAlign = 'center'
    ctx.fillText(
      isLoading.value ? 'Loading market candles...' : (error.value || 'No candle data available'),
      width / 2,
      height / 2
    )
    return
  }

  const padding = { top: 25, bottom: 45, left: 10, right: 65 }
  const chartWidth = width - padding.left - padding.right
  const chartHeight = height - padding.top - padding.bottom

  // Min and Max prices
  let minPrice = Infinity
  let maxPrice = -Infinity
  let maxVol = 0

  for (const c of candleList) {
    if (c.low < minPrice) minPrice = c.low
    if (c.high > maxPrice) maxPrice = c.high
    if (c.tick_volume > maxVol) maxVol = c.tick_volume
  }

  const triggerRef = props.selectedScenario?.trigger_reference
  const invalidationRef = props.selectedScenario?.invalidation_reference
  if (triggerRef && Math.abs(triggerRef - minPrice) / (maxPrice - minPrice || 1) < 2) {
    minPrice = Math.min(minPrice, triggerRef)
    maxPrice = Math.max(maxPrice, triggerRef)
  }
  if (invalidationRef && Math.abs(invalidationRef - minPrice) / (maxPrice - minPrice || 1) < 2) {
    minPrice = Math.min(minPrice, invalidationRef)
    maxPrice = Math.max(maxPrice, invalidationRef)
  }

  const priceRange = maxPrice - minPrice || 1
  const priceMargin = priceRange * 0.08
  const chartMin = minPrice - priceMargin
  const chartMax = maxPrice + priceMargin
  const adjustedRange = chartMax - chartMin

  function getY(price) {
    return padding.top + chartHeight - ((price - chartMin) / adjustedRange) * chartHeight
  }

  // Horizontal Grid & Price Axis
  const gridSteps = 5
  ctx.lineWidth = 1
  ctx.strokeStyle = isDark ? 'rgba(255, 255, 255, 0.08)' : '#e2e8f0'
  ctx.fillStyle = isDark ? '#94a3b8' : '#475569'
  ctx.font = '10px monospace'
  ctx.textAlign = 'left'

  for (let i = 0; i <= gridSteps; i++) {
    const y = padding.top + (chartHeight / gridSteps) * i
    const priceVal = chartMax - (adjustedRange / gridSteps) * i

    ctx.beginPath()
    ctx.moveTo(padding.left, y)
    ctx.lineTo(width - padding.right, y)
    ctx.stroke()

    ctx.fillText(formatPrice(priceVal, props.symbol), width - padding.right + 8, y + 3)
  }

  // Draw Key Levels Overlay
  const supports = props.keyLevels?.supports || []
  const resistances = props.keyLevels?.resistances || []

  // Resistances (red lines)
  ctx.lineWidth = 1
  ctx.setLineDash([4, 4])
  ctx.strokeStyle = 'rgba(239, 68, 68, 0.45)'
  for (const r of resistances.slice(0, 3)) {
    const y = getY(r.price)
    if (y >= padding.top && y <= height - padding.bottom) {
      ctx.beginPath()
      ctx.moveTo(padding.left, y)
      ctx.lineTo(width - padding.right, y)
      ctx.stroke()
    }
  }

  // Supports (green lines)
  ctx.strokeStyle = 'rgba(16, 185, 129, 0.45)'
  for (const s of supports.slice(0, 3)) {
    const y = getY(s.price)
    if (y >= padding.top && y <= height - padding.bottom) {
      ctx.beginPath()
      ctx.moveTo(padding.left, y)
      ctx.lineTo(width - padding.right, y)
      ctx.stroke()
    }
  }

  // Scenario Trigger Line
  if (triggerRef) {
    const y = getY(triggerRef)
    if (y >= padding.top && y <= height - padding.bottom) {
      ctx.strokeStyle = '#0f766e'
      ctx.lineWidth = 1.5
      ctx.setLineDash([6, 3])
      ctx.beginPath()
      ctx.moveTo(padding.left, y)
      ctx.lineTo(width - padding.right, y)
      ctx.stroke()

      ctx.fillStyle = '#0f766e'
      ctx.fillText('TRIGGER', width - padding.right + 8, y - 4)
    }
  }

  // Scenario Invalidation Line
  if (invalidationRef) {
    const y = getY(invalidationRef)
    if (y >= padding.top && y <= height - padding.bottom) {
      ctx.strokeStyle = '#f59e0b'
      ctx.lineWidth = 1.5
      ctx.setLineDash([6, 3])
      ctx.beginPath()
      ctx.moveTo(padding.left, y)
      ctx.lineTo(width - padding.right, y)
      ctx.stroke()

      ctx.fillStyle = '#f59e0b'
      ctx.fillText('INVAL', width - padding.right + 8, y - 4)
    }
  }

  ctx.setLineDash([]) // reset

  // Candlesticks rendering
  const count = candleList.length
  const candleSpacing = chartWidth / count
  const candleWidth = Math.max(2, candleSpacing * 0.7)

  const geom = { ctx, width, height, padding, chartWidth, chartHeight, getY, chartMin, chartMax, candleList, candleSpacing, isDark }
  const overlays = visibleOverlays(activeTf.value, layerPrefs.value)
  drawOverlays(geom, overlays, 'under')

  for (let i = 0; i < count; i++) {
    const c = candleList[i]
    const x = padding.left + i * candleSpacing + candleSpacing / 2

    const openY = getY(c.open)
    const closeY = getY(c.close)
    const highY = getY(c.high)
    const lowY = getY(c.low)

    const isBullish = c.close >= c.open
    const color = isBullish ? '#10b981' : '#ef4444'

    // Volume bars at bottom
    if (maxVol > 0) {
      const volHeight = (c.tick_volume / maxVol) * 40
      ctx.fillStyle = isBullish ? 'rgba(16, 185, 129, 0.15)' : 'rgba(239, 68, 68, 0.15)'
      ctx.fillRect(x - candleWidth / 2, height - padding.bottom - volHeight, candleWidth, volHeight)
    }

    // High / Low Wick
    ctx.strokeStyle = color
    ctx.lineWidth = 1.2
    ctx.beginPath()
    ctx.moveTo(x, highY)
    ctx.lineTo(x, lowY)
    ctx.stroke()

    // Body
    ctx.fillStyle = color
    const bodyTop = Math.min(openY, closeY)
    const bodyHeight = Math.max(1.5, Math.abs(closeY - openY))
    ctx.fillRect(x - candleWidth / 2, bodyTop, candleWidth, bodyHeight)
  }

  drawOverlays(geom, overlays, 'over')

  // Crosshair
  if (mousePos.value.x >= padding.left && mousePos.value.x <= width - padding.right) {
    ctx.strokeStyle = 'rgba(148, 163, 184, 0.4)'
    ctx.setLineDash([2, 2])
    ctx.lineWidth = 1

    ctx.beginPath()
    ctx.moveTo(mousePos.value.x, padding.top)
    ctx.lineTo(mousePos.value.x, height - padding.bottom)
    ctx.stroke()

    if (mousePos.value.y >= padding.top && mousePos.value.y <= height - padding.bottom) {
      ctx.beginPath()
      ctx.moveTo(padding.left, mousePos.value.y)
      ctx.lineTo(width - padding.right, mousePos.value.y)
      ctx.stroke()

      const hoveredPrice = chartMin + ((height - padding.bottom - mousePos.value.y) / chartHeight) * adjustedRange
      ctx.fillStyle = isDark ? '#1c273e' : '#0f172a'
      ctx.fillRect(width - padding.right + 2, mousePos.value.y - 8, 60, 16)
      ctx.fillStyle = '#ffffff'
      ctx.font = '10px monospace'
      ctx.fillText(formatPrice(hoveredPrice, props.symbol), width - padding.right + 5, mousePos.value.y + 4)
    }

    ctx.setLineDash([])
  }
}

// ---------------------------------------------------------------------------
// Overlay drawing (engine objects + AI chat annotations)
// ---------------------------------------------------------------------------

function timeToX(geom, iso) {
  const t = Date.parse(iso || '')
  const { times, padding, candleSpacing } = geom
  if (!Number.isFinite(t) || !times.length) return null
  if (t < times[0]) return padding.left // older than the visible window: clamp to the left edge
  let lo = 0
  let hi = times.length - 1
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1
    if (times[mid] <= t) lo = mid
    else hi = mid - 1
  }
  return padding.left + lo * candleSpacing + candleSpacing / 2
}

function drawTag(ctx, text, x, y, color, align = 'right') {
  ctx.save()
  ctx.shadowBlur = 0
  ctx.setLineDash([])
  ctx.font = 'bold 9px monospace'
  const w = ctx.measureText(text).width + 8
  const left = align === 'right' ? x - w : x
  ctx.fillStyle = color
  ctx.globalAlpha = Math.min(1, ctx.globalAlpha + 0.1)
  ctx.fillRect(left, y - 7, w, 13)
  ctx.fillStyle = '#ffffff'
  ctx.textAlign = 'left'
  ctx.fillText(text, left + 4, y + 3)
  ctx.restore()
}

function drawArrowHead(ctx, x, fromY, toY) {
  const dir = toY > fromY ? 1 : -1
  ctx.beginPath()
  ctx.moveTo(x, toY)
  ctx.lineTo(x - 5, toY - dir * 8)
  ctx.lineTo(x + 5, toY - dir * 8)
  ctx.closePath()
  ctx.fill()
}

function drawOverlay(geom, o, { htf, highlighted }) {
  const { ctx, width, padding, chartWidth, getY } = geom
  const right = width - padding.right
  const color = OVERLAY_COLORS[o.color] || OVERLAY_COLORS.neutral
  const label = `${htf ? `${o.timeframe} · ` : ''}${o.name}`
  const fmt = (p) => formatPrice(p, props.symbol)

  switch (o.kind) {
    case 'zone': {
      const x1 = timeToX(geom, o.time_start) ?? padding.left
      const x2 = timeToX(geom, o.time_end) ?? right
      const yTop = getY(o.price_high)
      const yBottom = getY(o.price_low)
      const base = ctx.globalAlpha
      ctx.globalAlpha = base * (highlighted ? 0.28 : 0.12)
      ctx.fillRect(x1, yTop, Math.max(2, x2 - x1), yBottom - yTop)
      ctx.globalAlpha = base
      ctx.strokeRect(x1, yTop, Math.max(2, x2 - x1), yBottom - yTop)
      ctx.font = '9px monospace'
      ctx.textAlign = 'right'
      ctx.fillText(label, right - 4, yTop + 10)
      break
    }
    case 'hline': {
      const x1 = timeToX(geom, o.time_start) ?? padding.left
      const x2 = timeToX(geom, o.time_end) ?? right
      const y = getY(o.price)
      ctx.beginPath()
      ctx.moveTo(x1, y)
      ctx.lineTo(x2, y)
      ctx.stroke()
      if (highlighted || o.layer === 'trade_plan') {
        drawTag(ctx, `${label} ${fmt(o.price)}`, x2 - 2, y - 9, color)
      } else {
        ctx.font = '9px monospace'
        ctx.textAlign = 'right'
        ctx.fillText(label, x2 - 4, y - 3)
      }
      break
    }
    case 'trendline': {
      const [a, b] = o.points
      const x1 = timeToX(geom, a.time)
      const x2 = timeToX(geom, b.time)
      if (x1 === null || x2 === null || x2 <= x1) break
      const y1 = getY(a.price)
      const y2 = getY(b.price)
      let xe = x2
      let ye = y2
      if (o.extend) {
        xe = right
        ye = y2 + ((y2 - y1) / (x2 - x1)) * (xe - x2)
      }
      ctx.beginPath()
      ctx.moveTo(x1, y1)
      ctx.lineTo(xe, ye)
      ctx.stroke()
      ctx.font = '9px monospace'
      ctx.textAlign = 'left'
      ctx.fillText(label, x2 + 4, y2 - 4)
      break
    }
    case 'arrow': {
      const [a, b] = o.points
      const x = timeToX(geom, a.time) ?? right - 40
      const y1 = getY(a.price)
      const y2 = getY(b.price)
      ctx.setLineDash([4, 3])
      ctx.beginPath()
      ctx.moveTo(x, y1)
      ctx.lineTo(x, y2)
      ctx.stroke()
      ctx.setLineDash([])
      drawArrowHead(ctx, x, y1, y2)
      drawTag(ctx, label, x - 8, y2 + (y2 < y1 ? -10 : 10), color)
      break
    }
    case 'marker': {
      const x = timeToX(geom, o.time_start)
      if (x === null) break
      const y = getY(o.price)
      const up = o.position !== 'below'
      ctx.textAlign = 'center'
      ctx.font = highlighted ? 'bold 10px monospace' : '9px monospace'
      if (o.shape === 'circle') {
        ctx.beginPath()
        ctx.arc(x, y, 7, 0, Math.PI * 2)
        ctx.stroke()
        ctx.fillText(label, x, up ? y - 11 : y + 18)
      } else {
        const ty = up ? y - 4 : y + 4
        ctx.beginPath()
        ctx.moveTo(x, ty)
        ctx.lineTo(x - 3.5, ty + (up ? -6 : 6))
        ctx.lineTo(x + 3.5, ty + (up ? -6 : 6))
        ctx.closePath()
        ctx.fill()
        ctx.fillText(label, x, up ? y - 13 : y + 20)
      }
      break
    }
    case 'label': {
      const y = getY(o.price)
      drawTag(ctx, label, right - 4, y, color)
      const blocker = o.meta?.blockers?.[0]
      if (blocker) {
        ctx.font = '9px sans-serif'
        ctx.textAlign = 'right'
        ctx.fillText(blocker.length > 70 ? `${blocker.slice(0, 67)}…` : blocker, right - 4, y + 16)
      }
      break
    }
    case 'position': {
      // Only sent when the engine's entry gate allows it (validated setup).
      const x1 = right - Math.max(120, chartWidth * 0.28)
      const w = right - x1
      const yEntry = getY(o.entry)
      const yStop = getY(o.stop)
      const base = ctx.globalAlpha
      ctx.globalAlpha = base * 0.16
      ctx.fillStyle = OVERLAY_COLORS.stop
      ctx.fillRect(x1, Math.min(yEntry, yStop), w, Math.abs(yStop - yEntry))
      if (o.target) {
        const yTarget = getY(o.target)
        ctx.fillStyle = OVERLAY_COLORS.target
        ctx.fillRect(x1, Math.min(yEntry, yTarget), w, Math.abs(yTarget - yEntry))
      }
      ctx.globalAlpha = base
      const lines = [
        ['ENTRY', o.entry, OVERLAY_COLORS.entry],
        ['SL', o.stop, OVERLAY_COLORS.stop],
        ...(o.target ? [['TP', o.target, OVERLAY_COLORS.target]] : []),
      ]
      for (const [name, price, c] of lines) {
        const y = getY(price)
        ctx.strokeStyle = c
        ctx.beginPath()
        ctx.moveTo(x1, y)
        ctx.lineTo(right, y)
        ctx.stroke()
        drawTag(ctx, `${name} ${fmt(price)}`, x1 + 2, y - 8, c, 'left')
      }
      drawTag(ctx, `${label}${o.rr ? ` · RR ${o.rr}` : ''}`, right - 2, yEntry + 10, OVERLAY_COLORS.entry)
      break
    }
    default:
      break
  }
}

function overlayPrices(o) {
  return [o.price, o.price_low, o.price_high, o.entry, o.stop, o.target]
    .concat((o.points || []).map((p) => p.price))
    .filter((p) => typeof p === 'number')
}

function drawOverlays(geom, items, phase) {
  const { ctx, width, height, padding, chartMin, chartMax, candleList } = geom
  geom.times = geom.times || candleList.map((c) => Date.parse(c.time_utc))
  const highlightedIds = new Set(chartStore.highlightIds)
  const top = padding.top
  const bottom = height - padding.bottom
  const offscreen = []

  ctx.save()
  ctx.beginPath()
  ctx.rect(padding.left, top, width - padding.right - padding.left, bottom - top)
  ctx.clip()

  for (const { overlay: o, htf } of items) {
    if ((o.kind === 'zone') !== (phase === 'under')) continue

    const highlighted = highlightedIds.has(o.id)
    const prices = overlayPrices(o)
    if (prices.length && prices.every((p) => p > chartMax || p < chartMin)) {
      if (highlighted || o.layer === 'trade_plan') offscreen.push(o)
      continue
    }

    const color = OVERLAY_COLORS[o.color] || OVERLAY_COLORS.neutral
    const faded = FADED_STATUSES.has(o.status)
    ctx.save()
    ctx.globalAlpha = (faded ? 0.35 : 1) * (isStale.value ? 0.5 : 1) * (htf ? 0.7 : 1) * (highlighted ? 1 : 0.9)
    ctx.strokeStyle = color
    ctx.fillStyle = color
    ctx.lineWidth = highlighted ? 2.4 : 1.1
    ctx.setLineDash(htf || faded || DASHED_STATUSES.has(o.status) ? [5, 4] : [])
    if (highlighted) {
      ctx.shadowColor = color
      ctx.shadowBlur = 8
    }
    drawOverlay(geom, o, { htf, highlighted })
    ctx.restore()
  }
  ctx.restore()

  // Highlighted objects outside the visible price range: edge tags instead of
  // silently dropping them (the chart range is never stretched by overlays).
  if (phase === 'over') {
    for (const o of offscreen.slice(0, 4)) {
      const above = overlayPrices(o)[0] > chartMax
      ctx.save()
      ctx.globalAlpha = isStale.value ? 0.5 : 1
      drawTag(
        ctx,
        `${above ? '▲' : '▼'} ${o.name} ${formatPrice(overlayPrices(o)[0], props.symbol)}`,
        width - padding.right - 4,
        above ? top + 8 : bottom - 8,
        OVERLAY_COLORS[o.color] || OVERLAY_COLORS.neutral
      )
      ctx.restore()
    }
  }
}

function handleMouseMove(e) {
  const canvas = canvasRef.value
  if (!canvas || !candles.value.length) return

  const rect = canvas.getBoundingClientRect()
  const x = e.clientX - rect.left
  const y = e.clientY - rect.top

  mousePos.value = { x, y }

  const padding = { left: 10, right: 65 }
  const chartWidth = rect.width - padding.left - padding.right
  const candleSpacing = chartWidth / candles.value.length

  const idx = Math.floor((x - padding.left) / candleSpacing)
  if (idx >= 0 && idx < candles.value.length) {
    hoveredCandle.value = candles.value[idx]
  } else {
    hoveredCandle.value = null
  }

  renderChart()
}

function handleMouseLeave() {
  mousePos.value = { x: -1, y: -1 }
  hoveredCandle.value = null
  renderChart()
}

function handleResize() {
  renderChart()
}

let themeObserver = null

onMounted(() => {
  if (chartStore.symbol !== props.symbol) resetForSymbol(props.symbol)
  applyOverlayPayload(props.overlayPayload, props.symbol)
  fetchCandles()
  window.addEventListener('resize', handleResize)
  clockTimer = setInterval(() => {
    now.value = Date.now()
  }, 30000)

  // Watch for theme change attribute on <html> element
  themeObserver = new MutationObserver(() => {
    renderChart()
  })
  themeObserver.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ['data-theme'],
  })
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  if (clockTimer) clearInterval(clockTimer)
  if (themeObserver) {
    themeObserver.disconnect()
  }
})
</script>

<template>
  <div class="card-box chart-card">
    <div class="chart-toolbar">
      <span class="card-title">PRICE ACTION CHART</span>

      <!-- Polished Segmented Control for Timeframe -->
      <div class="segmented-control">
        <button
          v-for="tf in timeframes"
          :key="tf"
          class="segment-btn"
          :class="{ active: activeTf === tf }"
          @click="handleTimeframeChange(tf)"
        >
          {{ tf }}
        </button>
      </div>
    </div>

    <!-- OHLC Readout Bar -->
    <div class="chart-readout-bar">
      <div v-if="hoveredCandle" class="stat-readout">
        <span>O: <strong class="font-mono">{{ formatPrice(hoveredCandle.open, symbol) }}</strong></span> &nbsp;
        <span>H: <strong class="font-mono">{{ formatPrice(hoveredCandle.high, symbol) }}</strong></span> &nbsp;
        <span>L: <strong class="font-mono">{{ formatPrice(hoveredCandle.low, symbol) }}</strong></span> &nbsp;
        <span>C: <strong class="font-mono" :class="hoveredCandle.close >= hoveredCandle.open ? 'text-green' : 'text-red'">{{ formatPrice(hoveredCandle.close, symbol) }}</strong></span>
      </div>
      <div v-else class="text-muted">
        <span>Hover over candles to view bar data.</span>
      </div>

      <div class="text-muted text-xs">
        <span>Timeframe: <strong>{{ activeTf }}</strong></span>
      </div>
    </div>

    <!-- AI Drawing Layers (preferences stay in this browser; no API call) -->
    <div class="overlay-bar">
      <label v-for="layer in LAYERS" :key="layer.id" class="overlay-chip" :class="{ on: layerPrefs.layers[layer.id] }">
        <input v-model="layerPrefs.layers[layer.id]" type="checkbox" />
        {{ layer.label }}
      </label>
      <label class="overlay-chip" :class="{ on: layerPrefs.showHtf }" title="Show higher-timeframe FVG / Order Blocks / Liquidity as reference">
        <input v-model="layerPrefs.showHtf" type="checkbox" />
        HTF refs
      </label>
      <span class="overlay-actions">
        <button class="btn btn-secondary btn-sm" @click="setAllLayers(true)">Show All</button>
        <button class="btn btn-secondary btn-sm" @click="setAllLayers(false)">Hide All</button>
        <button class="btn btn-secondary btn-sm" :disabled="!hasAiDrawings" @click="clearAiDrawings">Clear AI Drawings</button>
        <button class="btn btn-secondary btn-sm" @click="handleHighlightLatest">Highlight Latest Analysis</button>
      </span>
    </div>
    <div v-if="isStale || offTimeframeHighlights.length" class="overlay-notes text-xs">
      <span v-if="isStale" class="badge badge-warning badge-sm">STALE · analysis older than 5 min, drawings faded</span>
      <span v-if="offTimeframeHighlights.length" class="text-muted">
        AI highlighted objects on {{ offTimeframeHighlights.join(', ') }} — switch timeframe to see them.
      </span>
    </div>

    <!-- Canvas Container -->
    <div
      ref="chartContainerRef"
      class="canvas-container"
      @mousemove="handleMouseMove"
      @mouseleave="handleMouseLeave"
    >
      <canvas ref="canvasRef" class="trading-canvas"></canvas>
    </div>
  </div>
</template>

<style scoped>
.overlay-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  padding: 6px 16px;
  border-bottom: 1px solid var(--border-main);
  font-size: 11px;
}

.overlay-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border: 1px solid var(--border-main);
  border-radius: var(--radius-sm);
  color: var(--text-muted);
  cursor: pointer;
  user-select: none;
}

.overlay-chip.on {
  color: var(--text-main);
  border-color: var(--accent-primary);
}

.overlay-chip input {
  margin: 0;
}

.overlay-actions {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-left: auto;
}

.overlay-actions button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.overlay-notes {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 4px 16px;
}
</style>
