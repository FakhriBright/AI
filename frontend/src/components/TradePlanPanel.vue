<script setup>
import { computed } from 'vue'
import {
  formatPrice,
  formatPips,
  formatNumber,
  getStatusBadgeClass,
  getBiasBadgeClass,
} from '../utils/formatters'

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

const status = computed(() => plan.value.status || 'waiting')
const direction = computed(() => plan.value.direction || 'neutral')

const entryPrice = computed(() => plan.value.entry_price)
const stopPrice = computed(() => plan.value.stop_price)
const stopDistance = computed(() => plan.value.stop_distance)
const stopMethod = computed(() => plan.value.stop_method)

const riskPercent = computed(() => plan.value.risk_percent)
const riskAmount = computed(() => plan.value.risk_amount)
const volume = computed(() => plan.value.volume)
const estLoss = computed(() => plan.value.estimated_loss)

const reasons = computed(() => plan.value.reasons || [])
const warnings = computed(() => plan.value.warnings || [])

// Calculate theoretical 1:1.5 and 1:2 Take Profit targets for manual reference only
const tp1Target = computed(() => {
  if (!entryPrice.value || !stopPrice.value) return null
  const dist = Math.abs(entryPrice.value - stopPrice.value)
  if (direction.value === 'bullish') {
    return entryPrice.value + dist * 1.5
  }
  if (direction.value === 'bearish') {
    return entryPrice.value - dist * 1.5
  }
  return null
})

const tp2Target = computed(() => {
  if (!entryPrice.value || !stopPrice.value) return null
  const dist = Math.abs(entryPrice.value - stopPrice.value)
  if (direction.value === 'bullish') {
    return entryPrice.value + dist * 2.0
  }
  if (direction.value === 'bearish') {
    return entryPrice.value - dist * 2.0
  }
  return null
})
</script>

<template>
  <div class="panel-container">
    <div class="panel-header">
      <div class="panel-title-wrap">
        <svg class="panel-icon" viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
          <path d="M19 3H5c-1.11 0-2 .9-2 2v14c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-9 14l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z" />
        </svg>
        <h2 class="panel-title">TRADE PLAN & RISK SIZING (MANUAL EXECUTION ONLY)</h2>
      </div>

      <div class="plan-status-badge-wrap">
        <span class="badge" :class="getStatusBadgeClass(status)">
          {{ status.replace(/_/g, ' ').toUpperCase() }}
        </span>
      </div>
    </div>

    <!-- Manual Execution Warning Banner -->
    <div class="manual-execution-banner">
      <div class="warning-icon">
        <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor">
          <path d="M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z" />
        </svg>
      </div>
      <div class="warning-content">
        <strong>CRITICAL SAFETY POLICY:</strong>
        <span>
          This trade plan is strictly for decision support.
          The AI and backend NEVER place automated orders on MT5.
          The user must review risk limits and manually execute any trades in the MT5 Terminal.
        </span>
      </div>
    </div>

    <!-- Main Trade Plan Grid -->
    <div class="trade-plan-grid">
      <!-- Left Column: Order Parameters -->
      <div class="plan-section-card">
        <div class="section-card-title">ORDER PARAMETERS</div>

        <div class="param-row">
          <span class="param-label">Direction:</span>
          <span class="badge" :class="getBiasBadgeClass(direction)">
            {{ direction.toUpperCase() }}
          </span>
        </div>

        <div class="param-row">
          <span class="param-label">Scenario Model:</span>
          <span class="param-value uppercase">{{ plan.scenario_name ? plan.scenario_name.replace(/_/g, ' ') : 'Unavailable' }}</span>
        </div>

        <div class="param-row">
          <span class="param-label">Entry / Trigger Price:</span>
          <span class="param-value-large font-mono">
            {{ formatPrice(entryPrice, symbol) }}
          </span>
        </div>

        <div class="param-row">
          <span class="param-label">Stop Loss Level:</span>
          <div class="param-col-right">
            <span class="param-value-large font-mono text-red">
              {{ formatPrice(stopPrice, symbol) }}
            </span>
            <span v-if="stopDistance !== null && stopDistance !== undefined" class="text-xs text-muted">
              (Distance: {{ formatPips(stopDistance, symbol) }})
            </span>
          </div>
        </div>

        <div class="param-row">
          <span class="param-label">Stop Sizing Method:</span>
          <span class="param-value uppercase">{{ stopMethod ? stopMethod.replace(/_/g, ' ') : 'Unavailable' }}</span>
        </div>

        <!-- Take Profit References (1:1.5 and 1:2 R:R) -->
        <div class="tp-references-box">
          <div class="tp-row">
            <span class="tp-label">1:1.5 R:R Target:</span>
            <span class="font-mono text-green">{{ formatPrice(tp1Target, symbol) }}</span>
          </div>
          <div class="tp-row">
            <span class="tp-label">1:2.0 R:R Target:</span>
            <span class="font-mono text-green">{{ formatPrice(tp2Target, symbol) }}</span>
          </div>
        </div>
      </div>

      <!-- Right Column: Sizing & Capital Allocation -->
      <div class="plan-section-card">
        <div class="section-card-title">CAPITAL ALLOCATION & SIZING</div>

        <div class="param-row">
          <span class="param-label">Calculated Lot Size:</span>
          <div class="param-col-right">
            <span class="volume-highlight font-mono">
              {{ volume !== null && volume !== undefined ? volume : 'Unavailable' }}
            </span>
            <span v-if="volume" class="text-xs text-muted">Lots</span>
          </div>
        </div>

        <div class="param-row">
          <span class="param-label">Risk Percentage:</span>
          <span class="param-value font-mono">
            {{ riskPercent !== null && riskPercent !== undefined ? `${riskPercent}%` : 'Unavailable' }}
          </span>
        </div>

        <div class="param-row">
          <span class="param-label">Max Risk Amount:</span>
          <span class="param-value font-mono">
            {{ riskAmount !== null && riskAmount !== undefined ? `$${Number(riskAmount).toFixed(2)}` : 'Unavailable' }}
          </span>
        </div>

        <div class="param-row">
          <span class="param-label">Estimated Loss on SL:</span>
          <span class="param-value font-mono text-red">
            {{ estLoss !== null && estLoss !== undefined ? `$${Number(estLoss).toFixed(2)}` : 'Unavailable' }}
          </span>
        </div>

        <div class="param-row">
          <span class="param-label">Confirmation Type:</span>
          <span class="param-value uppercase">
            {{ plan.confirmation_type ? plan.confirmation_type.replace(/_/g, ' ') : 'Unavailable' }}
          </span>
        </div>

        <!-- Invalidation Notice -->
        <div class="inval-notice-box">
          <span class="inval-title">Execution Invalidation Rule:</span>
          <p class="inval-desc">
            If candle breaks beyond the Stop Loss level before reaching entry trigger, cancel setup immediately.
          </p>
        </div>
      </div>
    </div>

    <!-- Warnings & Reasons Checklist -->
    <div class="plan-feedback-row">
      <!-- Reasons -->
      <div class="feedback-col">
        <div class="feedback-title">
          <span class="dot dot-green"></span>
          <span>EXECUTION REASONS ({{ reasons.length }})</span>
        </div>
        <ul v-if="reasons.length" class="feedback-list">
          <li v-for="(reason, idx) in reasons" :key="idx">
            {{ reason.replace(/_/g, ' ') }}
          </li>
        </ul>
        <div v-else class="text-xs text-muted p-2">
          No execution reasons logged.
        </div>
      </div>

      <!-- Warnings -->
      <div class="feedback-col">
        <div class="feedback-title">
          <span class="dot dot-amber"></span>
          <span>WARNINGS & CONSTRAINTS ({{ warnings.length }})</span>
        </div>
        <ul v-if="warnings.length" class="feedback-list">
          <li v-for="(warning, idx) in warnings" :key="idx" class="warning-item">
            {{ warning }}
          </li>
        </ul>
        <div v-else class="text-xs text-muted p-2">
          No conflict warnings flagged.
        </div>
      </div>
    </div>
  </div>
</template>
