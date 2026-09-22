<script setup>
import { ref, computed } from 'vue'
import { formatPrice, formatPips, formatNumber, getStatusBadgeClass } from '../utils/formatters'

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

// Interactive Risk Calculator Simulator
const simEquity = ref(10000)
const simRiskPercent = ref(1.0)
const simStopPips = ref(20)

const simRiskAmount = computed(() => {
  return (simEquity.value * simRiskPercent.value) / 100
})

// Approximations for EURUSD (1 pip = $10 per 1.0 lot) or Gold (1 pt = $100 per 1.0 lot)
const simVolume = computed(() => {
  if (simStopPips.value <= 0) return 0
  const isGold = props.symbol.toUpperCase().includes('XAU')
  const costPerPipPerLot = isGold ? 100 : 10
  const riskPerLot = simStopPips.value * costPerPipPerLot
  const rawLot = simRiskAmount.value / (riskPerLot || 1)
  return Math.max(0.01, Math.min(50, Math.floor(rawLot * 100) / 100))
})

const simEstLoss = computed(() => {
  const isGold = props.symbol.toUpperCase().includes('XAU')
  const costPerPipPerLot = isGold ? 100 : 10
  return simVolume.value * simStopPips.value * costPerPipPerLot
})
</script>

<template>
  <div class="risk-view-container">
    <div class="panel-header">
      <div class="panel-title-wrap">
        <svg class="panel-icon" viewBox="0 0 24 24" width="18" height="18" fill="currentColor">
          <path d="M12 1L3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5l-9-4zm-2 16l-4-4 1.41-1.41L10 14.17l6.59-6.59L18 9l-8 8z" />
        </svg>
        <h2 class="panel-title">RISK ENGINE & POSITION SIZING ARCHITECTURE</h2>
      </div>
      <span class="panel-subtitle">Capital Preservation & Strict Mathematical Sizing</span>
    </div>

    <!-- Active Trade Plan Risk Parameters -->
    <div class="risk-cards-grid">
      <div class="risk-card">
        <span class="risk-card-label">CURRENT TRADE STATUS</span>
        <div class="risk-val-row">
          <span class="badge" :class="getStatusBadgeClass(tradePlan?.status)">
            {{ tradePlan?.status ? tradePlan.status.replace(/_/g, ' ').toUpperCase() : 'NO ACTIVE PLAN' }}
          </span>
        </div>
        <p class="risk-card-desc">
          Evaluated against broker contract specification.
        </p>
      </div>

      <div class="risk-card">
        <span class="risk-card-label">RECOMMENDED VOLUME</span>
        <div class="risk-val-row font-mono font-bold text-accent">
          {{ tradePlan?.volume !== null && tradePlan?.volume !== undefined ? `${tradePlan.volume} Lots` : 'Unavailable' }}
        </div>
        <p class="risk-card-desc">
          Normalized to broker volume min, max, and step.
        </p>
      </div>

      <div class="risk-card">
        <span class="risk-card-label">ESTIMATED MAXIMUM LOSS</span>
        <div class="risk-val-row font-mono font-bold text-red">
          {{ tradePlan?.estimated_loss !== null && tradePlan?.estimated_loss !== undefined ? `$${Number(tradePlan.estimated_loss).toFixed(2)}` : 'Unavailable' }}
        </div>
        <p class="risk-card-desc">
          Calculated at Stop Loss invalidation point.
        </p>
      </div>

      <div class="risk-card">
        <span class="risk-card-label">ALLOCATED RISK %</span>
        <div class="risk-val-row font-mono font-bold">
          {{ tradePlan?.risk_percent !== null && tradePlan?.risk_percent !== undefined ? `${tradePlan.risk_percent}%` : 'Unavailable' }}
        </div>
        <p class="risk-card-desc">
          Percentage of live MT5 account equity.
        </p>
      </div>
    </div>

    <!-- Risk Formula Explanation -->
    <div class="panel-container mt-4">
      <div class="section-card-title">MATHEMATICAL SIZING FORMULA</div>
      <div class="formula-box font-mono">
        <div class="formula-line">Risk Amount = Account Equity &times; (Risk % / 100)</div>
        <div class="formula-line">Risk Per Lot = (Stop Distance / Tick Size) &times; Tick Value</div>
        <div class="formula-line">Calculated Volume = Normalize(Risk Amount / Risk Per Lot, Min, Max, Step)</div>
        <div class="formula-line">Estimated Loss = (Stop Distance / Tick Size) &times; Tick Value &times; Volume</div>
      </div>
      <p class="text-xs text-muted mt-2">
        If estimated loss exceeds the requested risk amount (due to broker minimum lot size),
        the risk engine blocks trade generation with a safety violation.
      </p>
    </div>

    <!-- Position Size Simulator -->
    <div class="panel-container mt-4">
      <div class="section-card-title">MANUAL POSITION SIZING SIMULATOR ({{ symbol }})</div>

      <div class="simulator-grid mt-3">
        <div class="sim-input-col">
          <div class="form-group">
            <label class="input-label" for="sim-equity-input">Account Equity ($)</label>
            <input
              id="sim-equity-input"
              v-model.number="simEquity"
              type="number"
              class="terminal-input"
              step="100"
              min="100"
            />
          </div>

          <div class="form-group mt-3">
            <label class="input-label" for="sim-risk-input">Risk Percentage (%)</label>
            <input
              id="sim-risk-input"
              v-model.number="simRiskPercent"
              type="number"
              class="terminal-input"
              step="0.1"
              min="0.1"
              max="10"
            />
          </div>

          <div class="form-group mt-3">
            <label class="input-label" for="sim-stop-input">Stop Loss Distance (Pips / Points)</label>
            <input
              id="sim-stop-input"
              v-model.number="simStopPips"
              type="number"
              class="terminal-input"
              step="1"
              min="1"
            />
          </div>
        </div>

        <div class="sim-output-col">
          <div class="sim-metric-box">
            <span class="sim-lbl">Target Risk Budget:</span>
            <span class="sim-val font-mono">${{ simRiskAmount.toFixed(2) }}</span>
          </div>

          <div class="sim-metric-box">
            <span class="sim-lbl">Recommended Lot Size:</span>
            <span class="sim-val font-mono text-accent font-bold">{{ simVolume }} Lots</span>
          </div>

          <div class="sim-metric-box">
            <span class="sim-lbl">Simulated Loss at Stop:</span>
            <span class="sim-val font-mono text-red font-bold">${{ simEstLoss.toFixed(2) }}</span>
          </div>

          <div class="sim-note">
            Note: Simulator provides manual reference. Always review the MT5 bridge symbol specification before entering orders.
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
