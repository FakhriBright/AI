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
  if (!plan.value.status) return 'WAITING FOR CONFIRMATION'
  return plan.value.status.replace(/_/g, ' ').toUpperCase()
})

const bias = computed(() => {
  return plan.value.direction || plan.value.market_bias || 'Neutral'
})

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
  if (plan.value.take_profit !== null && plan.value.take_profit !== undefined) {
    return formatPrice(plan.value.take_profit, props.symbol)
  }
  return '—'
})

const riskRR = computed(() => {
  if (plan.value.rr_ratio !== null && plan.value.rr_ratio !== undefined) {
    return `1:${plan.value.rr_ratio}`
  }
  if (plan.value.risk_percent !== null && plan.value.risk_percent !== undefined) {
    return `${plan.value.risk_percent}%`
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
          <span class="metric-label">Entry</span>
          <span class="metric-val text-accent">{{ entry }}</span>
        </div>

        <div class="metric-card">
          <span class="metric-label">Stop Loss</span>
          <span class="metric-val text-red">{{ stopLoss }}</span>
        </div>

        <div class="metric-card">
          <span class="metric-label">Take Profit / R:R</span>
          <span class="metric-val text-green">{{ takeProfit !== '—' ? takeProfit : riskRR }}</span>
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
