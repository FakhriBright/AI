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
  buildDerived,
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
  sourceOf,
  tfRank,
  toggleHidden,
  visibleOverlays,
} from '../utils/chartOverlays'
import {
  MUTED_FACTOR,
  SCENARIO_TIER_STYLE,
  buildConfluence,
  confluenceLabel,
  layoutLabelsCached,
  lifecycleStyle,
} from '../utils/chartVisuals'

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
  marketBias: {
    type: Object,
    default: null,
  },
  scenarios: {
    type: Object,
    default: null,
  },
})

// Candles loaded per timeframe; the viewport shows a window of them.
const CANDLE_COUNT = 300
const DEFAULT_VISIBLE = 80
const FUTURE_BARS = 8 // blank space for conditional scenario projections

// Chart workspace palette (mandatory). Bullish = soft white, bearish =
// midnight blue violet on a dark navy canvas. #30265F is used for bodies and
// fills; a lighter tint of the same hue is used for wicks, edges and text so
// bearish objects stay visible on #0B1020. No bright green/red for direction.
const PALETTE = {
  bg: '#0B1020',
  bull: '#F5F5F7',
  bear: '#30265F',
  bearEdge: '#7A6FD0',
  bearWick: '#8E84DA',
  grid: 'rgba(245, 245, 247, 0.06)',
  axisText: '#8B93A7',
}
const OVERLAY_COLORS = {
  bullish: PALETTE.bull,
  bearish: PALETTE.bearEdge,
  neutral: '#8B93A7',
  info: '#5FB7D9', // liquidity: restrained cyan
  warning: '#E0A84A',
  entry: '#5FB7D9',
  stop: '#D9657F',
  target: PALETTE.bull,
}
// Zone fills: the base colours themselves, with a gain so #30265F reads on navy.
const FILL_COLOR = { bullish: PALETTE.bull, bearish: PALETTE.bear }
const FILL_GAIN = { bullish: 0.6, bearish: 2.6 }
const FADED_STATUSES = HISTORICAL_STATUSES

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
const objectFilter = ref({ tf: 'current', status: 'all', source: 'all' })

// Viewport: `size` visible candles; `anchor` = time of the first visible candle
// once the user pans (null = follow the latest candle). Time-anchored so a data
// refresh does not shift the view.
const view = ref({ size: DEFAULT_VISIBLE, anchor: null })
const drag = { active: false, moved: false, startX: 0, startIndex: 0 }
let lastGeom = null
const hoverInfo = ref(null) // { o, x, y }
const selected = ref(null) // pinned object details

// Display precision from the market data itself (symbol tick size).
const priceDigits = computed(() => {
  let digits = 0
  for (const c of candles.value.slice(-50)) {
    for (const v of [c.open, c.high, c.low, c.close]) {
      const text = String(v)
      const d = text.includes('.') ? text.split('.')[1].length : 0
      if (d > digits) digits = d
    }
  }
  return Math.min(digits, 6)
})

function fmtPrice(value) {
  if (typeof value !== 'number' || !Number.isFinite(value)) return formatPrice(value, props.symbol)
  return candles.value.length ? value.toFixed(priceDigits.value) : formatPrice(value, props.symbol)
}

function resetView() {
  view.value = { size: DEFAULT_VISIBLE, anchor: null }
}
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
    .filter((o) => objectFilter.value.source === 'all' || sourceOf(o) === objectFilter.value.source)
    .filter((o) => objectFilter.value.visibility !== 'drawn' || drawnIds.has(o.id))
    .map((o) => ({
      o, type: overlayType(o), source: sourceOf(o),
      drawn: drawnIds.has(o.id), hidden: chartStore.hiddenIds.includes(o.id),
    }))
  return CATEGORIES.map((c) => ({
    ...c,
    rows: rows
      .filter((r) => categoryOf(r.type) === c.id)
      .sort((a, b) => tfRank(b.o.timeframe) - tfRank(a.o.timeframe)
        || String(b.o.time_start || '').localeCompare(String(a.o.time_start || ''))),
  })).filter((g) => g.rows.length)
})

function objectPrice(o) {
  if (o.visualOnly === 'group') return o.meta?.text || ''
  if (o.kind === 'zone') return `${fmtPrice(o.price_low)}–${fmtPrice(o.price_high)}`
  if (o.kind === 'position') return `E ${fmtPrice(o.entry)}`
  if (o.points?.length) return o.points.map((p) => fmtPrice(p.price)).join(' → ')
  return fmtPrice(o.price)
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
  // Pan so the object's start time is inside the viewport (exact location).
  const t = o.time_start || o.points?.find((pt) => pt.time)?.time
  if (t && tf === activeTf.value) bringTimeIntoView(t)
}

function bringTimeIntoView(iso) {
  const t = Date.parse(iso)
  const times = candles.value.map((c) => Date.parse(c.time_utc))
  if (!Number.isFinite(t) || !times.length) return
  const size = Math.min(view.value.size, times.length)
  const latestStart = times.length - size
  const currentStart = view.value.anchor ? Math.max(0, times.findIndex((x) => x >= Date.parse(view.value.anchor))) : latestStart
  let idx = times.findIndex((x) => x >= t)
  if (idx < 0) idx = times.length - 1
  if (idx >= currentStart && idx < currentStart + size) return
  const start = Math.max(0, Math.min(latestStart, idx - Math.floor(size / 3)))
  view.value = { size, anchor: start >= latestStart ? null : candles.value[start].time_utc }
}

async function fetchCandles() {
  isLoading.value = true
  error.value = ''
  hoveredCandle.value = null

  try {
    const res = await getMarketCandles(props.symbol, activeTf.value, CANDLE_COUNT)
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
  resetView()
  selected.value = null
  fetchCandles()
}

watch(
  () => props.symbol,
  (symbol) => {
    // Never carry drawings of the previous symbol over.
    resetForSymbol(symbol)
    applyOverlayPayload(props.overlayPayload, symbol)
    applyKeyLevelZones(props.keyLevels, symbol)
    rebuildDerived()
    resetView()
    selected.value = null
    fetchCandles()
  }
)

watch(
  () => props.overlayPayload,
  (payload) => {
    applyOverlayPayload(payload, props.symbol)
    rebuildDerived()
  }
)

function rebuildDerived() {
  buildDerived({
    symbol: props.symbol,
    marketBias: props.marketBias,
    scenarios: props.scenarios,
    currentPrice: props.keyLevels?.current_price,
    selectedName: props.selectedScenario?.name || null,
    stale: isStale.value,
  })
}

watch(() => [props.marketBias, props.scenarios, props.selectedScenario, isStale.value], rebuildDerived)
watch(view, () => renderChart(), { deep: true })

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
    chartStore.engine, chartStore.keyZones, chartStore.derived, chartStore.annotations,
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

  // The chart canvas is always the dark navy workspace (#0B1020), in both app themes.
  const isDark = true
  ctx.fillStyle = PALETTE.bg
  ctx.fillRect(0, 0, width, height)

  const allCandles = candles.value
  if (!allCandles || allCandles.length === 0) {
    ctx.fillStyle = PALETTE.axisText
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

  // Viewport window over the loaded candles (zoom/pan).
  const allTimes = allCandles.map((c) => Date.parse(c.time_utc))
  const size = Math.max(15, Math.min(view.value.size, allCandles.length))
  const latestStart = allCandles.length - size
  let start = latestStart
  if (view.value.anchor) {
    const anchorT = Date.parse(view.value.anchor)
    const idx = allTimes.findIndex((t) => t >= anchorT)
    start = Math.max(0, Math.min(latestStart, idx < 0 ? latestStart : idx))
  }
  const followingLatest = start === latestStart
  const candleList = allCandles.slice(start, start + size)
  // Future space only at the live edge and only when scenarios are drawn.
  const future = followingLatest && layerPrefs.value.byTf[activeTf.value]?.scenario ? FUTURE_BARS : 0

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
  ctx.strokeStyle = PALETTE.grid
  ctx.fillStyle = PALETTE.axisText
  ctx.font = '10px monospace'
  ctx.textAlign = 'left'

  for (let i = 0; i <= gridSteps; i++) {
    const y = padding.top + (chartHeight / gridSteps) * i
    const priceVal = chartMax - (adjustedRange / gridSteps) * i

    ctx.beginPath()
    ctx.moveTo(padding.left, y)
    ctx.lineTo(width - padding.right, y)
    ctx.stroke()

    ctx.fillText(fmtPrice(priceVal), width - padding.right + 8, y + 3)
  }

  // Selected scenario trigger / invalidation (existing feature), restrained:
  // axis ticks always; a thin line only when the scenario layer is off (the
  // scenario annotation already draws these levels otherwise). Key S/R levels
  // are drawn by the Support & Resistance layer (same key_levels data).
  const scenarioLayerOn = Boolean(layerPrefs.value.byTf[activeTf.value]?.scenario)
  for (const [ref, tag, color] of [[triggerRef, 'TRG', '#5FB7D9'], [invalidationRef, 'INV', '#E0A84A']]) {
    if (!ref) continue
    const y = getY(ref)
    if (y < padding.top || y > height - padding.bottom) continue
    ctx.save()
    if (!scenarioLayerOn) {
      ctx.strokeStyle = color
      ctx.globalAlpha = 0.45
      ctx.lineWidth = 1
      ctx.setLineDash([6, 3])
      ctx.beginPath()
      ctx.moveTo(padding.left, y)
      ctx.lineTo(width - padding.right, y)
      ctx.stroke()
      ctx.globalAlpha = 1
    }
    ctx.fillStyle = color
    ctx.fillRect(width - padding.right, y - 1, 5, 2)
    ctx.font = 'bold 8px monospace'
    ctx.textAlign = 'left'
    ctx.fillText(tag, width - padding.right + 45, y + 3)
    ctx.restore()
  }

  ctx.setLineDash([]) // reset

  // Candlesticks rendering
  const count = candleList.length
  const candleSpacing = chartWidth / (count + future)
  const candleWidth = Math.max(1.5, candleSpacing * 0.7)
  const barMs = allTimes.length > 1 ? allTimes[allTimes.length - 1] - allTimes[allTimes.length - 2] : 60000

  const geom = {
    ctx, width, height, padding, chartWidth, chartHeight, getY, chartMin, chartMax, candleList, candleSpacing, isDark,
    allCandles, allTimes, start, future, barMs, followingLatest, hits: [], labels: [],
    labelReqs: [], reserved: [],
  }
  lastGeom = geom
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

    // Volume bars at bottom
    if (maxVol > 0) {
      const volHeight = (c.tick_volume / maxVol) * 40
      ctx.fillStyle = isBullish ? 'rgba(245, 245, 247, 0.10)' : 'rgba(122, 111, 208, 0.22)'
      ctx.fillRect(x - candleWidth / 2, height - padding.bottom - volHeight, candleWidth, volHeight)
    }

    // Wick: bearish uses a lighter tint of the bearish hue for contrast on navy.
    ctx.strokeStyle = isBullish ? PALETTE.bull : PALETTE.bearWick
    ctx.lineWidth = 1.2
    ctx.beginPath()
    ctx.moveTo(x, highY)
    ctx.lineTo(x, lowY)
    ctx.stroke()

    // Body: #F5F5F7 / #30265F, bearish bodies get a tinted border.
    const bodyTop = Math.min(openY, closeY)
    const bodyHeight = Math.max(1.5, Math.abs(closeY - openY))
    ctx.fillStyle = isBullish ? PALETTE.bull : PALETTE.bear
    ctx.fillRect(x - candleWidth / 2, bodyTop, candleWidth, bodyHeight)
    if (!isBullish && candleWidth >= 3) {
      ctx.strokeStyle = PALETTE.bearEdge
      ctx.lineWidth = 1
      ctx.strokeRect(x - candleWidth / 2 + 0.5, bodyTop + 0.5, candleWidth - 1, Math.max(0.5, bodyHeight - 1))
    }
    // Labels must not cover the latest candle bodies (current price action).
    if (i >= count - 12) {
      geom.reserved.push({ l: x - candleWidth / 2 - 1, r: x + candleWidth / 2 + 1, t: highY - 1, b: lowY + 1 })
    }
  }

  // Current price: dashed line + axis tag (last candle close from the live feed).
  const lastClose = allCandles[allCandles.length - 1]?.close
  if (typeof lastClose === 'number' && lastClose >= chartMin && lastClose <= chartMax) {
    const yp = getY(lastClose)
    ctx.save()
    ctx.strokeStyle = isDark ? 'rgba(20, 184, 166, 0.7)' : 'rgba(15, 118, 110, 0.7)'
    ctx.setLineDash([2, 2])
    ctx.beginPath(); ctx.moveTo(padding.left, yp); ctx.lineTo(width - padding.right, yp); ctx.stroke()
    ctx.setLineDash([])
    ctx.fillStyle = isDark ? '#14b8a6' : '#0f766e'
    ctx.fillRect(width - padding.right + 1, yp - 8, padding.right - 2, 16)
    ctx.fillStyle = '#ffffff'
    ctx.font = 'bold 10px monospace'
    ctx.textAlign = 'left'
    ctx.fillText(fmtPrice(lastClose), width - padding.right + 4, yp + 4)
    ctx.restore()
    // Labels may not cover the current price marker near the axis.
    geom.reserved.push({ l: width - padding.right - 70, r: width - padding.right, t: yp - 7, b: yp + 7 })
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
      ctx.fillText(fmtPrice(hoveredPrice), width - padding.right + 5, mousePos.value.y + 4)
    }

    ctx.setLineDash([])
  }
}

// ---------------------------------------------------------------------------
// Overlay drawing (engine objects + AI chat annotations)
// Rendering only: nothing here changes what the engine detected.
// ---------------------------------------------------------------------------

// Market time -> canvas x, through the loaded candle series and the viewport.
// Objects older than the loaded data start just off the left edge; times after
// the last candle are extrapolated by the bar duration (projection space).
function indexToX(geom, idx) {
  return geom.padding.left + (idx - geom.start) * geom.candleSpacing + geom.candleSpacing / 2
}

function timeToX(geom, iso) {
  const t = Date.parse(iso || '')
  const { allTimes } = geom
  if (!Number.isFinite(t) || !allTimes.length) return null
  if (t < allTimes[0]) return indexToX(geom, -1)
  const last = allTimes.length - 1
  if (t > allTimes[last]) return indexToX(geom, last + (t - allTimes[last]) / geom.barMs)
  return indexToX(geom, timeIndex(allTimes, t))
}

function xToIndex(geom, x) {
  return Math.round((x - geom.padding.left - geom.candleSpacing / 2) / geom.candleSpacing) + geom.start
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

// Label requests are collected while shapes are drawn and laid out once per
// render (chartVisuals.layoutLabels): high priority first, offsets, then "+N"
// groups. Anchors are market coordinates; only screen offsets change.
// priority: 3 = primary scenario / trade plan / highlighted, 2 = events,
// callouts, active zones, 1 = everything else.
function placeLabel(geom, text, x, y, { align = 'right', font = '9px monospace', color, tag = false, priority = 1, key, kind = 'text', anchor = null, ids = [] } = {}) {
  const { ctx } = geom
  ctx.save()
  ctx.font = tag || kind === 'callout' ? 'bold 9px monospace' : font
  const w = ctx.measureText(text).width + (tag || kind === 'callout' ? 10 : 2)
  ctx.restore()
  geom.labelReqs.push({
    key: key || `${text}@${Math.round(x)},${Math.round(y)}`,
    text, x, y, w, h: tag || kind === 'callout' ? 14 : 11, align, font, color, tag, kind, anchor, ids,
    priority, alpha: ctx.globalAlpha,
  })
  return true
}

function flushLabels(geom) {
  const { ctx, width, height, padding } = geom
  const bounds = { l: padding.left + 2, r: width - padding.right - 2, t: padding.top + 2, b: height - padding.bottom - 2 }
  const { placed, grouped } = layoutLabelsCached(geom.labelReqs, { reserved: geom.reserved, bounds })
  for (const r of placed) {
    const { rect } = r
    ctx.save()
    ctx.globalAlpha = r.alpha
    ctx.shadowBlur = 0
    ctx.setLineDash([])
    if (r.kind === 'callout') {
      if (r.anchor) {
        ctx.strokeStyle = r.color
        ctx.globalAlpha = r.alpha * 0.7
        ctx.beginPath()
        ctx.moveTo(r.anchor.x, r.anchor.y)
        ctx.lineTo(Math.max(rect.l, Math.min(rect.r, r.anchor.x)), r.anchor.y < rect.t ? rect.t : rect.b)
        ctx.stroke()
        ctx.globalAlpha = r.alpha
        ctx.fillStyle = r.color
        ctx.beginPath(); ctx.arc(r.anchor.x, r.anchor.y, 2.5, 0, Math.PI * 2); ctx.fill()
      }
      ctx.fillStyle = geom.isDark ? 'rgba(15, 23, 42, 0.92)' : 'rgba(255, 255, 255, 0.95)'
      ctx.fillRect(rect.l, rect.t, rect.r - rect.l, rect.b - rect.t)
      ctx.strokeStyle = r.color
      ctx.strokeRect(rect.l, rect.t, rect.r - rect.l, rect.b - rect.t)
      ctx.fillStyle = r.color
      ctx.font = 'bold 9px monospace'
      ctx.textAlign = 'left'
      ctx.fillText(r.text, rect.l + 5, rect.b - 4)
      if (r.ids.length) geom.hits.push({ o: r.owner, type: 'rect', ...rect, priority: 3 })
    } else if (r.tag) {
      ctx.fillStyle = r.color
      ctx.globalAlpha = Math.min(1, r.alpha + 0.1)
      ctx.fillRect(rect.l, rect.t, rect.r - rect.l, rect.b - rect.t)
      ctx.fillStyle = '#ffffff'
      ctx.font = 'bold 9px monospace'
      ctx.textAlign = 'left'
      ctx.fillText(r.text, rect.l + 5, rect.b - 4)
    } else {
      ctx.fillStyle = r.color
      ctx.font = r.font
      ctx.textAlign = 'left'
      ctx.fillText(r.text, rect.l + 1, rect.b - 2)
    }
    ctx.restore()
  }
  // Collapsed groups: "+N" chips; hover/click lists and highlights the members.
  for (const g of grouped) {
    ctx.save()
    ctx.fillStyle = geom.isDark ? 'rgba(148, 163, 184, 0.25)' : 'rgba(71, 85, 105, 0.15)'
    ctx.fillRect(g.rect.l, g.rect.t, g.rect.r - g.rect.l, g.rect.b - g.rect.t)
    ctx.fillStyle = geom.isDark ? '#cbd5e1' : '#334155'
    ctx.font = 'bold 9px monospace'
    ctx.textAlign = 'left'
    ctx.fillText(g.text, g.rect.l + 4, g.rect.b - 2)
    ctx.restore()
    const ids = [...new Set(g.items.flatMap((i) => i.ids))]
    geom.hits.push({
      o: {
        id: `group:${g.items.map((i) => i.key).join('|')}`, visualOnly: 'group', kind: 'label', timeframe: activeTf.value,
        name: `${g.items.length} grouped labels`, status: 'active', price: null,
        meta: { text: g.items.map((i) => i.text).join(' · ') }, memberIds: ids,
      },
      type: 'rect', ...g.rect, priority: 3,
    })
  }
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

function drawLineArrow(ctx, ax, ay, bx, by, size = 7) {
  const ang = Math.atan2(by - ay, bx - ax)
  ctx.beginPath()
  ctx.moveTo(bx, by)
  ctx.lineTo(bx - size * Math.cos(ang - 0.4), by - size * Math.sin(ang - 0.4))
  ctx.lineTo(bx - size * Math.cos(ang + 0.4), by - size * Math.sin(ang + 0.4))
  ctx.closePath()
  ctx.fill()
}

// A mitigated/filled zone ends at the first candle that trades into it after it
// formed (same "touched" rule the engine uses for `fresh`).
function zoneEndX(geom, o, type) {
  if (!FADED_STATUSES.has(o.status) || !['fvg', 'ob', 'supply', 'demand'].includes(type)) return null
  const t = Date.parse(o.time_start || '')
  if (!Number.isFinite(t) || t < geom.allTimes[0]) return null
  const from = timeIndex(geom.allTimes, t) + (type === 'fvg' ? 3 : 2)
  for (let i = from; i < geom.allCandles.length; i += 1) {
    const c = geom.allCandles[i]
    if (c.low <= o.price_high && c.high >= o.price_low) return indexToX(geom, i)
  }
  return null
}

const SHORT_NAME = {
  bsl: 'BSL', ssl: 'SSL', eqh: 'EQH', eql: 'EQL', support: 'S', resistance: 'R', supply: 'Supply', demand: 'Demand',
}

function drawOverlay(geom, item, highlighted) {
  const { overlay: o, htf, type } = item
  const { ctx, width, padding, chartWidth, getY } = geom
  const right = width - padding.right
  const color = OVERLAY_COLORS[o.color] || OVERLAY_COLORS.neutral
  const minimal = layerPrefs.value.labels === 'minimal'
  const tfTag = htf ? `${o.timeframe} · ` : ''
  const label = `${tfTag}${o.name}`
  const fmt = (p) => fmtPrice(p)
  const priority = highlighted || o.layer === 'trade_plan' ? 3 : o.meta?.key && !FADED_STATUSES.has(o.status) ? 2 : 1
  const ids = [o.id]
  const style = item.style

  switch (o.kind) {
    case 'zone': {
      const x1 = timeToX(geom, o.time_start) ?? padding.left
      const x2 = timeToX(geom, o.time_end) ?? zoneEndX(geom, o, type) ?? right
      const yTop = getY(o.price_high)
      const yBottom = getY(o.price_low)
      const w = Math.max(2, x2 - x1)
      const base = ctx.globalAlpha
      const consolidated = geom.consolidated?.has(o.id) && !highlighted
      const gain = FILL_GAIN[o.color] ?? 1
      const fill = ({ premium: 0.06, discount: 0.06, supply: 0.1, demand: 0.1, fvg: 0.16, ob: 0.2 }[type] ?? 0.12)
        * style.fill * gain * (consolidated ? 0.35 : 1)
      ctx.fillStyle = FILL_COLOR[o.color] || color
      ctx.globalAlpha = Math.min(1, base * (highlighted ? fill + 0.14 : fill))
      ctx.fillRect(x1, yTop, w, yBottom - yTop)
      ctx.fillStyle = color
      ctx.globalAlpha = base * (consolidated ? 0.5 : 1)
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
        // Supply/demand block: solid box + accent bar on the origin candle.
        ctx.strokeRect(x1, yTop, w, yBottom - yTop)
        ctx.fillRect(x1, yTop, 3, yBottom - yTop)
      } else if (type === 'supply' || type === 'demand') {
        ctx.save(); ctx.setLineDash([1, 3]); ctx.strokeRect(x1, yTop, w, yBottom - yTop); ctx.restore()
      } else if (type === 'premium' || type === 'discount') {
        // Dealing-range section: edge line toward the range extreme only.
        ctx.beginPath()
        const yEdge = type === 'premium' ? yTop : yBottom
        ctx.moveTo(x1, yEdge); ctx.lineTo(x1 + w, yEdge)
        ctx.stroke()
      } else {
        ctx.strokeRect(x1, yTop, w, yBottom - yTop)
      }
      // Consolidated members: the confluence band carries the label (inspect via hover).
      if (!consolidated && (!minimal || highlighted || type === 'fvg' || type === 'ob')) {
        const short = type === 'fvg' ? 'FVG' : type === 'ob' ? 'OB' : (SHORT_NAME[type] || o.name)
        const life = o.status === 'active' ? (o.meta?.fresh === true ? 'fresh' : 'active') : o.status
        const text = ['fvg', 'ob', 'supply', 'demand'].includes(type)
          ? `${tfTag}${o.color === 'bullish' ? '▲' : '▼'} ${short} · ${life}`
          : label
        // Inside the zone, top-left: stays with the zone when zooming/panning.
        placeLabel(geom, text, Math.max(padding.left + 2, x1 + 4), yTop + 10, {
          align: 'left', color, priority, key: o.id, ids,
        })
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
      if ((type === 'support' || type === 'resistance') && !o.time_start) {
        // Price-only level: compact segment at the live edge, not a full-width line.
        ctx.beginPath()
        ctx.moveTo(Math.max(padding.left, right - chartWidth * 0.35), y)
        ctx.lineTo(right, y)
        ctx.stroke()
        if (!minimal || highlighted) {
          placeLabel(geom, `${tfTag}${SHORT_NAME[type]}${major ? ' major' : ''}`, right - 4, y - 3, { color, priority, key: o.id, ids })
        }
        break
      }
      if (type === 'choch') ctx.setLineDash([4, 3])
      if (type === 'eq') ctx.setLineDash([6, 2, 1, 2])
      if (['bsl', 'ssl'].includes(type)) ctx.setLineDash([1, 3])
      ctx.beginPath()
      ctx.moveTo(x1, y)
      ctx.lineTo(x2, y)
      ctx.stroke()
      if (event) {
        // Structure connector: swing level -> break candle, label on the connector.
        ctx.beginPath()
        ctx.arc(x1, y, 2.5, 0, Math.PI * 2)
        ctx.fill()
        ctx.beginPath()
        ctx.moveTo(x2, y - 4); ctx.lineTo(x2 + 4, y); ctx.lineTo(x2, y + 4); ctx.lineTo(x2 - 4, y)
        ctx.closePath(); ctx.fill()
        const up = o.name.includes('↑')
        placeLabel(geom, `${tfTag}${type === 'bos' ? 'BOS' : 'CHoCH'}`, (x1 + x2) / 2, up ? y - 3 : y + 11, {
          align: 'center', color, priority: highlighted ? 3 : 2, key: o.id, ids, font: 'bold 9px monospace',
        })
      } else if (type === 'eq') {
        placeLabel(geom, `${tfTag}EQ 50%`, x2 - 4, y - 3, { color, priority: 1, key: o.id, ids })
      } else if (o.status === 'taken') {
        // Swept level: subdued line + cross at its end.
        ctx.save(); ctx.setLineDash([]); ctx.lineWidth = 1.2
        ctx.beginPath(); ctx.moveTo(x2 - 4, y - 4); ctx.lineTo(x2 + 4, y + 4); ctx.moveTo(x2 + 4, y - 4); ctx.lineTo(x2 - 4, y + 4); ctx.stroke()
        ctx.restore()
        if (!minimal) placeLabel(geom, `${tfTag}${SHORT_NAME[type] || o.name} swept`, x2 - 8, y - 3, { color, priority: 1, key: o.id, ids })
      } else if (highlighted || o.layer === 'trade_plan') {
        placeLabel(geom, `${label} ${fmt(o.price)}`, x2 - 2, y - 9, { color, tag: true, priority: 3, key: o.id, ids })
      } else if (!minimal) {
        placeLabel(geom, `${tfTag}${SHORT_NAME[type] || o.name}`, x2 - 4, y - 3, { color, priority, key: o.id, ids })
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
      const isEq = type === 'eqh' || type === 'eql'
      let xe = x2
      let ye = y2
      if (o.extend) {
        xe = right
        ye = y2 + ((y2 - y1) / (x2 - x1)) * (xe - x2)
      }
      if (isEq) {
        // Liquidity pool: band between the equal highs/lows.
        const base = ctx.globalAlpha
        ctx.globalAlpha = base * 0.18
        ctx.fillRect(x1, Math.min(y1, y2) - 3, x2 - x1, Math.abs(y2 - y1) + 6)
        ctx.globalAlpha = base
        ctx.setLineDash([1, 3])
      }
      ctx.beginPath()
      ctx.moveTo(x1, y1)
      ctx.lineTo(xe, ye)
      ctx.stroke()
      // Pivot anchors.
      for (const [ax, ay] of [[x1, y1], [x2, y2]]) {
        ctx.beginPath(); ctx.arc(ax, ay, 2.5, 0, Math.PI * 2); ctx.fill()
      }
      if (!minimal || highlighted) {
        placeLabel(geom, isEq ? `${tfTag}${type.toUpperCase()} $$` : label, x2 + 4, y2 - 4, {
          align: 'left', color, priority, key: o.id, ids,
        })
      }
      break
    }
    case 'arrow': {
      const [a, b] = o.points
      if (a.time && b.time) {
        // Relationship arrow between two real chart coordinates.
        const ax = timeToX(geom, a.time)
        const bx = timeToX(geom, b.time)
        if (ax === null || bx === null) break
        const ay = getY(a.price)
        const by = getY(b.price)
        ctx.setLineDash([3, 3])
        ctx.beginPath(); ctx.moveTo(ax, ay); ctx.lineTo(bx, by); ctx.stroke()
        ctx.setLineDash([])
        drawLineArrow(ctx, ax, ay, bx, by)
        break
      }
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
      placeLabel(geom, label, x - 8, y2 + (y2 < y1 ? -10 : 10), { color, tag: true, priority: 3, key: o.id, ids })
      break
    }
    case 'callout': {
      const ax = timeToX(geom, o.time_start) ?? right - 4
      const ay = getY(o.price)
      const text = `${tfTag}${o.name}`
      placeLabel(geom, text, ax - 14, ay - 12, {
        kind: 'callout', color, priority: o.meta?.priority >= 2 ? 2 : 1, key: o.id,
        anchor: { x: ax, y: ay }, ids: o.meta?.sources || ids,
      })
      geom.labelReqs[geom.labelReqs.length - 1].owner = o
      break
    }
    case 'scenario': {
      // The engine gives trigger + invalidation LEVELS only (no time, no path),
      // so no trajectory is drawn: trigger area, direction marker, invalidation
      // line and the required condition, in the projection space after the
      // last candle. Clearly separate from historical candles.
      if (!geom.future) break
      const tier = SCENARIO_TIER_STYLE[o.meta?.tier] || SCENARIO_TIER_STYLE.secondary
      const factor = o.meta?.muted ? MUTED_FACTOR : 1
      const lastIdx = geom.allCandles.length - 1
      const x0 = indexToX(geom, lastIdx) + geom.candleSpacing
      const xm = indexToX(geom, lastIdx + Math.max(2, geom.future - 3))
      const [, b] = o.points
      const y1 = getY(b.price)
      ctx.globalAlpha *= tier.alpha * factor
      ctx.lineWidth = tier.width
      // Projection-space divider (conditional area starts here).
      ctx.save(); ctx.globalAlpha *= 0.4; ctx.setLineDash([1, 4])
      ctx.beginPath(); ctx.moveTo(x0 - geom.candleSpacing / 2, padding.top); ctx.lineTo(x0 - geom.candleSpacing / 2, geom.height - padding.bottom); ctx.stroke()
      ctx.restore()
      // Trigger area: band at the trigger level.
      const base = ctx.globalAlpha
      ctx.fillStyle = FILL_COLOR[o.color] || color
      ctx.globalAlpha = Math.min(1, base * 0.22 * (FILL_GAIN[o.color] ?? 1))
      ctx.fillRect(x0, y1 - 4, right - x0, 8)
      ctx.globalAlpha = base
      ctx.fillStyle = color
      ctx.setLineDash([4, 3])
      ctx.beginPath(); ctx.moveTo(x0, y1); ctx.lineTo(right, y1); ctx.stroke()
      ctx.setLineDash([])
      // Direction marker supported by the scenario's own direction.
      const dir = o.color === 'bearish' ? 1 : -1
      ctx.beginPath()
      ctx.moveTo(xm - 5, y1 + dir * 6); ctx.lineTo(xm, y1 + dir * 14); ctx.lineTo(xm + 5, y1 + dir * 6)
      ctx.stroke()
      const inval = o.meta?.invalidation_price
      if (typeof inval === 'number') {
        const yi = getY(inval)
        ctx.setLineDash([1, 3])
        ctx.beginPath(); ctx.moveTo(x0, yi); ctx.lineTo(right, yi); ctx.stroke()
        ctx.setLineDash([])
        placeLabel(geom, `✕ invalid beyond ${fmt(inval)}`, right - 4, yi - 3, { color, priority: 1, key: `${o.id}:inval`, ids })
      }
      const strong = o.meta?.tier === 'primary' || o.meta?.tier === 'unranked'
      const conv = o.meta?.conviction ? ` · ${String(o.meta.conviction).toUpperCase()}` : ''
      placeLabel(geom, `${tier.label} · ${o.name}${conv}`, right - 4, y1 + (dir > 0 ? -8 : 16), {
        color, tag: strong && !o.meta?.muted, priority: strong ? 3 : 1, key: o.id, ids,
      })
      const needs = o.meta?.trigger ? String(o.meta.trigger).replace(/_/g, ' ') : `trigger ${fmt(b.price)}`
      placeLabel(geom, `requires: ${needs.length > 60 ? `${needs.slice(0, 57)}…` : needs}`, right - 4, y1 + (dir > 0 ? -22 : 30), {
        color, priority: strong ? 2 : 1, key: `${o.id}:needs`, ids, font: '9px sans-serif',
      })
      item.seg = [x0, y1, right, y1]
      break
    }
    case 'marker': {
      const x = timeToX(geom, o.time_start)
      if (x === null) break
      const y = getY(o.price)
      const up = o.position !== 'below'
      if (o.shape === 'circle') {
        // Sweep: ring on the actual sweep candle wick.
        ctx.beginPath()
        ctx.arc(x, y, 7, 0, Math.PI * 2)
        ctx.stroke()
        ctx.beginPath()
        ctx.arc(x, y, 2, 0, Math.PI * 2)
        ctx.fill()
      } else {
        const ty = up ? y - 4 : y + 4
        ctx.beginPath()
        ctx.moveTo(x, ty)
        ctx.lineTo(x - 3.5, ty + (up ? -6 : 6))
        ctx.lineTo(x + 3.5, ty + (up ? -6 : 6))
        ctx.closePath()
        ctx.fill()
      }
      if (!minimal || highlighted || (item.swingRank ?? 0) < 2 || o.shape === 'circle') {
        placeLabel(geom, label, x, up ? y - 12 : y + 19, {
          align: 'center', color, priority: o.shape === 'circle' ? 2 : (item.swingRank ?? 0) < 2 ? 2 : 1, key: o.id, ids,
          font: highlighted ? 'bold 10px monospace' : '9px monospace',
        })
      }
      break
    }
    case 'label': {
      const y = getY(o.price)
      placeLabel(geom, label, right - 4, y, { color, tag: true, priority: 3, key: o.id, ids })
      const blocker = o.meta?.blockers?.[0]
      if (blocker) {
        placeLabel(geom, blocker.length > 70 ? `${blocker.slice(0, 67)}…` : blocker, right - 4, y + 15, {
          color, font: '9px sans-serif', priority: 2, key: `${o.id}:blocker`, ids,
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
        placeLabel(geom, `${name} ${fmt(price)}`, x1 + 2, y - 4, { align: 'left', color: c, tag: true, priority: 3, key: `${o.id}:${name}`, ids })
      }
      placeLabel(geom, `${label}${o.rr ? ` · RR ${o.rr}` : ''}`, right - 2, yEntry + 14, {
        color: OVERLAY_COLORS.entry, tag: true, priority: 3, key: `${o.id}:rr`, ids,
      })
      break
    }
    default:
      break
  }

  // Lifecycle markers.
  if (style.marker === 'invalid' && typeof o.price === 'number') {
    placeLabel(geom, '✕ invalidated', right - 4, getY(o.price) + 11, { color, priority: 1, key: `${o.id}:invalid`, ids })
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
  return (highlightedIds.has(item.overlay.id) ? 10 : 0) + (item.htf ? 0 : 5)
    + (item.overlay.layer === 'premium_discount' ? -3 : 0) + (item.overlay.kind === 'scenario' ? 8 : 0)
}

// Confluence: overlapping drawn objects (chartVisuals.buildConfluence). Drawn
// as a combined band with a double gold border; members stay selectable.
const CONFLUENCE_COLOR = '#C9A227'

function drawConfluence(geom, groups) {
  const { ctx, padding, width, getY, chartMin, chartMax } = geom
  const right = width - padding.right
  for (const g of groups) {
    if (g.price_high < chartMin || g.price_low > chartMax) continue
    const x1 = timeToX(geom, g.time_start) ?? padding.left
    let yTop = getY(g.price_high)
    let yBottom = getY(g.price_low)
    if (yBottom - yTop < 4) {
      const mid = (yTop + yBottom) / 2
      yTop = mid - 2
      yBottom = mid + 2
    }
    ctx.save()
    ctx.globalAlpha = isStale.value ? 0.5 : 1
    ctx.fillStyle = CONFLUENCE_COLOR
    ctx.globalAlpha *= 0.12
    ctx.fillRect(x1, yTop, right - x1, yBottom - yTop)
    ctx.globalAlpha = isStale.value ? 0.5 : 0.9
    ctx.strokeStyle = CONFLUENCE_COLOR
    ctx.lineWidth = 1
    ctx.strokeRect(x1, yTop, right - x1, yBottom - yTop)
    ctx.strokeRect(x1 + 2, yTop + 2, Math.max(0, right - x1 - 4), Math.max(0, yBottom - yTop - 4))
    ctx.restore()
    const pseudo = {
      id: g.id, visualOnly: 'confluence', kind: 'zone', timeframe: g.timeframes.join(','),
      name: `Confluence · ${g.count} objects`, status: g.statuses.join('/'),
      price_low: g.price_low, price_high: g.price_high, time_start: g.time_start,
      meta: {
        text: `${g.types.join(' + ')} · ${g.timeframes.join(', ')} · ${g.direction}`,
      },
      memberIds: g.memberIds,
    }
    geom.hits.push({ o: pseudo, type: 'rect', l: x1, r: right, t: yTop, b: yBottom, priority: 1 })
    placeLabel(geom, confluenceLabel(g), right - 4, yBottom + 11, {
      color: CONFLUENCE_COLOR, priority: 2, key: g.id, ids: g.memberIds, font: 'bold 9px monospace',
    })
  }
}

function drawOverlays(geom, items, phase) {
  const { ctx, width, height, padding, chartMin, chartMax } = geom
  const highlightedIds = new Set(chartStore.highlightIds)
  const top = padding.top
  const bottom = height - padding.bottom
  const offscreen = []

  ctx.save()
  ctx.beginPath()
  ctx.rect(padding.left, top, width - padding.right - padding.left, bottom - top)
  ctx.clip()

  if (phase === 'under') {
    geom.consolidated = new Set()
    if (tfPrefs.value.confluence) {
      const groups = buildConfluence(items, overlayType)
      // Zone consolidation: members are dimmed under one unified band instead of
      // stacking indistinguishable rectangles; their boundaries are unchanged.
      for (const g of groups) g.memberIds.forEach((id) => geom.consolidated.add(id))
      drawConfluence(geom, groups)
    }
  }

  const ordered = items
    .filter((item) => (item.overlay.kind === 'zone') === (phase === 'under'))
    .sort((a, b) => drawPriority(a, highlightedIds) - drawPriority(b, highlightedIds))

  for (const item of ordered) {
    const o = item.overlay
    const highlighted = highlightedIds.has(o.id)
    const prices = overlayPrices(o)
    if (o.kind !== 'scenario' && prices.length && prices.every((p) => p > chartMax || p < chartMin)) {
      if (highlighted || o.layer === 'trade_plan') offscreen.push(o)
      continue
    }

    const color = OVERLAY_COLORS[o.color] || OVERLAY_COLORS.neutral
    const oldSwing = (item.swingRank ?? 0) >= 2
    item.style = lifecycleStyle(o.status, { historical: oldSwing && !highlighted })
    ctx.save()
    ctx.globalAlpha = item.style.alpha * (isStale.value ? 0.5 : 1) * (item.htf ? 0.6 : 1) * (highlighted ? 1 : 0.92)
    ctx.strokeStyle = color
    ctx.fillStyle = color
    ctx.lineWidth = highlighted ? 2.4 : item.htf ? 1 : item.style.width
    // HTF references: long dashes; lifecycle dash otherwise.
    ctx.setLineDash(item.htf ? [8, 4] : item.style.dash)
    if (highlighted) {
      ctx.shadowColor = color
      ctx.shadowBlur = 8
    }
    drawOverlay(geom, item, highlighted)
    registerHit(geom, item)
    ctx.restore()
  }
  ctx.restore()

  if (phase === 'over') {
    // Highlighted objects outside the visible price range: edge tags instead of
    // silently dropping them (the chart range is never stretched by overlays).
    for (const o of offscreen.slice(0, 4)) {
      const above = overlayPrices(o)[0] > chartMax
      placeLabel(
        geom,
        `${above ? '▲' : '▼'} ${o.name} ${fmtPrice(overlayPrices(o)[0])}`,
        width - padding.right - 4,
        above ? top + 14 : bottom - 4,
        { color: OVERLAY_COLORS[o.color] || OVERLAY_COLORS.neutral, tag: true, priority: 3, key: `edge:${o.id}`, ids: [o.id] }
      )
    }
    flushLabels(geom)
  }
}

// Hit areas recorded while drawing (canvas has no DOM per object).
function registerHit(geom, item) {
  const o = item.overlay
  const { getY, padding, width } = geom
  const right = width - padding.right
  const add = (shape) => geom.hits.push({ o, ...shape })
  switch (o.kind) {
    case 'zone': {
      const x1 = timeToX(geom, o.time_start) ?? padding.left
      add({ type: 'rect', l: x1, r: right, t: getY(o.price_high), b: getY(o.price_low) })
      break
    }
    case 'hline':
      add({ type: 'seg', x1: timeToX(geom, o.time_start) ?? padding.left, y1: getY(o.price), x2: timeToX(geom, o.time_end) ?? right, y2: getY(o.price) })
      break
    case 'trendline':
    case 'arrow': {
      const [a, b] = o.points
      const x1 = timeToX(geom, a.time)
      const x2 = timeToX(geom, b.time)
      if (x1 !== null && x2 !== null) add({ type: 'seg', x1, y1: getY(a.price), x2, y2: getY(b.price) })
      break
    }
    case 'scenario':
      if (item.seg) add({ type: 'seg', x1: item.seg[0], y1: item.seg[1], x2: item.seg[2], y2: item.seg[3] })
      break
    case 'callout':
      break // hit area added when the callout box is placed (flushLabels)
    case 'marker': {
      const x = timeToX(geom, o.time_start)
      if (x !== null) add({ type: 'pt', x, y: getY(o.price), priority: 2 })
      break
    }
    case 'label':
    case 'position':
      add({ type: 'seg', x1: right - 160, y1: getY(o.price ?? o.entry), x2: right, y2: getY(o.price ?? o.entry), priority: 2 })
      break
    default:
      break
  }
}

function hitTest(x, y) {
  if (!lastGeom) return null
  let best = null
  for (const h of lastGeom.hits) {
    let d = Infinity
    if (h.type === 'rect') {
      const t = Math.min(h.t, h.b)
      const b = Math.max(h.t, h.b)
      d = x >= h.l && x <= h.r && y >= t - 2 && y <= b + 2 ? 0.5 : Infinity
    } else if (h.type === 'pt') {
      d = Math.hypot(x - h.x, y - h.y) <= 8 ? Math.hypot(x - h.x, y - h.y) / 8 : Infinity
    } else {
      const dx = h.x2 - h.x1
      const dy = h.y2 - h.y1
      const len2 = dx * dx + dy * dy || 1
      const u = Math.max(0, Math.min(1, ((x - h.x1) * dx + (y - h.y1) * dy) / len2))
      const dist = Math.hypot(x - (h.x1 + u * dx), y - (h.y1 + u * dy))
      d = dist <= 5 ? dist / 5 : Infinity
    }
    if (d === Infinity) continue
    const score = d - (h.priority || 0)
    if (!best || score < best.score) best = { o: h.o, score }
  }
  return best?.o || null
}

function canvasPoint(e) {
  const rect = canvasRef.value.getBoundingClientRect()
  return { x: e.clientX - rect.left, y: e.clientY - rect.top }
}

function handleMouseDown(e) {
  if (!lastGeom || e.button !== 0) return
  drag.active = true
  drag.moved = false
  drag.startX = e.clientX
  drag.startIndex = lastGeom.start
}

function handleMouseUp(e) {
  const wasDrag = drag.moved
  drag.active = false
  if (wasDrag || !canvasRef.value) return
  // Click: select an object (callouts highlight their source objects).
  const { x, y } = canvasPoint(e)
  const o = hitTest(x, y)
  selected.value = o
  if (!o) return
  const known = new Set(allOverlays().map((q) => q.id))
  if (o.memberIds) {
    // Confluence / grouped labels: highlight the underlying objects individually.
    chartStore.highlightIds = o.memberIds.filter((id) => known.has(id))
    return
  }
  const sources = (o.meta?.sources || []).filter((id) => known.has(id))
  chartStore.highlightIds = o.kind === 'callout' && sources.length ? sources : [o.id]
}

function handleMouseMove(e) {
  const canvas = canvasRef.value
  if (!canvas || !candles.value.length || !lastGeom) return
  const { x, y } = canvasPoint(e)

  if (drag.active) {
    const shift = Math.round((drag.startX - e.clientX) / lastGeom.candleSpacing)
    if (shift !== 0) drag.moved = true
    const size = Math.min(view.value.size, candles.value.length)
    const latestStart = candles.value.length - size
    const start = Math.max(0, Math.min(latestStart, drag.startIndex + shift))
    const anchor = start >= latestStart ? null : candles.value[start].time_utc
    if (anchor !== view.value.anchor) view.value = { size, anchor }
    return
  }

  mousePos.value = { x, y }
  const idx = xToIndex(lastGeom, x)
  hoveredCandle.value = idx >= 0 && idx < candles.value.length && idx >= lastGeom.start ? candles.value[idx] : null
  renderChart()
  const o = hitTest(x, y)
  hoverInfo.value = o ? { o, x, y } : null
}

function handleWheel(e) {
  if (!lastGeom || !candles.value.length) return
  // Zoom around the candle under the cursor; it stays at the same screen spot.
  const { x } = canvasPoint(e)
  const pivot = xToIndex(lastGeom, x)
  const total = candles.value.length
  const size = Math.max(15, Math.min(total, Math.round(view.value.size * (e.deltaY > 0 ? 1.15 : 0.87))))
  const frac = (pivot - lastGeom.start) / Math.max(1, Math.min(view.value.size, total))
  const latestStart = total - size
  const start = Math.max(0, Math.min(latestStart, Math.round(pivot - frac * size)))
  view.value = { size, anchor: start >= latestStart ? null : candles.value[start].time_utc }
}

function handleMouseLeave() {
  drag.active = false
  mousePos.value = { x: -1, y: -1 }
  hoveredCandle.value = null
  hoverInfo.value = null
  renderChart()
}

function describe(o) {
  if (o.visualOnly) return `${o.timeframe} · ${o.status} · visual grouping`
  const parts = [`${o.timeframe}`, o.status, sourceOf(o)]
  if (o.meta?.tier) parts.push(`${o.meta.tier} priority (${(o.meta.rank_reasons || []).join(', ') || 'equal'})`)
  return parts.filter(Boolean).join(' · ')
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
        <span>O: <strong class="font-mono">{{ fmtPrice(hoveredCandle.open) }}</strong></span> &nbsp;
        <span>H: <strong class="font-mono">{{ fmtPrice(hoveredCandle.high) }}</strong></span> &nbsp;
        <span>L: <strong class="font-mono">{{ fmtPrice(hoveredCandle.low) }}</strong></span> &nbsp;
        <span>C: <strong class="font-mono" :class="hoveredCandle.close >= hoveredCandle.open ? 'text-green' : 'text-red'">{{ fmtPrice(hoveredCandle.close) }}</strong></span>
      </div>
      <div v-else class="text-muted">
        <span>Hover over candles to view bar data.</span>
      </div>

      <div class="text-muted text-xs">
        <span title="Mouse wheel: zoom · drag: pan · double-click: back to latest · click an object: details">
          Wheel zoom · drag pan · dbl-click reset ·
        </span>
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
          <select v-model="objectFilter.source" class="mini-select" aria-label="Source filter">
            <option value="all">All sources</option>
            <option value="detected">Detected</option>
            <option value="callout">Callouts / arrows</option>
            <option value="scenario">Conditional scenarios</option>
            <option value="ai">AI annotations</option>
          </select>
          <select v-model="objectFilter.visibility" class="mini-select" aria-label="Visibility filter">
            <option :value="undefined">Drawn + not drawn</option>
            <option value="drawn">Drawn only</option>
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
            <span class="text-xs text-muted">{{ r.o.status }} · {{ r.source }}</span>
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
      @mousedown="handleMouseDown"
      @mouseup="handleMouseUp"
      @mouseleave="handleMouseLeave"
      @wheel.prevent="handleWheel"
      @dblclick="resetView"
    >
      <canvas ref="canvasRef" class="trading-canvas"></canvas>
      <div
        v-if="hoverInfo"
        class="chart-tooltip"
        :style="{ left: `${Math.max(4, hoverInfo.x - 230)}px`, top: `${hoverInfo.y + 14}px` }"
      >
        <strong>{{ hoverInfo.o.name }}</strong>
        <span class="text-muted">{{ describe(hoverInfo.o) }}</span>
        <span class="font-mono">{{ objectPrice(hoverInfo.o) }}</span>
        <span v-if="hoverInfo.o.meta?.text" class="text-muted">{{ hoverInfo.o.meta.text }}</span>
      </div>
    </div>

    <!-- Selected object details (click on the chart) -->
    <div v-if="selected" class="object-details text-xs">
      <span class="font-bold">{{ selected.name }}</span>
      <span class="badge badge-neutral badge-sm">{{ selected.timeframe }}</span>
      <span>{{ selected.status }}</span>
      <span class="font-mono">{{ objectPrice(selected) }}</span>
      <span class="text-muted">{{ objectTime(selected) }}</span>
      <span class="text-muted">source: {{ selected.source }}</span>
      <span v-if="selected.meta?.text" class="text-muted">· {{ selected.meta.text }}</span>
      <span v-if="selected.meta?.blockers?.length" class="text-muted">· {{ selected.meta.blockers[0] }}</span>
      <span class="details-actions">
        <button v-if="!selected.visualOnly" class="btn btn-secondary btn-sm" @click="toggleHidden(selected.id); selected = null">Hide</button>
        <button class="btn btn-secondary btn-sm" @click="selected = null">Close</button>
      </span>
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

.canvas-container {
  position: relative;
  cursor: crosshair;
}

.chart-tooltip {
  position: absolute;
  z-index: 15;
  width: 220px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 6px 8px;
  font-size: 11px;
  background: var(--bg-surface);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  box-shadow: var(--shadow-md);
  pointer-events: none;
}

.object-details {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  padding: 6px 16px;
  border-top: 1px solid var(--border-main);
}

.details-actions {
  display: inline-flex;
  gap: 4px;
  margin-left: auto;
}

.overlay-notes {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 4px 16px;
}
</style>
