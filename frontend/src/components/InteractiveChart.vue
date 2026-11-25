<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { getMarketCandles } from '../services/api'
import { formatPrice, formatDateTimeUtc } from '../utils/formatters'
import {
  ALL_TYPES,
  CATEGORIES,
  HISTORICAL_STATUSES,
  HTF_GROUPS,
  PRESETS,
  STALE_AFTER_MS,
  TIMEFRAMES,
  allOverlays,
  applyKeyLevelZones,
  applyOverlayPayload,
  categoryOf,
  chartStore,
  clearAiDrawings,
  highlightLatest,
  highlightedTimeframes,
  loadLayerPrefs,
  overlayType,
  presetPrefs,
  resetForSymbol,
  saveLayerPrefs,
  tfRank,
  toggleHidden,
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
const FADED_STATUSES = HISTORICAL_STATUSES
const DASHED_STATUSES = new Set(['candidate', 'waiting', 'potential'])

const layerPrefs = ref(loadLayerPrefs())
const now = ref(Date.now())
let clockTimer = null

const canvasRef = ref(null)
const chartContainerRef = ref(null)
const activeTf = ref(chartStore.activeTf || 'M5')
const timeframes = TIMEFRAMES

const candles = ref([])
const isLoading = ref(false)
const error = ref('')

const hoveredCandle = ref(null)
const mousePos = ref({ x: -1, y: -1 })

// Toolbar popovers
const openPanel = ref(null) // 'layers' | 'objects' | null
const expanded = ref({})
const objectFilter = ref({ tf: 'current', status: 'all' })
const visibleRange = ref(null) // price range of the last render (for Relevant Only)

const isStale = computed(() => {
  const ts = Date.parse(chartStore.generatedAt || '')
  return Number.isFinite(ts) && now.value - ts > STALE_AFTER_MS
})
const offTimeframeHighlights = computed(() => highlightedTimeframes(activeTf.value))
const hasAiDrawings = computed(
  () => Object.keys(chartStore.annotations).length > 0 || chartStore.highlightIds.length > 0
)
const tfPrefs = computed(() => layerPrefs.value.byTf[activeTf.value] || {})

// Detected objects per type: current timeframe and higher timeframes.
const typeCounts = computed(() => {
  const counts = {}
  for (const o of allOverlays()) {
    const c = (counts[overlayType(o)] ||= { current: 0, htf: 0 })
    if (o.timeframe === activeTf.value || o.timeframe === 'MTF') c.current += 1
    else if (tfRank(o.timeframe) > tfRank(activeTf.value)) c.htf += 1
  }
  return counts
})

function categoryState(cat) {
  const on = cat.types.filter((t) => tfPrefs.value[t.id]).length
  return on === 0 ? 'off' : on === cat.types.length ? 'on' : 'mixed'
}

function updateTfPrefs(next) {
  layerPrefs.value = {
    ...layerPrefs.value,
    byTf: { ...layerPrefs.value.byTf, [activeTf.value]: next },
    preset: 'custom',
  }
}

function setType(type, on) {
  updateTfPrefs({ ...tfPrefs.value, [type]: on })
}

function setCategory(cat, on) {
  const next = { ...tfPrefs.value }
  for (const t of cat.types) next[t.id] = on
  updateTfPrefs(next)
}

function setAllLayers(on) {
  updateTfPrefs(Object.fromEntries(ALL_TYPES.map((t) => [t, on])))
}

function applyPreset(name) {
  layerPrefs.value = presetPrefs(name)
}

function setOption(key, value) {
  layerPrefs.value = { ...layerPrefs.value, [key]: value }
}

function setHtf(group, on) {
  layerPrefs.value = { ...layerPrefs.value, htf: { ...layerPrefs.value.htf, [group]: on } }
}

function togglePanel(name) {
  openPanel.value = openPanel.value === name ? null : name
}

function handleHighlightLatest() {
  highlightLatest(activeTf.value)
}

// ---------------------------------------------------------------------------
// Object Manager: real objects only (engine, key-level zones, AI annotations)
// ---------------------------------------------------------------------------
const managerGroups = computed(() => {
  const drawnIds = new Set(
    visibleOverlays(activeTf.value, layerPrefs.value, visibleRange.value).map((v) => v.overlay.id)
  )
  const rows = allOverlays()
    .filter((o) => objectFilter.value.tf === 'all' || o.timeframe === activeTf.value || o.timeframe === 'MTF')
    .filter((o) => {
      if (objectFilter.value.status === 'live') return !HISTORICAL_STATUSES.has(o.status)
      if (objectFilter.value.status === 'historical') return HISTORICAL_STATUSES.has(o.status)
      return true
    })
    .map((o) => ({ o, type: overlayType(o), drawn: drawnIds.has(o.id), hidden: chartStore.hiddenIds.includes(o.id) }))
  return CATEGORIES.map((c) => ({
    ...c,
    rows: rows
      .filter((r) => categoryOf(r.type) === c.id)
      .sort((a, b) => tfRank(b.o.timeframe) - tfRank(a.o.timeframe)
        || String(b.o.time_start || '').localeCompare(String(a.o.time_start || ''))),
  })).filter((g) => g.rows.length)
})

function objectPrice(o) {
  if (o.kind === 'zone') return `${formatPrice(o.price_low, props.symbol)}–${formatPrice(o.price_high, props.symbol)}`
  if (o.kind === 'position') return `E ${formatPrice(o.entry, props.symbol)}`
  if (o.points?.length) return o.points.map((p) => formatPrice(p.price, props.symbol)).join(' → ')
  return formatPrice(o.price, props.symbol)
}

function objectTime(o) {
  const t = o.time_start || o.points?.[0]?.time
  return t ? formatDateTimeUtc(t) : '—'
}

function focusObject(o) {
  // No zoom/pan exists: "navigate" = switch to the object's timeframe, make sure
  // its type is drawn there, unhide it and highlight it.
  const tf = o.timeframe === 'MTF' ? activeTf.value : o.timeframe
  if (tf !== activeTf.value) handleTimeframeChange(tf)
  const type = overlayType(o)
  const byTf = layerPrefs.value.byTf
  if (!byTf[tf]?.[type]) {
    layerPrefs.value = { ...layerPrefs.value, byTf: { ...byTf, [tf]: { ...byTf[tf], [type]: true } }, preset: 'custom' }
  }
  if (chartStore.hiddenIds.includes(o.id)) toggleHidden(o.id)
  chartStore.highlightIds = [o.id]
}

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
  chartStore.activeTf = tf
  fetchCandles()
}

watch(
  () => props.symbol,
  (symbol) => {
    // Never carry drawings of the previous symbol over.
    resetForSymbol(symbol)
    applyOverlayPayload(props.overlayPayload, symbol)
    applyKeyLevelZones(props.keyLevels, symbol)
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
  () => [
    chartStore.engine, chartStore.keyZones, chartStore.annotations,
    chartStore.highlightIds, chartStore.hiddenIds, isStale.value,
  ],
  () => {
    renderChart()
  }
)

watch(
  () => [props.keyLevels, props.selectedScenario],
  () => {
    applyKeyLevelZones(props.keyLevels, props.symbol)
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
  const range = { min: chartMin, max: chartMax }
  if (!visibleRange.value || visibleRange.value.min !== range.min || visibleRange.value.max !== range.max) {
    visibleRange.value = range
  }
  const overlays = visibleOverlays(activeTf.value, layerPrefs.value, range)
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
// Rendering only: nothing here changes what the engine detected.
// ---------------------------------------------------------------------------

function timeToX(geom, iso) {
  const t = Date.parse(iso || '')
  const { times, padding, candleSpacing } = geom
  if (!Number.isFinite(t) || !times.length) return null
  if (t < times[0]) return padding.left // older than the visible window: clamp to the left edge
  return padding.left + timeIndex(times, t) * candleSpacing + candleSpacing / 2
}

function timeIndex(times, t) {
  let lo = 0
  let hi = times.length - 1
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1
    if (times[mid] <= t) lo = mid
    else hi = mid - 1
  }
  return lo
}

// Label placement: try the requested spot, then nudge vertically; low-priority
// labels are dropped instead of overlapping (priority 2 = always drawn).
function placeLabel(geom, text, x, y, { align = 'right', font = '9px monospace', color, tag = false, priority = 1 } = {}) {
  const { ctx } = geom
  ctx.save()
  ctx.shadowBlur = 0
  ctx.setLineDash([])
  ctx.font = tag ? 'bold 9px monospace' : font
  const w = ctx.measureText(text).width + (tag ? 8 : 2)
  const h = tag ? 13 : 11
  const offsets = priority >= 2 ? [0, -13, 13, -26, 26, 0] : [0, -12, 12, -24, 24]
  for (let i = 0; i < offsets.length; i += 1) {
    const cy = y + offsets[i]
    const left = align === 'right' ? x - w : align === 'center' ? x - w / 2 : x
    const rect = { l: left, r: left + w, t: cy - h + 3, b: cy + 3 }
    const free = !geom.labels.some((o) => rect.l < o.r && rect.r > o.l && rect.t < o.b && rect.b > o.t)
    if (free || i === offsets.length - 1 && priority >= 2) {
      geom.labels.push(rect)
      if (tag) {
        ctx.fillStyle = color
        ctx.globalAlpha = Math.min(1, ctx.globalAlpha + 0.1)
        ctx.fillRect(left, cy - 7, w, 13)
        ctx.fillStyle = '#ffffff'
        ctx.textAlign = 'left'
        ctx.fillText(text, left + 4, cy + 3)
      } else {
        ctx.fillStyle = color
        ctx.textAlign = 'left'
        ctx.fillText(text, left + 1, cy)
      }
      ctx.restore()
      return true
    }
  }
  ctx.restore()
  return false
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

// A mitigated/filled zone ends at the first candle that trades into it after it
// formed (same "touched" rule the engine uses for `fresh`).
function zoneEndX(geom, o, type) {
  if (!FADED_STATUSES.has(o.status) || !['fvg', 'ob', 'supply', 'demand'].includes(type)) return null
  const t = Date.parse(o.time_start || '')
  if (!Number.isFinite(t)) return null
  const start = timeIndex(geom.times, t) + (type === 'fvg' ? 3 : 2)
  for (let i = start; i < geom.candleList.length; i += 1) {
    const c = geom.candleList[i]
    if (c.low <= o.price_high && c.high >= o.price_low) {
      return geom.padding.left + i * geom.candleSpacing + geom.candleSpacing / 2
    }
  }
  return null
}

function drawOverlay(geom, item, highlighted) {
  const { overlay: o, htf, type } = item
  const { ctx, width, padding, chartWidth, getY } = geom
  const right = width - padding.right
  const color = OVERLAY_COLORS[o.color] || OVERLAY_COLORS.neutral
  const minimal = layerPrefs.value.labels === 'minimal'
  const label = `${htf ? `[${o.timeframe}] ` : ''}${o.name}`
  const fmt = (p) => formatPrice(p, props.symbol)
  const priority = highlighted || o.layer === 'trade_plan' ? 2 : 1

  switch (o.kind) {
    case 'zone': {
      const x1 = timeToX(geom, o.time_start) ?? padding.left
      const x2 = timeToX(geom, o.time_end) ?? zoneEndX(geom, o, type) ?? right
      const yTop = getY(o.price_high)
      const yBottom = getY(o.price_low)
      const w = Math.max(2, x2 - x1)
      const base = ctx.globalAlpha
      const fill = { premium: 0.06, discount: 0.06, supply: 0.07, demand: 0.07, fvg: 0.14, ob: 0.18 }[type] ?? 0.12
      ctx.globalAlpha = base * (highlighted ? fill + 0.12 : fill)
      ctx.fillRect(x1, yTop, w, yBottom - yTop)
      ctx.globalAlpha = base
      if (type === 'fvg') {
        // Imbalance: top/bottom edges + dashed midline (no side borders).
        ctx.beginPath()
        ctx.moveTo(x1, yTop); ctx.lineTo(x1 + w, yTop)
        ctx.moveTo(x1, yBottom); ctx.lineTo(x1 + w, yBottom)
        ctx.stroke()
        ctx.save(); ctx.setLineDash([2, 3]); ctx.globalAlpha = base * 0.6
        ctx.beginPath(); ctx.moveTo(x1, (yTop + yBottom) / 2); ctx.lineTo(x1 + w, (yTop + yBottom) / 2); ctx.stroke()
        ctx.restore()
      } else if (type === 'ob') {
        // Institutional zone: solid box + accent bar on the origin candle.
        ctx.strokeRect(x1, yTop, w, yBottom - yTop)
        ctx.fillRect(x1, yTop, 3, yBottom - yTop)
      } else if (type === 'supply' || type === 'demand') {
        ctx.save(); ctx.setLineDash([1, 3]); ctx.strokeRect(x1, yTop, w, yBottom - yTop); ctx.restore()
      } else if (type !== 'premium' && type !== 'discount') {
        ctx.strokeRect(x1, yTop, w, yBottom - yTop)
      }
      if (!minimal || highlighted) {
        placeLabel(geom, label, Math.min(x1 + w, right) - 4, yTop + 10, { color, priority })
      }
      break
    }
    case 'hline': {
      const x1 = timeToX(geom, o.time_start) ?? padding.left
      const x2 = timeToX(geom, o.time_end) ?? right
      const y = getY(o.price)
      const event = type === 'bos' || type === 'choch'
      const major = (o.meta?.touches || 0) >= 3 || (o.meta?.timeframes || []).length >= 2
      if (major && (type === 'support' || type === 'resistance')) ctx.lineWidth += 0.6
      if (type === 'choch') ctx.setLineDash([4, 3])
      ctx.beginPath()
      ctx.moveTo(x1, y)
      ctx.lineTo(x2, y)
      ctx.stroke()
      if (event) {
        // Mark the break candle itself.
        ctx.beginPath()
        ctx.moveTo(x2, y - 4); ctx.lineTo(x2 + 4, y); ctx.lineTo(x2, y + 4); ctx.lineTo(x2 - 4, y)
        ctx.closePath(); ctx.fill()
        placeLabel(geom, `${htf ? `[${o.timeframe}] ` : ''}${type === 'bos' ? 'BOS' : 'CHoCH'}`, x2 - 6, y - 4, { color, priority: highlighted ? 2 : 1 })
      } else if (highlighted || o.layer === 'trade_plan') {
        placeLabel(geom, `${label} ${fmt(o.price)}`, x2 - 2, y - 9, { color, tag: true, priority: 2 })
      } else if (!minimal) {
        placeLabel(geom, label, x2 - 4, y - 3, { color })
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
      if (!minimal || highlighted) placeLabel(geom, label, x2 + 4, y2 - 4, { align: 'left', color, priority })
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
      placeLabel(geom, label, x - 8, y2 + (y2 < y1 ? -10 : 10), { color, tag: true, priority: 2 })
      break
    }
    case 'marker': {
      const x = timeToX(geom, o.time_start)
      if (x === null) break
      const y = getY(o.price)
      const up = o.position !== 'below'
      if (o.shape === 'circle') {
        ctx.beginPath()
        ctx.arc(x, y, 7, 0, Math.PI * 2)
        ctx.stroke()
      } else {
        const ty = up ? y - 4 : y + 4
        ctx.beginPath()
        ctx.moveTo(x, ty)
        ctx.lineTo(x - 3.5, ty + (up ? -6 : 6))
        ctx.lineTo(x + 3.5, ty + (up ? -6 : 6))
        ctx.closePath()
        ctx.fill()
      }
      // Minimal labels: only the two most recent swings of each kind.
      if (!minimal || highlighted || (item.swingRank ?? 0) < 2 || o.shape === 'circle') {
        placeLabel(geom, label, x, up ? y - 13 : y + 20, {
          align: 'center', color, priority, font: highlighted ? 'bold 10px monospace' : '9px monospace',
        })
      }
      break
    }
    case 'label': {
      const y = getY(o.price)
      placeLabel(geom, label, right - 4, y, { color, tag: true, priority: 2 })
      const blocker = o.meta?.blockers?.[0]
      if (blocker) {
        placeLabel(geom, blocker.length > 70 ? `${blocker.slice(0, 67)}…` : blocker, right - 4, y + 16, {
          color, font: '9px sans-serif', priority: 2,
        })
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
        placeLabel(geom, `${name} ${fmt(price)}`, x1 + 2, y - 8, { align: 'left', color: c, tag: true, priority: 2 })
      }
      placeLabel(geom, `${label}${o.rr ? ` · RR ${o.rr}` : ''}`, right - 2, yEntry + 10, {
        color: OVERLAY_COLORS.entry, tag: true, priority: 2,
      })
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

// Draw order inside a pass: background zones first, HTF before current TF,
// highlighted last so they stay on top.
function drawPriority(item, highlightedIds) {
  return (highlightedIds.has(item.overlay.id) ? 10 : 0) + (item.htf ? 0 : 5) + (item.overlay.layer === 'premium_discount' ? -3 : 0)
}

function drawOverlays(geom, items, phase) {
  const { ctx, width, height, padding, chartMin, chartMax, candleList } = geom
  geom.times = geom.times || candleList.map((c) => Date.parse(c.time_utc))
  geom.labels = geom.labels || []
  const highlightedIds = new Set(chartStore.highlightIds)
  const top = padding.top
  const bottom = height - padding.bottom
  const offscreen = []

  ctx.save()
  ctx.beginPath()
  ctx.rect(padding.left, top, width - padding.right - padding.left, bottom - top)
  ctx.clip()

  const ordered = items
    .filter((item) => (item.overlay.kind === 'zone') === (phase === 'under'))
    .sort((a, b) => drawPriority(a, highlightedIds) - drawPriority(b, highlightedIds))

  for (const item of ordered) {
    const o = item.overlay
    const highlighted = highlightedIds.has(o.id)
    const prices = overlayPrices(o)
    if (prices.length && prices.every((p) => p > chartMax || p < chartMin)) {
      if (highlighted || o.layer === 'trade_plan') offscreen.push(o)
      continue
    }

    const color = OVERLAY_COLORS[o.color] || OVERLAY_COLORS.neutral
    const faded = FADED_STATUSES.has(o.status)
    const oldSwing = (item.swingRank ?? 0) >= 2
    ctx.save()
    ctx.globalAlpha = (faded ? 0.35 : 1) * (oldSwing && !highlighted ? 0.5 : 1)
      * (isStale.value ? 0.5 : 1) * (item.htf ? 0.65 : 1) * (highlighted ? 1 : 0.9)
    ctx.strokeStyle = color
    ctx.fillStyle = color
    ctx.lineWidth = highlighted ? 2.4 : item.htf ? 1 : 1.2
    ctx.setLineDash(item.htf || faded || DASHED_STATUSES.has(o.status) ? [5, 4] : [])
    if (highlighted) {
      ctx.shadowColor = color
      ctx.shadowBlur = 8
    }
    drawOverlay(geom, item, highlighted)
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
      placeLabel(
        geom,
        `${above ? '▲' : '▼'} ${o.name} ${formatPrice(overlayPrices(o)[0], props.symbol)}`,
        width - padding.right - 4,
        above ? top + 8 : bottom - 8,
        { color: OVERLAY_COLORS[o.color] || OVERLAY_COLORS.neutral, tag: true, priority: 2 }
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

function handleKeydown(e) {
  if (e.key === 'Escape') openPanel.value = null
}

function handleResize() {
  renderChart()
}

let themeObserver = null

onMounted(() => {
  if (chartStore.symbol !== props.symbol) resetForSymbol(props.symbol)
  applyOverlayPayload(props.overlayPayload, props.symbol)
  applyKeyLevelZones(props.keyLevels, props.symbol)
  chartStore.activeTf = activeTf.value
  fetchCandles()
  window.addEventListener('resize', handleResize)
  window.addEventListener('keydown', handleKeydown)
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
  window.removeEventListener('keydown', handleKeydown)
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

    <!-- Chart toolbar: Layer Manager, Object Manager, presets (local only, no API call) -->
    <div class="overlay-bar">
      <button class="btn btn-secondary btn-sm" :class="{ 'tool-on': openPanel === 'layers' }" title="Choose which detected objects are drawn on this timeframe" @click="togglePanel('layers')">
        Layers ▾
      </button>
      <button class="btn btn-secondary btn-sm" :class="{ 'tool-on': openPanel === 'objects' }" title="List every detected object; show, hide, highlight or jump to it" @click="togglePanel('objects')">
        Objects ▾
      </button>
      <span class="preset-group" role="group" aria-label="Display preset">
        <button
          v-for="(p, name) in PRESETS"
          :key="name"
          class="preset-btn"
          :class="{ active: layerPrefs.preset === name }"
          :title="`${p.label} preset (only changes what is drawn)`"
          @click="applyPreset(name)"
        >
          {{ p.label }}
        </button>
      </span>
      <label class="overlay-chip" :class="{ on: layerPrefs.relevantOnly }" title="Only live objects inside the visible price range; latest swings only">
        <input type="checkbox" :checked="layerPrefs.relevantOnly" @change="setOption('relevantOnly', $event.target.checked)" />
        Relevant only
      </label>
      <span class="overlay-actions">
        <button class="btn btn-secondary btn-sm" title="Show every object type on this timeframe" @click="setAllLayers(true)">Show All</button>
        <button class="btn btn-secondary btn-sm" title="Hide every object type on this timeframe" @click="setAllLayers(false)">Hide All</button>
        <button class="btn btn-secondary btn-sm" title="Highlight the key objects of the latest analysis on this timeframe" @click="handleHighlightLatest">Highlight Latest</button>
        <button class="btn btn-secondary btn-sm" :disabled="!hasAiDrawings" title="Remove AI chat annotations and highlights (detected objects stay)" @click="clearAiDrawings">Clear AI</button>
      </span>
    </div>

    <!-- Layer Manager -->
    <div v-if="openPanel === 'layers'" class="chart-popover">
      <div class="popover-head">
        <span class="text-xs">
          Settings for <strong>{{ activeTf }}</strong>
          <span class="text-muted">· preset: {{ PRESETS[layerPrefs.preset]?.label || 'Custom' }}</span>
        </span>
        <button class="btn btn-secondary btn-sm" @click="openPanel = null">Close</button>
      </div>
      <div class="popover-body">
        <div v-for="cat in CATEGORIES" :key="cat.id" class="cat-block">
          <div class="cat-row">
            <button class="cat-toggle" :aria-expanded="!!expanded[cat.id]" @click="expanded[cat.id] = !expanded[cat.id]">
              {{ expanded[cat.id] ? '▾' : '▸' }}
            </button>
            <label class="cat-label">
              <input
                type="checkbox"
                :checked="categoryState(cat) !== 'off'"
                :indeterminate.prop="categoryState(cat) === 'mixed'"
                @change="setCategory(cat, $event.target.checked)"
              />
              {{ cat.label }}
            </label>
            <span class="text-xs text-muted">
              {{ cat.types.reduce((n, t) => n + (typeCounts[t.id]?.current || 0), 0) }}
              <template v-if="cat.types.some((t) => typeCounts[t.id]?.htf)">
                · HTF {{ cat.types.reduce((n, t) => n + (typeCounts[t.id]?.htf || 0), 0) }}
              </template>
            </span>
          </div>
          <div v-if="expanded[cat.id]" class="type-list">
            <label v-for="t in cat.types" :key="t.id" class="type-row">
              <input type="checkbox" :checked="!!tfPrefs[t.id]" @change="setType(t.id, $event.target.checked)" />
              <span>{{ t.label }}</span>
              <span class="text-xs text-muted">{{ typeCounts[t.id]?.current || 0 }}</span>
            </label>
            <div v-for="u in cat.unsupported || []" :key="u" class="type-row disabled" title="The analysis engine does not detect this object yet">
              <input type="checkbox" disabled />
              <span>{{ u }}</span>
              <span class="text-xs text-muted">not detected by engine</span>
            </div>
          </div>
        </div>

        <div class="cat-block">
          <div class="text-xs text-muted uppercase font-bold">Display</div>
          <label class="type-row">
            <input type="checkbox" :checked="layerPrefs.showHistory" @change="setOption('showHistory', $event.target.checked)" />
            <span>Show history (mitigated / swept / broken, older swings)</span>
          </label>
          <label class="type-row">
            <input type="checkbox" :checked="layerPrefs.labels === 'minimal'" @change="setOption('labels', $event.target.checked ? 'minimal' : 'normal')" />
            <span>Minimal labels</span>
          </label>
        </div>

        <div class="cat-block">
          <div class="text-xs text-muted uppercase font-bold">Higher-timeframe references (above {{ activeTf }})</div>
          <label v-for="g in HTF_GROUPS" :key="g.id" class="type-row">
            <input type="checkbox" :checked="!!layerPrefs.htf[g.id]" @change="setHtf(g.id, $event.target.checked)" />
            <span>{{ g.label }}</span>
          </label>
          <div class="text-xs text-muted">HTF objects keep their timeframe tag, are dashed, live and in view only, max 2 per type per timeframe.</div>
        </div>
      </div>
    </div>

    <!-- Object Manager -->
    <div v-if="openPanel === 'objects'" class="chart-popover">
      <div class="popover-head">
        <span class="popover-filters">
          <select v-model="objectFilter.tf" class="mini-select" aria-label="Timeframe filter">
            <option value="current">{{ activeTf }} + MTF</option>
            <option value="all">All timeframes</option>
          </select>
          <select v-model="objectFilter.status" class="mini-select" aria-label="Status filter">
            <option value="all">All statuses</option>
            <option value="live">Live only</option>
            <option value="historical">Historical only</option>
          </select>
        </span>
        <button class="btn btn-secondary btn-sm" @click="openPanel = null">Close</button>
      </div>
      <div class="popover-body">
        <div v-if="!managerGroups.length" class="text-xs text-muted">No detected objects for this filter.</div>
        <div v-for="g in managerGroups" :key="g.id" class="cat-block">
          <div class="text-xs text-muted uppercase font-bold">{{ g.label }} ({{ g.rows.length }})</div>
          <div v-for="r in g.rows" :key="r.o.id" class="obj-row" :class="{ dim: !r.drawn }">
            <button
              class="obj-eye"
              :title="r.hidden ? 'Show this object' : 'Hide this object'"
              :aria-pressed="!r.hidden"
              @click="toggleHidden(r.o.id)"
            >
              {{ r.hidden ? '◌' : '●' }}
            </button>
            <span class="obj-main" :class="r.o.color === 'bullish' ? 'text-green' : r.o.color === 'bearish' ? 'text-red' : ''">
              {{ r.o.name }}
            </span>
            <span class="badge badge-neutral badge-sm">{{ r.o.timeframe }}</span>
            <span class="text-xs text-muted">{{ r.o.status }}</span>
            <span class="text-xs font-mono">{{ objectPrice(r.o) }}</span>
            <span class="text-xs text-muted">{{ objectTime(r.o) }}</span>
            <button class="btn btn-secondary btn-sm obj-go" title="Switch to its timeframe and highlight it" @click="focusObject(r.o)">Show</button>
          </div>
        </div>
        <div class="text-xs text-muted">Greyed rows are detected but not drawn with the current layer/relevance settings.</div>
      </div>
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

.chart-card {
  position: relative;
}

.tool-on {
  border-color: var(--accent-primary) !important;
  color: var(--accent-primary) !important;
}

.preset-group {
  display: inline-flex;
  border: 1px solid var(--border-main);
  border-radius: var(--radius-sm);
  overflow: hidden;
}

.preset-btn {
  background: transparent;
  border: none;
  border-right: 1px solid var(--border-main);
  color: var(--text-muted);
  font-size: 11px;
  font-weight: 600;
  padding: 3px 9px;
  cursor: pointer;
}

.preset-btn:last-child {
  border-right: none;
}

.preset-btn.active {
  background: var(--accent-light);
  color: var(--accent-primary);
}

.chart-popover {
  position: absolute;
  top: 92px;
  right: 16px;
  width: min(460px, calc(100% - 32px));
  max-height: 400px;
  display: flex;
  flex-direction: column;
  background: var(--bg-surface);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-lg);
  z-index: 20;
}

.popover-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--border-main);
}

.popover-filters {
  display: inline-flex;
  gap: 6px;
}

.mini-select {
  font-size: 11px;
  padding: 2px 6px;
  border: 1px solid var(--border-main);
  border-radius: var(--radius-sm);
}

.popover-body {
  overflow-y: auto;
  padding: 8px 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.cat-block {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.cat-row {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 600;
}

.cat-toggle {
  background: transparent;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  width: 16px;
  padding: 0;
}

.cat-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex: 1;
  cursor: pointer;
}

.type-list {
  padding-left: 22px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.type-row {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  cursor: pointer;
}

.type-row span:first-of-type {
  flex: 1;
}

.type-row.disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.obj-row {
  display: grid;
  grid-template-columns: 18px minmax(90px, 1fr) auto auto auto auto auto;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  padding: 2px 0;
  border-bottom: 1px dashed var(--border-main);
}

.obj-row.dim {
  opacity: 0.55;
}

.obj-eye {
  background: transparent;
  border: none;
  color: var(--accent-primary);
  cursor: pointer;
  padding: 0;
  font-size: 12px;
}

.obj-main {
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.obj-go {
  padding: 1px 6px;
}

.overlay-notes {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 4px 16px;
}
</style>
