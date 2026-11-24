/**
 * Chart overlay store shared by the chart and the AI chat.
 *
 * - "engine" overlays come from the analysis response (chart_overlays). They
 *   are deterministic, recomputed every refresh, and replaced as a whole.
 * - "annotations" come from AI chat commands. They are upserted by id and kept
 *   until the user clears them; a new chat message never wipes them.
 * Every overlay is validated before it can reach the canvas.
 */
import { reactive } from 'vue'

export const TIMEFRAMES = ['M1', 'M5', 'M15', 'M30', 'H1', 'H4', 'D1']

export const LAYERS = [
  { id: 'structure', label: 'Market Structure' },
  { id: 'fvg', label: 'FVG' },
  { id: 'order_blocks', label: 'Order Blocks' },
  { id: 'liquidity', label: 'Liquidity' },
  { id: 'trendline', label: 'Trendline' },
  { id: 'sr', label: 'Support & Resistance' },
  { id: 'premium_discount', label: 'Premium & Discount' },
  { id: 'trade_plan', label: 'Trade Plan' },
]

const KINDS = new Set(['hline', 'zone', 'trendline', 'arrow', 'marker', 'label', 'position'])
const COLORS = new Set(['bullish', 'bearish', 'neutral', 'info', 'warning', 'entry', 'stop', 'target'])
const STATUSES = new Set([
  'active', 'confirmed', 'candidate', 'potential', 'waiting',
  'invalidated', 'mitigated', 'taken', 'broken', 'expired',
])
const LAYER_IDS = new Set(LAYERS.map((l) => l.id))
const OVERLAY_TFS = new Set([...TIMEFRAMES, 'MTF'])

// Analysis older than this is drawn faded and flagged STALE.
export const STALE_AFTER_MS = 5 * 60 * 1000

const PREFS_KEY = 'quantterminal_chart_layers'

function isPrice(value) {
  return typeof value === 'number' && Number.isFinite(value) && value > 0
}

export function validateOverlay(o) {
  if (!o || typeof o !== 'object') return false
  if (typeof o.id !== 'string' || !o.id || typeof o.symbol !== 'string' || !o.symbol) return false
  if (!OVERLAY_TFS.has(o.timeframe) || !LAYER_IDS.has(o.layer) || !KINDS.has(o.kind)) return false
  if (!COLORS.has(o.color) || (o.status && !STATUSES.has(o.status))) return false

  const prices = ['price', 'price_low', 'price_high', 'entry', 'stop', 'target']
    .map((k) => o[k])
    .concat((o.points || []).map((p) => p?.price))
    .filter((v) => v !== undefined && v !== null)
  if (!prices.every(isPrice)) return false

  switch (o.kind) {
    case 'hline':
    case 'marker':
    case 'label':
      return isPrice(o.price)
    case 'zone':
      return isPrice(o.price_low) && isPrice(o.price_high) && o.price_low < o.price_high
    case 'trendline':
    case 'arrow':
      return Array.isArray(o.points) && o.points.length === 2
    case 'position':
      return isPrice(o.entry) && isPrice(o.stop)
    default:
      return false
  }
}

export const chartStore = reactive({
  symbol: '',
  analysisId: '',
  generatedAt: null,
  engine: {},
  annotations: {},
  highlightIds: [],
  lastCommand: null,
  rejected: 0,
})

function toMap(list, symbol) {
  const map = {}
  for (const o of list || []) {
    if (o?.symbol === symbol && validateOverlay(o)) {
      map[o.id] = o
    } else {
      chartStore.rejected += 1
    }
  }
  return map
}

export function resetForSymbol(symbol) {
  chartStore.symbol = symbol
  chartStore.analysisId = ''
  chartStore.generatedAt = null
  chartStore.engine = {}
  chartStore.annotations = {}
  chartStore.highlightIds = []
  chartStore.lastCommand = null
}

/** Engine overlays from GET /analysis (action "replace"). */
export function applyOverlayPayload(payload, symbol) {
  if (!payload || payload.type !== 'chart_overlay' || payload.symbol !== symbol) return
  if (chartStore.symbol !== symbol) resetForSymbol(symbol)

  // Never let an older snapshot overwrite a newer one.
  const incoming = Date.parse(payload.generated_at_utc || '')
  const current = Date.parse(chartStore.generatedAt || '')
  if (Number.isFinite(current) && Number.isFinite(incoming) && incoming < current) return

  chartStore.engine = toMap(payload.overlays, symbol)
  chartStore.analysisId = payload.analysis_id || ''
  chartStore.generatedAt = payload.generated_at_utc || null
  // Drop highlights that no longer exist.
  chartStore.highlightIds = chartStore.highlightIds.filter(
    (id) => chartStore.engine[id] || chartStore.annotations[id]
  )
}

/** Commands from the chat response: create/update (upsert), highlight, clear. */
export function applyChartCommand(command, symbol) {
  if (!command || command.type !== 'chart_command' || command.symbol !== symbol) return null
  if (command.overlay_payload) applyOverlayPayload(command.overlay_payload, symbol)

  const summary = { highlighted: 0, created: [], cleared: false, offTimeframe: [] }
  for (const op of command.operations || []) {
    if (op.op === 'clear') {
      clearAiDrawings()
      summary.cleared = true
    } else if (op.op === 'create' || op.op === 'update') {
      const next = { ...chartStore.annotations, ...toMap(op.overlays, symbol) }
      chartStore.annotations = next
      summary.created.push(...(op.overlays || []).filter((o) => next[o.id]).map((o) => o.name))
    } else if (op.op === 'highlight') {
      const ids = (op.ids || []).filter((id) => chartStore.engine[id] || chartStore.annotations[id])
      chartStore.highlightIds = ids
      summary.highlighted = ids.length
    }
  }
  chartStore.lastCommand = {
    ...summary,
    intents: command.intents || [],
    blockers: command.blockers || [],
    notes: command.notes || [],
  }
  return chartStore.lastCommand
}

export function clearAiDrawings() {
  chartStore.annotations = {}
  chartStore.highlightIds = []
}

export function highlightLatest(activeTf) {
  chartStore.highlightIds = Object.values(chartStore.engine)
    .filter((o) => o.meta?.key && (o.timeframe === activeTf || o.timeframe === 'MTF'))
    .map((o) => o.id)
}

function tfRank(tf) {
  return TIMEFRAMES.indexOf(tf)
}

/**
 * Which overlays belong on a chart of `activeTf`.
 * - same timeframe: drawn normally
 * - MTF (trade plan, chat annotations): always
 * - higher timeframe S/R and premium/discount: as HTF reference
 * - higher timeframe FVG/OB/liquidity: as HTF reference only if enabled
 * - lower timeframe objects: never (an M5 object is not an H1 object)
 */
export function visibleOverlays(activeTf, prefs) {
  const all = [...Object.values(chartStore.engine), ...Object.values(chartStore.annotations)]
  const out = []
  for (const o of all) {
    if (!prefs.layers[o.layer]) continue
    if (o.timeframe === activeTf || o.timeframe === 'MTF') {
      out.push({ overlay: o, htf: false })
      continue
    }
    if (tfRank(o.timeframe) <= tfRank(activeTf)) continue
    if (['sr', 'premium_discount'].includes(o.layer)) {
      out.push({ overlay: o, htf: true })
    } else if (prefs.showHtf && ['fvg', 'order_blocks', 'liquidity'].includes(o.layer)) {
      out.push({ overlay: o, htf: true })
    }
  }
  return out
}

export function highlightedTimeframes(activeTf) {
  const tfs = new Set()
  for (const id of chartStore.highlightIds) {
    const o = chartStore.engine[id] || chartStore.annotations[id]
    if (o && o.timeframe !== 'MTF' && o.timeframe !== activeTf) tfs.add(o.timeframe)
  }
  return [...tfs].sort((a, b) => tfRank(a) - tfRank(b))
}

export function loadLayerPrefs() {
  const defaults = {
    layers: Object.fromEntries(LAYERS.map((l) => [l.id, ['structure', 'fvg', 'order_blocks', 'liquidity', 'sr', 'trade_plan'].includes(l.id)])),
    showHtf: false,
  }
  try {
    const saved = JSON.parse(localStorage.getItem(PREFS_KEY) || 'null')
    if (saved && typeof saved === 'object') {
      return {
        layers: { ...defaults.layers, ...(saved.layers || {}) },
        showHtf: Boolean(saved.showHtf),
      }
    }
  } catch {
    // Corrupt preference value: fall back to defaults without touching other keys.
  }
  return defaults
}

export function saveLayerPrefs(prefs) {
  try {
    localStorage.setItem(PREFS_KEY, JSON.stringify(prefs))
  } catch {
    // Storage full/blocked: preferences simply are not persisted.
  }
}
