/**
 * Chart overlay store shared by the chart, the Layer/Object managers and the AI chat.
 *
 * Three separate object sources (never mixed):
 * - "engine": deterministic objects from GET /analysis (chart_overlays). Replaced
 *   as a whole on every analysis refresh.
 * - "keyZones": supply/demand zones the engine already returns in
 *   key_levels.supply_zones / demand_zones (analysis/levels.py). Converted for
 *   display only; nothing is detected here.
 * - "annotations": AI chat commands, upserted by id, kept until cleared.
 *
 * Visibility (presets, per-timeframe toggles, relevance, HTF, individual hide)
 * only decides what is drawn. It never alters or deletes a detection result.
 */
import { reactive } from 'vue'

export const TIMEFRAMES = ['M1', 'M5', 'M15', 'M30', 'H1', 'H4', 'D1']

// Kept for compatibility with v1 preferences and the backend `layer` field.
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

// Layer Manager catalog. `unsupported` lists items the engine does not detect.
export const CATEGORIES = [
  { id: 'structure', label: 'Market Structure', types: [
    { id: 'HH', label: 'HH' }, { id: 'HL', label: 'HL' }, { id: 'LH', label: 'LH' }, { id: 'LL', label: 'LL' },
    { id: 'swing', label: 'First swing (unlabelled)' },
  ] },
  { id: 'events', label: 'Structure Events', types: [
    { id: 'bos', label: 'BOS' }, { id: 'choch', label: 'CHoCH / MSS (candidate)' },
  ] },
  { id: 'imbalance', label: 'Imbalance', types: [{ id: 'fvg', label: 'FVG' }],
    unsupported: ['IFVG', 'BPR', 'Volume Imbalance'] },
  { id: 'liquidity', label: 'Liquidity', types: [
    { id: 'bsl', label: 'BSL' }, { id: 'ssl', label: 'SSL' }, { id: 'eqh', label: 'EQH' },
    { id: 'eql', label: 'EQL' }, { id: 'sweep', label: 'Liquidity Sweep' },
  ] },
  { id: 'institutional', label: 'Institutional Zones', types: [{ id: 'ob', label: 'Order Block' }],
    unsupported: ['Breaker Block', 'Mitigation Block'] },
  { id: 'trend', label: 'Trend Analysis', types: [{ id: 'trendline', label: 'Trendline' }],
    unsupported: ['Trend Channel'] },
  { id: 'zones', label: 'Price Zones', types: [
    { id: 'premium', label: 'Premium' }, { id: 'eq', label: 'Equilibrium' }, { id: 'discount', label: 'Discount' },
  ] },
  { id: 'sr', label: 'Support & Resistance', types: [
    { id: 'support', label: 'Support' }, { id: 'resistance', label: 'Resistance' },
    { id: 'supply', label: 'Supply' }, { id: 'demand', label: 'Demand' },
  ] },
  { id: 'plan', label: 'Trade Plan', types: [{ id: 'plan', label: 'Trade Plan / WAITING' }] },
]

export const ALL_TYPES = CATEGORIES.flatMap((c) => c.types.map((t) => t.id))

export const HTF_GROUPS = [
  { id: 'structure', label: 'HTF Structure (BOS/CHoCH)', types: ['bos', 'choch'] },
  { id: 'fvg', label: 'HTF FVG', types: ['fvg'] },
  { id: 'ob', label: 'HTF Order Block', types: ['ob'] },
  { id: 'trendline', label: 'HTF Trendline', types: ['trendline'] },
  { id: 'sr', label: 'HTF S/R & Premium/Discount', types: ['support', 'resistance', 'supply', 'demand', 'premium', 'eq', 'discount'] },
]

const KINDS = new Set(['hline', 'zone', 'trendline', 'arrow', 'marker', 'label', 'position'])
const COLORS = new Set(['bullish', 'bearish', 'neutral', 'info', 'warning', 'entry', 'stop', 'target'])
const STATUSES = new Set([
  'active', 'confirmed', 'candidate', 'potential', 'waiting',
  'invalidated', 'mitigated', 'taken', 'broken', 'expired',
])
export const LIVE_STATUSES = new Set(['active', 'confirmed', 'candidate', 'waiting', 'potential'])
export const HISTORICAL_STATUSES = new Set(['mitigated', 'taken', 'broken', 'expired', 'invalidated'])
const LAYER_IDS = new Set(LAYERS.map((l) => l.id))
const OVERLAY_TFS = new Set([...TIMEFRAMES, 'MTF'])

// Analysis older than this is drawn faded and flagged STALE.
export const STALE_AFTER_MS = 5 * 60 * 1000

const PREFS_V1_KEY = 'quantterminal_chart_layers' // read only (migration)
const PREFS_KEY = 'quantterminal_chart_layers_v2'

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

/** Object type from the deterministic id: "<symbol>:<tf>:<kind>:<...>". */
export function overlayType(o) {
  const parts = o.id.split(':')
  const kind = parts[2]
  const sub = parts[3]
  switch (kind) {
    case 'swing': return ['HH', 'HL', 'LH', 'LL'].includes(o.name) ? o.name : 'swing'
    case 'break': return sub === 'choch' ? 'choch' : 'bos'
    case 'fvg': return 'fvg'
    case 'ob': return 'ob'
    case 'liq': return ['bsl', 'ssl', 'eqh', 'eql'].includes(sub) ? sub : 'bsl'
    case 'sweep': return 'sweep'
    case 'trend': return 'trendline'
    case 'pd': return { premium: 'premium', discount: 'discount', eq: 'eq' }[sub] || 'eq'
    case 'sr': return sub === 'supports' ? 'support' : 'resistance'
    case 'sd': return sub === 'supply' ? 'supply' : 'demand'
    case 'plan':
    case 'chat':
      return 'plan'
    default:
      return o.layer === 'trade_plan' ? 'plan' : 'swing'
  }
}

export function categoryOf(type) {
  return CATEGORIES.find((c) => c.types.some((t) => t.id === type))?.id || 'plan'
}

export const chartStore = reactive({
  symbol: '',
  activeTf: 'M5',
  analysisId: '',
  generatedAt: null,
  engine: {},
  keyZones: {},
  annotations: {},
  highlightIds: [],
  hiddenIds: [],
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
  chartStore.keyZones = {}
  chartStore.annotations = {}
  chartStore.highlightIds = []
  chartStore.hiddenIds = []
  chartStore.lastCommand = null
}

function knownId(id) {
  return Boolean(chartStore.engine[id] || chartStore.keyZones[id] || chartStore.annotations[id])
}

export function findOverlay(id) {
  return chartStore.engine[id] || chartStore.keyZones[id] || chartStore.annotations[id] || null
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
  chartStore.highlightIds = chartStore.highlightIds.filter(knownId)
}

/**
 * Supply/demand zones already computed by analysis/levels.py and returned in
 * key_levels. Display conversion only: price range, timeframe, freshness.
 */
export function applyKeyLevelZones(keyLevels, symbol) {
  if (!keyLevels || keyLevels.symbol && keyLevels.symbol !== symbol) return
  if (chartStore.symbol !== symbol) return
  const zones = []
  for (const [list, type] of [[keyLevels.supply_zones, 'supply'], [keyLevels.demand_zones, 'demand']]) {
    for (const z of list || []) {
      const tf = (z.timeframes || []).find((t) => TIMEFRAMES.includes(t))
      if (!tf) continue
      zones.push({
        id: `${symbol}:${tf}:sd:${type}:${z.low}-${z.high}`,
        symbol, timeframe: tf, layer: 'sr', kind: 'zone',
        name: type === 'supply' ? 'Supply' : 'Demand',
        color: type === 'supply' ? 'bearish' : 'bullish',
        status: z.is_fresh === false ? 'mitigated' : 'active',
        price_low: z.low, price_high: z.high,
        source: 'analysis.levels (key_levels)',
        meta: { touches: z.touches, fresh: z.is_fresh },
      })
    }
  }
  chartStore.keyZones = toMap(zones, symbol)
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
      const ids = (op.ids || []).filter(knownId)
      chartStore.highlightIds = ids
      summary.highlighted = ids.length
    }
  }
  chartStore.lastCommand = {
    ...summary,
    intents: command.intents || [],
    blockers: command.blockers || [],
    notes: command.notes || [],
    analysisId: command.analysis_id || '',
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

export function toggleHidden(id) {
  chartStore.hiddenIds = chartStore.hiddenIds.includes(id)
    ? chartStore.hiddenIds.filter((x) => x !== id)
    : [...chartStore.hiddenIds, id]
}

export function tfRank(tf) {
  return TIMEFRAMES.indexOf(tf)
}

export function allOverlays() {
  return [
    ...Object.values(chartStore.engine),
    ...Object.values(chartStore.keyZones),
    ...Object.values(chartStore.annotations),
  ]
}

function overlayPrices(o) {
  return [o.price, o.price_low, o.price_high, o.entry, o.stop, o.target]
    .concat((o.points || []).map((p) => p.price))
    .filter((p) => typeof p === 'number')
}

function inRange(o, range) {
  if (!range) return true
  const prices = overlayPrices(o)
  if (!prices.length) return true
  const lo = Math.min(...prices)
  const hi = Math.max(...prices)
  return hi >= range.min && lo <= range.max
}

/**
 * Which overlays are drawn on a chart of `activeTf`.
 *
 * Timeframe rule: own timeframe and MTF objects; higher-timeframe objects only
 * through the HTF toggles; lower-timeframe objects never.
 *
 * "Relevant Only" (documented method): status is live (active, confirmed,
 * candidate, waiting) AND the object's price span intersects the visible price
 * range AND, for swing labels, it is one of the two most recent swings of its
 * kind on that timeframe. HTF references always use this filter, and at most
 * two per type per timeframe are shown.
 *
 * "Show history" off hides mitigated / taken / broken objects and swing labels
 * older than the last four per kind.
 */
export function visibleOverlays(activeTf, prefs, range = null) {
  const tfPrefs = prefs.byTf[activeTf] || {}
  const hidden = new Set(chartStore.hiddenIds)
  const swingRank = new Map()
  const bySwingKind = {}
  for (const o of Object.values(chartStore.engine)) {
    if (o.id.split(':')[2] !== 'swing') continue
    const key = `${o.timeframe}:${o.meta?.swing_type}`
    ;(bySwingKind[key] ||= []).push(o)
  }
  for (const list of Object.values(bySwingKind)) {
    list.sort((a, b) => Date.parse(b.time_start) - Date.parse(a.time_start))
    list.forEach((o, i) => swingRank.set(o.id, i))
  }

  const out = []
  const htfCount = {}
  for (const o of allOverlays()) {
    if (hidden.has(o.id)) continue
    const type = overlayType(o)
    const own = o.timeframe === activeTf || o.timeframe === 'MTF'
    // Current-timeframe objects follow the per-timeframe type toggles; HTF
    // references follow only their own HTF toggles (separate controls).
    if (own && !tfPrefs[type]) continue

    const historical = HISTORICAL_STATUSES.has(o.status)
    const rank = swingRank.get(o.id)

    if (own) {
      if (!prefs.showHistory && (historical || (rank !== undefined && rank >= 4))) continue
      if (prefs.relevantOnly && o.timeframe !== 'MTF') {
        if (!LIVE_STATUSES.has(o.status) || !inRange(o, range)) continue
        if (rank !== undefined && rank >= 2) continue
      }
      out.push({ overlay: o, htf: false, type, swingRank: rank })
      continue
    }

    if (tfRank(o.timeframe) <= tfRank(activeTf)) continue
    const group = HTF_GROUPS.find((g) => g.types.includes(type))
    if (!group || !prefs.htf[group.id]) continue
    if (!LIVE_STATUSES.has(o.status) || !inRange(o, range)) continue
    const key = `${o.timeframe}:${type}`
    htfCount[key] = (htfCount[key] || 0) + 1
    if (htfCount[key] > 2) continue
    out.push({ overlay: o, htf: true, type, swingRank: rank })
  }
  return out
}

export function highlightedTimeframes(activeTf) {
  const tfs = new Set()
  for (const id of chartStore.highlightIds) {
    const o = findOverlay(id)
    if (o && o.timeframe !== 'MTF' && o.timeframe !== activeTf) tfs.add(o.timeframe)
  }
  return [...tfs].sort((a, b) => tfRank(a) - tfRank(b))
}

// ---------------------------------------------------------------------------
// Presets and per-timeframe defaults (visualization preferences only)
// ---------------------------------------------------------------------------

const ON = (tfs) => Object.fromEntries(TIMEFRAMES.map((tf) => [tf, tfs.includes(tf)]))
const ALL_TF = TIMEFRAMES
const FROM = (tf) => TIMEFRAMES.slice(TIMEFRAMES.indexOf(tf))

// Default visibility table (STANDARD): configurable, not a detection limit.
const STANDARD_TABLE = {
  HH: ALL_TF, HL: ALL_TF, LH: ALL_TF, LL: ALL_TF, swing: [],
  bos: ALL_TF, choch: ALL_TF,
  fvg: ALL_TF,
  ob: FROM('M5'),
  bsl: ALL_TF, ssl: ALL_TF, sweep: ALL_TF,
  eqh: FROM('M5'), eql: FROM('M5'),
  trendline: FROM('M30'),
  premium: FROM('M5'), eq: FROM('M5'), discount: FROM('M5'),
  support: FROM('M15'), resistance: FROM('M15'),
  supply: [], demand: [],
  plan: ALL_TF,
}

const CLEAN_TABLE = {
  ...Object.fromEntries(ALL_TYPES.map((t) => [t, []])),
  HH: ALL_TF, HL: ALL_TF, LH: ALL_TF, LL: ALL_TF,
  bos: ALL_TF, choch: ALL_TF,
  fvg: ALL_TF, ob: FROM('M5'),
  bsl: ALL_TF, ssl: ALL_TF, sweep: ALL_TF,
  support: FROM('M15'), resistance: FROM('M15'),
  plan: ALL_TF,
}

const FULL_TABLE = Object.fromEntries(ALL_TYPES.map((t) => [t, ALL_TF]))

export const PRESETS = {
  clean: { label: 'Clean', table: CLEAN_TABLE, relevantOnly: true, showHistory: false, labels: 'minimal',
    htf: { structure: false, fvg: false, ob: false, trendline: false, sr: true } },
  standard: { label: 'Standard', table: STANDARD_TABLE, relevantOnly: false, showHistory: false, labels: 'normal',
    htf: { structure: false, fvg: true, ob: true, trendline: false, sr: true } },
  full: { label: 'Full', table: FULL_TABLE, relevantOnly: false, showHistory: true, labels: 'normal',
    htf: { structure: true, fvg: true, ob: true, trendline: true, sr: true } },
}

export function presetPrefs(name) {
  const p = PRESETS[name] || PRESETS.standard
  const byTf = {}
  for (const tf of TIMEFRAMES) {
    byTf[tf] = Object.fromEntries(ALL_TYPES.map((t) => [t, (p.table[t] || []).includes(tf)]))
  }
  return {
    version: 2, preset: name, byTf,
    relevantOnly: p.relevantOnly, showHistory: p.showHistory, labels: p.labels, htf: { ...p.htf },
  }
}

const V1_LAYER_TYPES = {
  structure: ['HH', 'HL', 'LH', 'LL', 'swing', 'bos', 'choch'],
  fvg: ['fvg'], order_blocks: ['ob'],
  liquidity: ['bsl', 'ssl', 'eqh', 'eql', 'sweep'],
  trendline: ['trendline'], sr: ['support', 'resistance'],
  premium_discount: ['premium', 'eq', 'discount'], trade_plan: ['plan'],
}

export function loadLayerPrefs() {
  try {
    const saved = JSON.parse(localStorage.getItem(PREFS_KEY) || 'null')
    if (saved?.version === 2 && saved.byTf) {
      const base = presetPrefs(saved.preset || 'standard')
      for (const tf of TIMEFRAMES) base.byTf[tf] = { ...base.byTf[tf], ...(saved.byTf[tf] || {}) }
      return { ...base, ...saved, byTf: base.byTf, htf: { ...base.htf, ...(saved.htf || {}) } }
    }
  } catch {
    // Corrupt value: fall back to defaults without touching other keys.
  }

  const prefs = presetPrefs('standard')
  try {
    // One-time migration from v1: layers the user switched off stay off.
    const v1 = JSON.parse(localStorage.getItem(PREFS_V1_KEY) || 'null')
    for (const [layer, on] of Object.entries(v1?.layers || {})) {
      if (on !== false) continue
      for (const tf of TIMEFRAMES) for (const t of V1_LAYER_TYPES[layer] || []) prefs.byTf[tf][t] = false
    }
    if (v1?.showHtf) prefs.htf = { ...prefs.htf, fvg: true, ob: true }
  } catch {
    // ignore unreadable v1 preferences
  }
  return prefs
}

export function saveLayerPrefs(prefs) {
  try {
    localStorage.setItem(PREFS_KEY, JSON.stringify(prefs))
  } catch {
    // Storage full/blocked: preferences simply are not persisted.
  }
}
