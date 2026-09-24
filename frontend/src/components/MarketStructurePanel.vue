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

const structureState = computed(() => {
  return currentTfData.value?.structure || 'Neutral'
})

// Extract latest swing points by label
const swingHH = computed(() => swings.value.find(s => s.label === 'HH'))
const swingHL = computed(() => swings.value.find(s => s.label === 'HL'))
const swingLH = computed(() => swings.value.find(s => s.label === 'LH'))
const swingLL = computed(() => swings.value.find(s => s.label === 'LL'))

function getLabelBadgeClass(label) {
  if (label === 'HH' || label === 'HL') return 'badge-bullish'
  if (label === 'LH' || label === 'LL') return 'badge-bearish'
  return 'badge-neutral'
}
</script>

<template>
  <div class="card-box">
    <div class="card-header">
      <span class="card-title">MARKET STRUCTURE</span>
      <!-- Timeframe Segmented Control -->
      <div class="segmented-control">
        <button
          v-for="tf in timeframesList"
          :key="tf"
          class="segment-btn"
          :class="{ active: selectedTf === tf }"
          @click="selectedTf = tf"
        >
          {{ tf }}
        </button>
      </div>
    </div>

    <div class="card-body">
      <!-- Structure State Header -->
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px;">
        <span class="text-xs text-muted font-bold">STRUCTURE STATE ({{ selectedTf }}):</span>
        <span class="badge" :class="getBiasBadgeClass(structureState)">
          {{ structureState.toUpperCase() }}
        </span>
      </div>

      <!-- Clean 4-Grid Key Swing Levels -->
      <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; margin-bottom: 12px;">
        <div class="metric-card" style="padding: 8px 10px;">
          <div style="display: flex; justify-content: space-between; align-items: center;">
            <span class="badge badge-sm badge-bullish">HH</span>
            <span class="text-xs text-muted">Higher High</span>
          </div>
          <span class="metric-val font-mono text-sm" style="margin-top: 4px;">
            {{ swingHH ? formatPrice(swingHH.price, symbol) : '—' }}
          </span>
        </div>

        <div class="metric-card" style="padding: 8px 10px;">
          <div style="display: flex; justify-content: space-between; align-items: center;">
            <span class="badge badge-sm badge-bullish">HL</span>
            <span class="text-xs text-muted">Higher Low</span>
          </div>
          <span class="metric-val font-mono text-sm" style="margin-top: 4px;">
            {{ swingHL ? formatPrice(swingHL.price, symbol) : '—' }}
          </span>
        </div>

        <div class="metric-card" style="padding: 8px 10px;">
          <div style="display: flex; justify-content: space-between; align-items: center;">
            <span class="badge badge-sm badge-bearish">LH</span>
            <span class="text-xs text-muted">Lower High</span>
          </div>
          <span class="metric-val font-mono text-sm" style="margin-top: 4px;">
            {{ swingLH ? formatPrice(swingLH.price, symbol) : '—' }}
          </span>
        </div>

        <div class="metric-card" style="padding: 8px 10px;">
          <div style="display: flex; justify-content: space-between; align-items: center;">
            <span class="badge badge-sm badge-bearish">LL</span>
            <span class="text-xs text-muted">Lower Low</span>
          </div>
          <span class="metric-val font-mono text-sm" style="margin-top: 4px;">
            {{ swingLL ? formatPrice(swingLL.price, symbol) : '—' }}
          </span>
        </div>
      </div>

      <!-- Expandable Swing History Table -->
      <details class="details-accordion">
        <summary style="padding: 8px 12px; font-size: 11px;">View Structure Swing Log ({{ swings.length }})</summary>
        <div style="padding: 8px 12px;">
          <div v-if="swings.length" style="overflow-x: auto;">
            <table class="terminal-table table-compact" style="width: 100%; font-size: 11px;">
              <thead>
                <tr>
                  <th style="text-align: left; padding: 4px;">Type</th>
                  <th style="text-align: left; padding: 4px;">Label</th>
                  <th style="text-align: right; padding: 4px;">Price</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(s, idx) in swings.slice(0, 6)" :key="idx">
                  <td style="padding: 4px;" class="text-muted">{{ s.type === 'swing_high' ? 'High' : 'Low' }}</td>
                  <td style="padding: 4px;">
                    <span class="badge badge-sm" :class="getLabelBadgeClass(s.label)">{{ s.label || '—' }}</span>
                  </td>
                  <td style="padding: 4px; text-align: right;" class="font-mono font-bold">{{ formatPrice(s.price, symbol) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div v-else class="text-xs text-muted p-2">
            No swing points detected.
          </div>
        </div>
      </details>
    </div>
  </div>
</template>
