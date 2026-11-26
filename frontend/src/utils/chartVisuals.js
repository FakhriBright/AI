/**
 * Chart visual intelligence: pure, deterministic functions used by the chart
 * renderer. They only INTERPRET existing analysis objects and scenario
 * metadata for display. Nothing here detects, re-scores or changes analysis:
 * no new signals, no new scenarios, no probability numbers.
 */

// ---------------------------------------------------------------------------
// 1. Lifecycle style map (only statuses that exist in the overlay contract)
// ---------------------------------------------------------------------------
export const LIFECYCLE_STYLE = {
  active: { alpha: 1, fill: 1, dash: [], width: 1.2 },
  confirmed: { alpha: 1, fill: 1, dash: [], width: 1.4 },
  candidate: { alpha: 0.9, fill: 0.7, dash: [5, 3], width: 1.2 },
  potential: { alpha: 0.8, fill: 0.55, dash: [4, 3], width: 1.1 },
  waiting: { alpha: 0.9, fill: 0.6, dash: [5, 3], width: 1.2 },
  mitigated: { alpha: 0.4, fill: 0.45, dash: [], width: 1 },
  taken: { alpha: 0.45, fill: 0.4, dash: [2, 3], width: 1, marker: 'swept' }, // swept liquidity
  broken: { alpha: 0.35, fill: 0.35, dash: [6, 4], width: 1 },
  // Invalidated/expired are hidden by default (history off); very faint otherwise.
  invalidated: { alpha: 0.2, fill: 0.2, dash: [2, 3], width: 1, marker: 'invalid' },
  expired: { alpha: 0.2, fill: 0.2, dash: [2, 4], width: 1 },
}
export const HISTORICAL_STYLE = { alpha: 0.3, fill: 0.35 }

export function lifecycleStyle(status, { historical = false } = {}) {
  const base = LIFECYCLE_STYLE[status] || LIFECYCLE_STYLE.active
  return historical ? { ...base, alpha: Math.min(base.alpha, HISTORICAL_STYLE.alpha), fill: base.fill * HISTORICAL_STYLE.fill } : base
}

// ---------------------------------------------------------------------------
// 2. Scenario visual priority (deterministic, from existing fields only)
// ---------------------------------------------------------------------------
const CONVICTION_RANK = { high: 3, medium: 2, low: 1 }

/**
 * Ranking order (each step only if the field exists):
 *  1. engine selection (selected_scenario / trade_plan.scenario_name)
 *  2. trigger validity (trigger_confirmed)
 *  3. conviction category (high > medium > low)
 *  4. confluence_score
 *  5. timeframe alignment with market_bias.htf direction
 * Tiers: PRIMARY = the single top rank. If several scenarios share the top rank
 * on every available field, the data cannot separate them: they are UNRANKED
 * (equal priority) instead of being forced into an order. Everything else is
 * SECONDARY. `muted` (low conviction, against HTF, or stale analysis) only
 * lowers intensity. The tier is visual only and never changes validity.
 */
export function rankScenarios(scenarios, { selectedName = null, htfDirection = null, stale = false } = {}) {
  const htf = String(htfDirection || '').toLowerCase()
  const rows = scenarios.map((sc) => {
    const dir = String(sc.direction || '').toLowerCase()
    const conviction = String(sc.conviction || '').toLowerCase()
    const aligned = htf && ['bullish', 'bearish'].includes(htf) && dir ? (dir.includes(htf) ? 1 : -1) : 0
    const key = [
      selectedName && sc.name === selectedName ? 1 : 0,
      sc.trigger_confirmed === true ? 1 : 0,
      CONVICTION_RANK[conviction] || 0,
      typeof sc.confluence_score === 'number' ? sc.confluence_score : 0,
      aligned,
    ]
    return { sc, key, conviction, aligned }
  })
  const cmp = (a, b) => {
    for (let i = 0; i < a.key.length; i += 1) if (a.key[i] !== b.key[i]) return b.key[i] - a.key[i]
    return 0
  }
  rows.sort((a, b) => cmp(a, b) || String(a.sc.name).localeCompare(String(b.sc.name)))

  return rows.map((row, i) => {
    const reasons = []
    if (row.key[0]) reasons.push('engine-selected scenario')
    if (row.key[1]) reasons.push('trigger confirmed')
    if (row.conviction) reasons.push(`${row.conviction} conviction`)
    if (typeof row.sc.confluence_score === 'number') reasons.push(`confluence score ${row.sc.confluence_score}`)
    if (row.aligned === 1) reasons.push('aligned with HTF')
    if (row.aligned === -1) reasons.push('against HTF')

    const topTied = rows.filter((x) => cmp(x, rows[0]) === 0).length
    let tier = 'secondary'
    if (cmp(row, rows[0]) === 0) tier = topTied > 1 ? 'unranked' : 'primary'
    const muted = stale || row.conviction === 'low' || row.aligned === -1
    return { name: row.sc.name, tier, muted, rank: i + 1, reasons }
  })
}

export const SCENARIO_TIER_STYLE = {
  primary: { alpha: 1, width: 2, label: 'PRIMARY' },
  unranked: { alpha: 0.8, width: 1.5, label: 'UNRANKED' },
  secondary: { alpha: 0.6, width: 1.2, label: 'SECONDARY' },
}
export const MUTED_FACTOR = 0.55

// ---------------------------------------------------------------------------
// 3. Confluence (visual relationship between existing, drawn objects)
// ---------------------------------------------------------------------------
const CONFLUENCE_TYPES = new Set(['fvg', 'ob', 'supply', 'demand', 'support', 'resistance', 'bsl', 'ssl', 'eqh', 'eql'])
const LIVE = new Set(['active', 'confirmed', 'candidate', 'waiting', 'potential'])

function priceRange(o) {
  if (typeof o.price_low === 'number' && typeof o.price_high === 'number') return [o.price_low, o.price_high]
  if (typeof o.price === 'number') return [o.price, o.price]
  return null
}

function directionOf(o) {
  if (o.color === 'bullish') return 'bullish'
  if (o.color === 'bearish') return 'bearish'
  return 'neutral'
}

/**
 * Groups drawn objects whose price ranges share a common overlap.
 * Rules: live status only (no historical zones), valid price boundaries, at
 * least one rectangular zone in the group, and a non-empty common price band.
 * Every member id is kept; members stay individually selectable.
 */
export function buildConfluence(items, typeOf) {
  const candidates = items
    .map((item) => ({ item, o: item.overlay, type: typeOf(item.overlay), range: priceRange(item.overlay) }))
    .filter((c) => c.range && CONFLUENCE_TYPES.has(c.type) && LIVE.has(c.o.status))
    .sort((a, b) => a.range[0] - b.range[0] || a.range[1] - b.range[1] || a.o.id.localeCompare(b.o.id))

  const groups = []
  const used = new Set()
  for (let i = 0; i < candidates.length; i += 1) {
    const seed = candidates[i]
    if (used.has(seed.o.id) || seed.range[0] === seed.range[1]) continue // seed must be a zone
    let lo = seed.range[0]
    let hi = seed.range[1]
    const members = [seed]
    for (let j = 0; j < candidates.length; j += 1) {
      const c = candidates[j]
      if (j === i || used.has(c.o.id)) continue
      const nlo = Math.max(lo, c.range[0])
      const nhi = Math.min(hi, c.range[1])
      if (nlo <= nhi) {
        members.push(c)
        lo = nlo
        hi = nhi
      }
    }
    if (members.length < 2) continue
    members.forEach((m) => used.add(m.o.id))
    const dirs = [...new Set(members.map((m) => directionOf(m.o)).filter((d) => d !== 'neutral'))]
    const tfs = [...new Set(members.map((m) => m.o.timeframe))]
    const types = [...new Set(members.map((m) => m.type))]
    groups.push({
      id: `confluence:${members.map((m) => m.o.id).sort().join('|')}`,
      memberIds: members.map((m) => m.o.id),
      count: members.length,
      price_low: lo,
      price_high: hi,
      timeframes: tfs,
      types,
      direction: dirs.length === 1 ? dirs[0] : dirs.length ? 'mixed' : 'neutral',
      statuses: [...new Set(members.map((m) => m.o.status))],
      time_start: members.map((m) => m.o.time_start).filter(Boolean).sort().slice(-1)[0] || null,
    })
  }
  return groups
}

const TYPE_SHORT = {
  fvg: 'FVG', ob: 'OB', supply: 'Supply', demand: 'Demand', support: 'S', resistance: 'R',
  bsl: 'BSL', ssl: 'SSL', eqh: 'EQH', eql: 'EQL',
}

export function confluenceLabel(g) {
  const title = { bearish: 'SUPPLY', bullish: 'DEMAND' }[g.direction] || 'MIXED'
  return `${title} CONFLUENCE · ${g.timeframes.join(' + ')} · ${g.types.map((t) => TYPE_SHORT[t] || t).join(' + ')}`
}

// ---------------------------------------------------------------------------
// 4. Deterministic label layout (screen space only)
// ---------------------------------------------------------------------------
function overlaps(a, b) {
  return a.l < b.r && a.r > b.l && a.t < b.b && a.b > b.t
}

/**
 * requests: { key, text, x, y, w, h, align, priority, ... }
 * reserved: rects nothing may cover (price axis, current price tag, ...)
 * Places high priority first (ties by key), tries vertical offsets, and
 * collapses labels that do not fit into "+N" groups at the anchor of the
 * group's highest-priority member. Anchors (market coordinates) never move.
 */
let lastLayout = { sig: null, result: null }

/** Same as layoutLabels, but reuses the previous result when nothing that
 *  affects placement changed (requests, reserved areas, bounds). */
export function layoutLabelsCached(requests, options = {}) {
  const sig = JSON.stringify([
    requests.map((r) => [r.key, Math.round(r.x), Math.round(r.y), Math.round(r.w), r.priority, r.text]),
    (options.reserved || []).map((q) => [Math.round(q.l), Math.round(q.t), Math.round(q.r), Math.round(q.b)]),
    options.bounds,
  ])
  if (sig === lastLayout.sig) return { ...lastLayout.result, cached: true }
  const result = layoutLabels(requests, options)
  lastLayout = { sig, result }
  return result
}

export function layoutLabels(requests, { reserved = [], bounds, offsets = [0, -12, 12, -24, 24, -36, 36] } = {}) {
  const placed = []
  const taken = [...reserved]
  const overflow = []
  const ordered = [...requests]
    .filter((r) => r.priority > 0) // priority 0 = no on-chart label (hover / Objects only)
    .sort((a, b) => b.priority - a.priority || String(a.key).localeCompare(String(b.key)))

  for (const r of ordered) {
    let spot = null
    // Primary labels may move further; secondary labels barely move and are
    // grouped instead of being pushed around the chart.
    const tries = r.priority >= 3 ? [...offsets, 48, -48] : r.priority >= 2 ? offsets : [0, -12, 12]
    for (const dy of tries) {
      const left = r.align === 'right' ? r.x - r.w : r.align === 'center' ? r.x - r.w / 2 : r.x
      const rect = { l: left, r: left + r.w, t: r.y + dy - r.h, b: r.y + dy }
      if (bounds && (rect.l < bounds.l || rect.r > bounds.r || rect.t < bounds.t || rect.b > bounds.b)) continue
      if (taken.some((q) => overlaps(rect, q))) continue
      spot = rect
      break
    }
    if (spot) {
      taken.push(spot)
      placed.push({ ...r, rect: spot })
    } else {
      overflow.push(r)
    }
  }

  // Collapse overflow: nearby labels (same 14px band, 120px span) form a group.
  const groups = []
  for (const r of overflow) {
    // Wider clusters -> fewer "+N" chips; members stay listed on hover/click.
    const g = groups.find((x) => Math.abs(x.y - r.y) <= 26 && Math.abs(x.x - r.x) <= 240)
    if (g) g.items.push(r)
    else groups.push({ x: r.x, y: r.y, items: [r] })
  }
  const grouped = []
  const unplaced = []
  const chipSpots = []
  for (const dx of [0, -50, -100]) {
    for (const dy of [0, -12, 12, -24, 24, -36, 36, -48, 48, -60, 60, -72, 72, -84, 84, -96, 96]) chipSpots.push([dx, dy])
  }
  for (const g of groups) {
    const text = `+${g.items.length}`
    const w = 8 + text.length * 6
    let done = false
    for (const [dx, dy] of chipSpots) {
      const rect = { l: g.x - w + dx, r: g.x + dx, t: g.y + dy - 11, b: g.y + dy }
      if (bounds && (rect.l < bounds.l || rect.r > bounds.r || rect.t < bounds.t || rect.b > bounds.b)) continue
      if (taken.some((q) => overlaps(rect, q))) continue
      taken.push(rect)
      grouped.push({ text, rect, items: g.items, x: g.x, y: g.y })
      done = true
      break
    }
    if (!done) unplaced.push(g)
  }
  // Never lose a label: a group without room joins the nearest placed group;
  // if there is none, it is placed at its anchor as the last resort.
  for (const g of unplaced) {
    if (!grouped.length) {
      const w = 8 + `+${g.items.length}`.length * 6
      grouped.push({ text: '', rect: { l: g.x - w, r: g.x, t: g.y - 11, b: g.y }, items: [], x: g.x, y: g.y })
    }
    const nearest = grouped.reduce((best, c) => (
      Math.hypot(c.x - g.x, c.y - g.y) < Math.hypot(best.x - g.x, best.y - g.y) ? c : best
    ))
    nearest.items.push(...g.items)
  }
  for (const g of grouped) g.text = `+${g.items.length}`
  return { placed, grouped, hiddenCount: overflow.length }
}

// ---------------------------------------------------------------------------
// 5. Visual emphasis: PRIMARY / SECONDARY / HISTORICAL (display only)
// ---------------------------------------------------------------------------
const ZONE_TYPES = new Set(['fvg', 'ob', 'supply', 'demand'])
const HISTORICAL_STATUS = new Set(['mitigated', 'taken', 'broken', 'expired', 'invalidated'])

/**
 * Deterministic emphasis for drawn items (`{ overlay, htf, type, swingRank }`):
 * HISTORICAL - mitigated / swept / broken / expired / invalidated objects and
 *              swing labels older than the two most recent of their kind.
 * PRIMARY    - the trade plan, PRIMARY or UNRANKED scenarios, BOS/CHoCH of the
 *              chart timeframe, and the most relevant live zones: the zone(s)
 *              containing the current price, otherwise the nearest live zone
 *              above and the nearest below it (chart timeframe first, HTF only
 *              if the chart timeframe has none on that side).
 * SECONDARY  - everything else (HTF references, alternatives, other zones).
 * Returns Map(id -> 'primary' | 'secondary' | 'historical').
 */
export function assignEmphasis(items, { currentPrice = null } = {}) {
  const out = new Map()
  for (const it of items) {
    const o = it.overlay
    let e = 'secondary'
    if (HISTORICAL_STATUS.has(o.status) || (it.swingRank ?? 0) >= 2) e = 'historical'
    else if (o.layer === 'trade_plan') e = 'primary'
    else if (it.type === 'scenario' && ['primary', 'unranked'].includes(o.meta?.tier)) e = 'primary'
    else if ((it.type === 'bos' || it.type === 'choch') && !it.htf) e = 'primary'
    out.set(o.id, e)
  }

  if (typeof currentPrice === 'number') {
    const zones = items.filter((it) => ZONE_TYPES.has(it.type) && out.get(it.overlay.id) !== 'historical'
      && typeof it.overlay.price_low === 'number' && typeof it.overlay.price_high === 'number')
    const containing = zones.filter((it) => it.overlay.price_low <= currentPrice && it.overlay.price_high >= currentPrice)
    if (containing.length) {
      containing.forEach((it) => out.set(it.overlay.id, 'primary'))
    } else {
      for (const side of ['above', 'below']) {
        const candidates = zones.filter((it) => (side === 'above' ? it.overlay.price_low > currentPrice : it.overlay.price_high < currentPrice))
        const dist = (it) => (side === 'above' ? it.overlay.price_low - currentPrice : currentPrice - it.overlay.price_high)
        const pick = (list) => [...list].sort((a, b) => dist(a) - dist(b) || a.overlay.id.localeCompare(b.overlay.id))[0]
        const best = pick(candidates.filter((it) => !it.htf)) || pick(candidates)
        if (best) out.set(best.overlay.id, 'primary')
      }
    }
  }
  return out
}

export const EMPHASIS_STYLE = {
  primary: { alpha: 1, fill: 1.35, width: 0.4 },
  secondary: { alpha: 0.55, fill: 0.7, width: 0 },
  historical: { alpha: 1, fill: 1, width: 0 }, // lifecycle style already fades these
}

/** Short scenario name for on-chart labels (full name stays in the tooltip). */
export function shortScenarioName(name) {
  const text = String(name || '').replace(/^CONDITIONAL · /, '').replace(/_/g, ' ')
  return text.length > 22 ? `${text.slice(0, 21)}…` : text
}

// ---------------------------------------------------------------------------
// 6. Timeframe display profiles (visualization only, no analysis)
// ---------------------------------------------------------------------------
// htfTimeframes: which higher timeframes may appear as references on this chart.
// htfAlpha: intensity of those references. structureHistory: keep historical
// structure (faded) visible on macro charts.
export const TF_PROFILES = {
  M1: { label: 'EXECUTION', htfTimeframes: ['H1', 'H4'], htfAlpha: 0.4, structureHistory: false },
  M5: { label: 'EXECUTION', htfTimeframes: ['H1', 'H4'], htfAlpha: 0.4, structureHistory: false },
  M15: { label: 'EXECUTION', htfTimeframes: ['H1', 'H4'], htfAlpha: 0.45, structureHistory: false },
  M30: { label: 'INTRADAY', htfTimeframes: ['H1', 'H4'], htfAlpha: 0.5, structureHistory: false },
  H1: { label: 'INTRADAY', htfTimeframes: ['H4', 'D1'], htfAlpha: 0.55, structureHistory: false },
  H4: { label: 'MACRO', htfTimeframes: ['D1'], htfAlpha: 0.65, structureHistory: true },
  D1: { label: 'MACRO', htfTimeframes: [], htfAlpha: 0.65, structureHistory: true },
}

export function tfProfile(tf) {
  return TF_PROFILES[tf] || TF_PROFILES.M5
}

// ---------------------------------------------------------------------------
// 7. Candle-first autoscale (price range of the viewport)
// ---------------------------------------------------------------------------
/**
 * The visible candles' OHLC define the range. The current price is added when
 * given (caller passes it only at the live edge). Reference levels (e.g. the
 * selected scenario trigger/invalidation) are added only when they lie within
 * `nearFraction` of the candle range beyond its edges; farther references are
 * returned in `excluded` and shown as edge tags instead of compressing candles.
 * Pure: never changes any market coordinate.
 */
export function computeAutoscale(candles, { currentPrice = null, refs = [], pad = 0.06, nearFraction = 0.25 } = {}) {
  let lo = Infinity
  let hi = -Infinity
  for (const c of candles) {
    if (c.low < lo) lo = c.low
    if (c.high > hi) hi = c.high
  }
  if (!Number.isFinite(lo) || !Number.isFinite(hi)) return null
  if (typeof currentPrice === 'number' && Number.isFinite(currentPrice)) {
    lo = Math.min(lo, currentPrice)
    hi = Math.max(hi, currentPrice)
  }
  const base = hi - lo || Math.abs(hi) * 0.0005 || 1
  const included = []
  const excluded = []
  for (const r of refs) {
    if (typeof r !== 'number' || !Number.isFinite(r)) continue
    const beyond = r > hi ? r - hi : r < lo ? lo - r : 0
    if (beyond <= base * nearFraction) included.push(r)
    else excluded.push(r)
  }
  for (const r of included) {
    lo = Math.min(lo, r)
    hi = Math.max(hi, r)
  }
  const range = hi - lo || base
  return { min: lo - range * pad, max: hi + range * pad, included, excluded }
}

/** Compact direction word for scenario labels. */
export function scenarioBadge(o) {
  const dir = o.color === 'bearish' ? 'BEARISH' : 'BULLISH'
  const tier = { primary: 'PRIMARY', unranked: 'UNRANKED', secondary: 'SECONDARY' }[o.meta?.tier] || 'SECONDARY'
  const counter = (o.meta?.rank_reasons || []).includes('against HTF') || /counter/i.test(o.name || '')
  return `${tier} ${dir}${counter ? ' · COUNTERTREND' : ''}`
}
