<script setup>
import { computed, ref } from 'vue'
import {
  formatPrice,
  formatDateTimeUtc,
  getBiasBadgeClass,
} from '../utils/formatters'

const props = defineProps({
  multiTimeframe: {
    type: Object,
    default: () => ({}),
  },
  symbol: {
    type: String,
    default: 'EURUSDm',
  },
  initialTimeframe: {
    type: String,
    default: 'M5',
  },
})

const selectedTf = ref(props.initialTimeframe || 'M5')
const timeframesList = ['D1', 'H4', 'H1', 'M30', 'M15', 'M5', 'M1']

const currentTfData = computed(() => {
  return props.multiTimeframe?.timeframes?.[selectedTf.value] || null
})

const swings = computed(() => {
  return currentTfData.value?.swings || []
})

const structureDirection = computed(() => {
  return currentTfData.value?.structure || 'Unavailable'
})

function getLabelColorClass(label) {
  if (!label) return 'label-neutral'
  if (label === 'HH' || label === 'HL') return 'label-bullish'
  if (label === 'LH' || label === 'LL') return 'label-bearish'
  return 'label-neutral'
}

function getLabelDesc(label) {
  switch (label) {
    case 'HH': return 'Higher High (Bullish Expansion)'
    case 'HL': return 'Higher Low (Bullish Retracement)'
    case 'LH': return 'Lower High (Bearish Retracement)'
    case 'LL': return 'Lower Low (Bearish Expansion)'
    default: return 'Swing Reference'
  }
}
</script>

<template>
  <div class="panel-container">
    <div class="panel-header">
      <div class="panel-title-wrap">
        <svg class="panel-icon" viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
          <path d="M3.5 18.49l6-6.01 4 4L22 6.92l-1.41-1.41-7.09 7.97-4-4L2 16.99z" />
        </svg>
        <h2 class="panel-title">MARKET STRUCTURE (HH / HL / LH / LL)</h2>
      </div>

      <!-- Timeframe Selector Tabs -->
      <div class="tf-btn-group">
        <button
          v-for="tf in timeframesList"
          :key="tf"
          class="tf-tab-btn"
          :class="{ active: selectedTf === tf }"
          @click="selectedTf = tf"
        >
          {{ tf }}
        </button>
      </div>
    </div>

    <!-- Structure Summary Banner -->
    <div class="structure-summary-banner">
      <div class="summary-left">
        <span class="structure-caption">STRUCTURE STATE ({{ selectedTf }}):</span>
        <span class="badge" :class="getBiasBadgeClass(structureDirection)">
          {{ structureDirection.toUpperCase() }}
        </span>
      </div>
      <div class="structure-legend">
        <span class="legend-item"><span class="legend-dot dot-hh"></span>HH: Higher High</span>
        <span class="legend-item"><span class="legend-dot dot-hl"></span>HL: Higher Low</span>
        <span class="legend-item"><span class="legend-dot dot-lh"></span>LH: Lower High</span>
        <span class="legend-item"><span class="legend-dot dot-ll"></span>LL: Lower Low</span>
      </div>
    </div>

    <!-- Swings Visual Flow / Cards -->
    <div v-if="swings.length" class="swings-flow-wrap">
      <div class="swings-track">
        <div
          v-for="(swing, idx) in swings"
          :key="idx"
          class="swing-node-card"
          :class="getLabelColorClass(swing.label)"
        >
          <div class="node-header">
            <span class="node-badge" :class="getLabelColorClass(swing.label)">
              {{ swing.label || '—' }}
            </span>
            <span class="node-type">
              {{ swing.type === 'swing_high' ? 'HIGH' : 'LOW' }}
            </span>
          </div>

          <div class="node-price font-mono">
            {{ formatPrice(swing.price, symbol) }}
          </div>

          <div class="node-desc">
            {{ getLabelDesc(swing.label) }}
          </div>

          <div class="node-time">
            {{ formatDateTimeUtc(swing.time_utc) }}
          </div>
        </div>
      </div>
    </div>
    <div v-else class="empty-state-box">
      <span>No swing points detected for {{ selectedTf }} on {{ symbol }}.</span>
    </div>

    <!-- Swings Log Table -->
    <div v-if="swings.length" class="table-responsive mt-3">
      <table class="terminal-table table-compact">
        <thead>
          <tr>
            <th>#</th>
            <th>TIME (UTC)</th>
            <th>SWING TYPE</th>
            <th>LABEL</th>
            <th>PRICE</th>
            <th>STRUCTURE SIGNIFICANCE</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(swing, idx) in swings.slice().reverse()" :key="idx">
            <td class="text-muted">{{ swings.length - idx }}</td>
            <td class="font-mono text-xs">{{ formatDateTimeUtc(swing.time_utc) }}</td>
            <td>
              <span
                class="badge badge-sm"
                :class="swing.type === 'swing_high' ? 'badge-bullish' : 'badge-bearish'"
              >
                {{ swing.type === 'swing_high' ? 'SWING HIGH' : 'SWING LOW' }}
              </span>
            </td>
            <td>
              <span class="label-pill font-bold" :class="getLabelColorClass(swing.label)">
                {{ swing.label || 'None' }}
              </span>
            </td>
            <td class="font-mono font-bold">{{ formatPrice(swing.price, symbol) }}</td>
            <td class="text-xs text-muted">{{ getLabelDesc(swing.label) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
