<script setup>
import { computed } from 'vue'
import { formatPrice, getBiasBadgeClass } from '../utils/formatters'

const props = defineProps({
  tradePlan: {
    type: Object,
    default: null,
  },
  stopPlan: {
    type: Object,
    default: null,
  },
  symbol: {
    type: String,
    default: 'EURUSDm',
  },
})

const plan = computed(() => props.tradePlan || {})

const status = computed(() => {
  const value = String(plan.value.status || 'waiting').toLowerCase()
  if (['ready_for_manual_review', 'ready', 'approved'].includes(value)) return 'READY FOR REVIEW'
  if (value === 'confirmed_needs_risk') return 'WAIT — RISK SETTINGS REQUIRED'
  if (value === 'confirmed_needs_stop') return 'WAIT — STOP LOSS REQUIRED'
  if (value === 'confirmed_needs_target') return 'WAIT — TAKE PROFIT REQUIRED'
  if (value === 'waiting' || value === 'waiting_for_confirmation') return 'WAIT — CONFIRMATION REQUIRED'
  return `WAIT — ${value.replace(/_/g, ' ').toUpperCase()}`
})

const action = computed(() => {
  const direction = String(plan.value.direction || plan.value.market_bias || '').toLowerCase()
  if (['bullish', 'long', 'buy'].includes(direction)) return 'BUY'
  if (['bearish', 'short', 'sell'].includes(direction)) return 'SELL'
  return 'NO CLEAR DIRECTION'
})

const isReady = computed(() => String(plan.value.status || '').toLowerCase() === 'ready_for_manual_review')

const statusExplanation = computed(() => {
  if (isReady.value) return `${action.value} setup passed the engine checks. Review the plan before placing any trade.`
  if (plan.value.status === 'confirmed_needs_risk') return `${action.value} is the preferred setup, but risk settings/position sizing are incomplete. Do not enter yet.`
  if (plan.value.status === 'confirmed_needs_stop') return `${action.value} is the preferred direction, but a valid stop loss is missing. Do not enter yet.`
  if (plan.value.status === 'confirmed_needs_target') return `${action.value} is the preferred direction, but a valid take-profit and risk/reward calculation are missing. Do not enter yet.`
  return `${action.value} is the preferred direction, not an active entry. Wait for the required candle confirmation.`
})

const bias = computed(() => plan.value.direction || plan.value.market_bias || 'Neutral')

const entry = computed(() => {
  if (plan.value.entry_price !== null && plan.value.entry_price !== undefined) {
    return formatPrice(plan.value.entry_price, props.symbol)
  }
  return '—'
})

const stopLoss = computed(() => {
  if (plan.value.stop_price !== null && plan.value.stop_price !== undefined) {
    return formatPrice(plan.value.stop_price, props.symbol)
  }
  return '—'
})

const takeProfit = computed(() => {
  if (plan.value.target_price !== null && plan.value.target_price !== undefined) {
    return formatPrice(plan.value.target_price, props.symbol)
  }
  if (plan.value.take_profit !== null && plan.value.take_profit !== undefined) {
    return formatPrice(plan.value.take_profit, props.symbol)
  }
  return '—'
})

const riskRR = computed(() => {
  if (plan.value.rr_ratio !== null && plan.value.rr_ratio !== undefined) {
    return `1:${Number(plan.value.rr_ratio).toFixed(2)}`
  }
  return '—'
})

const trigger = computed(() => {
  if (plan.value.trigger) return plan.value.trigger
  if (plan.value.entry_price) return `Break and close price near ${formatPrice(plan.value.entry_price, props.symbol)}`
  return 'Waiting for setup confirmation'
})

const invalidation = computed(() => {
  if (plan.value.invalidation) return plan.value.invalidation
  if (plan.value.stop_price) return `Price moves beyond ${formatPrice(plan.value.stop_price, props.symbol)}`
  return '—'
})
</script>

<template>
  <div class="card-box trade-plan-module">
    <div class="trade-decision-banner" :class="isReady ? 'decision-ready' : 'decision-wait'">
      <div class="decision-action">{{ isReady ? action : 'WAIT' }}</div>
      <div class="decision-copy">
        <strong>{{ action }} {{ isReady ? '— setup siap ditinjau' : '— rencana bersyarat, belum entry' }}</strong>
        <p>{{ statusExplanation }}</p>
      </div>
    </div>
    <div class="card-header">
      <span class="card-title">TRADE PLAN</span>
      <div class="badge badge-warning">
        {{ status }}
      </div>
    </div>

    <div class="card-body">
      <!-- 4 Core Metric Grid -->
      <div class="trade-plan-grid">
        <div class="metric-card">
          <span class="metric-label">Bias</span>
          <div>
            <span class="badge" :class="getBiasBadgeClass(bias)">
              {{ String(bias).toUpperCase() }}
            </span>
          </div>
        </div>

        <div class="metric-card">
          <span class="metric-label">{{ isReady ? 'Entry' : 'Planned Entry (conditional)' }}</span>
          <span class="metric-val text-accent">{{ entry }}</span>
        </div>

        <div class="metric-card">
          <span class="metric-label">Stop Loss</span>
          <span class="metric-val text-red">{{ stopLoss }}</span>
        </div>

        <div class="metric-card">
          <span class="metric-label">Take Profit / R:R</span>
          <span class="metric-val text-green">{{ takeProfit }}</span>
          <span class="metric-label">R:R {{ riskRR }}</span>
        </div>
      </div>

      <!-- Trigger & Invalidation Rules -->
      <div class="trade-rules-row">
        <div class="rule-item">
          <span class="rule-label">Trigger:</span>
          <span class="font-mono text-main">{{ trigger }}</span>
        </div>
        <div class="rule-item">
          <span class="rule-label">Invalidation:</span>
          <span class="font-mono text-muted">{{ invalidation }}</span>
        </div>
      </div>
    </div>
  </div>
</template>
