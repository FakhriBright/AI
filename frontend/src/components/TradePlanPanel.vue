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

const action = computed(() => ['BUY', 'SELL'].includes(plan.value.action) ? plan.value.action : 'WAIT')

const decisionTitle = computed(() => {
  if (action.value === 'BUY') return 'BUY — rencana beli terkonfirmasi'
  if (action.value === 'SELL') return 'SELL — rencana jual terkonfirmasi'
  return 'WAIT — jangan entry dulu'
})

const decisionReason = computed(() => {
  const current = plan.value
  if (action.value !== 'WAIT') {
    return 'Syarat setup, stop loss, target, dan rasio risiko/hasil lolos pemeriksaan engine. Tetap tinjau manual sebelum membuka posisi.'
  }
  if (current.status === 'confirmed_needs_risk') {
    return 'Arah setup sudah terkonfirmasi, tetapi pengaturan risiko atau perhitungan ukuran posisi belum lengkap.'
  }
  if (current.status === 'confirmed_needs_stop') {
    return 'Sinyal sudah terkonfirmasi, tetapi stop loss yang valid belum tersedia. Jangan entry dulu.'
  }
  if (current.status === 'rejected_rr') {
    return 'Target yang valid belum memberi rasio risiko/hasil minimal 1:1. Tunggu setup yang lebih layak.'
  }
  if (current.status === 'waiting') {
    return current.reasons?.[0] || 'Candle konfirmasi belum memenuhi aturan entry.'
  }
  return current.warnings?.[0] || 'Belum semua syarat entry lolos pemeriksaan engine.'
})

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
      <section class="trade-decision" :class="'decision-' + action.toLowerCase()" aria-live="polite">
        <div class="decision-action">{{ action }}</div>
        <div class="decision-copy">
          <strong>{{ decisionTitle }}</strong>
          <p>{{ decisionReason }}</p>
        </div>
      </section>

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
