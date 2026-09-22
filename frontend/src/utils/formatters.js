/**
 * Formatting and helper utilities for trading data
 * Strictly respects the "Never fabricate data" rule:
 * Returns "Unavailable" or "—" for missing values.
 */

export function formatPrice(price, symbol = '') {
  if (price === null || price === undefined || isNaN(price)) {
    return 'Unavailable'
  }

  const num = Number(price)
  const sym = (symbol || '').toUpperCase()

  if (sym.includes('XAU') || sym.includes('GOLD')) {
    return num.toFixed(2)
  }
  if (sym.includes('BTC') || sym.includes('ETH')) {
    return num.toFixed(2)
  }
  if (sym.includes('JPY')) {
    return num.toFixed(3)
  }
  // Standard FX
  if (num < 10) {
    return num.toFixed(5)
  }
  return num.toFixed(2)
}

export function formatPips(distance, symbol = '') {
  if (distance === null || distance === undefined || isNaN(distance)) {
    return 'Unavailable'
  }

  const dist = Number(distance)
  const sym = (symbol || '').toUpperCase()

  if (sym.includes('XAU') || sym.includes('GOLD')) {
    return `$${dist.toFixed(2)}`
  }
  if (sym.includes('JPY')) {
    return `${(dist * 100).toFixed(1)} pips`
  }
  if (dist < 10) {
    return `${(dist * 10000).toFixed(1)} pips`
  }
  return dist.toFixed(2)
}

export function formatDateTimeUtc(utcString) {
  if (!utcString) return 'Unavailable'
  try {
    const d = new Date(utcString)
    if (isNaN(d.getTime())) return String(utcString)
    return d.toISOString().replace('T', ' ').substring(0, 19) + ' UTC'
  } catch {
    return String(utcString)
  }
}

export function formatTimeOnlyUtc(utcString) {
  if (!utcString) return '—'
  try {
    const d = new Date(utcString)
    if (isNaN(d.getTime())) return String(utcString)
    return d.toISOString().substring(11, 19) + ' UTC'
  } catch {
    return String(utcString)
  }
}

export function formatNumber(val, decimals = 2) {
  if (val === null || val === undefined || isNaN(val)) {
    return 'Unavailable'
  }
  return Number(val).toFixed(decimals)
}

export function getBiasBadgeClass(bias) {
  if (!bias) return 'badge-neutral'
  const b = String(bias).toLowerCase()
  if (b === 'bullish') return 'badge-bullish'
  if (b === 'bearish') return 'badge-bearish'
  return 'badge-mixed'
}

export function getStatusBadgeClass(status) {
  if (!status) return 'badge-neutral'
  const s = String(status).toLowerCase()
  if (s === 'ready_for_manual_review' || s === 'confirmed') return 'badge-bullish'
  if (s === 'waiting' || s === 'conditional') return 'badge-mixed'
  if (s.includes('needs')) return 'badge-warning'
  return 'badge-neutral'
}
