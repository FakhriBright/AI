<script setup>
import { computed, ref } from 'vue'
import {
  formatPrice,
  formatNumber,
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
})

const emit = defineEmits(['select-tf'])

const timeframesList = ['D1', 'H4', 'H1', 'M30', 'M15', 'M5', 'M1']
const activeDetailsTf = ref('M5')

const timeframesData = computed(() => {
  return props.multiTimeframe?.timeframes || {}
})

function getTfData(tf) {
  return timeframesData.value[tf] || null
}

function selectTf(tf) {
  activeDetailsTf.value = tf
  emit('select-tf', tf)
}

function getRsiClass(val) {
  if (val === null || val === undefined) return ''
  const num = Number(val)
  if (num >= 70) return 'text-red font-bold'
  if (num <= 30) return 'text-green font-bold'
  return 'text-normal'
}

function getMacdHistClass(val) {
  if (val === null || val === undefined) return ''
  return Number(val) >= 0 ? 'text-green' : 'text-red'
}
</script>

<template>
  <div class="panel-container">
    <div class="panel-header">
      <div class="panel-title-wrap">
        <svg class="panel-icon" viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
          <path d="M4 4h4v4H4zm6 0h4v4h-4zm6 0h4v4h-4zM4 10h4v4H4zm6 0h4v4h-4zm6 0h4v4h-4zM4 16h4v4H4zm6 0h4v4h-4zm6 0h4v4h-4z" />
        </svg>
        <h2 class="panel-title">MULTI-TIMEFRAME ANALYSIS (D1 → M1)</h2>
      </div>
      <span class="panel-subtitle">Multi-Horizon Technical Alignment Engine</span>
    </div>

    <!-- Table Matrix -->
    <div class="table-responsive">
      <table class="terminal-table">
        <thead>
          <tr>
            <th>TF</th>
            <th>TREND</th>
            <th>STRUCTURE</th>
            <th>EMA</th>
            <th>RSI</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="tf in timeframesList"
            :key="tf"
            :class="{ 'row-active': activeDetailsTf === tf }"
            @click="selectTf(tf)"
          >
            <!-- Timeframe Pill -->
            <td>
              <span class="tf-badge" :class="activeDetailsTf === tf ? 'tf-badge-active' : ''">
                {{ tf }}
              </span>
            </td>


            <!-- Trend -->
            <td>
              <span
                v-if="getTfData(tf)?.trend"
                class="badge badge-sm"
                :class="getBiasBadgeClass(getTfData(tf)?.trend)"
              >
                {{ getTfData(tf)?.trend.toUpperCase() }}
              </span>
              <span v-else class="text-muted">Unavailable</span>
            </td>

            <!-- Structure -->
            <td>
              <span
                v-if="getTfData(tf)?.structure"
                class="badge badge-sm"
                :class="getBiasBadgeClass(getTfData(tf)?.structure)"
              >
                {{ getTfData(tf)?.structure.toUpperCase() }}
              </span>
              <span v-else class="text-muted">Unavailable</span>
            </td>

            <!-- EMA Alignment -->
            <td>
              <span
                v-if="getTfData(tf)?.ema_alignment"
                class="badge badge-sm"
                :class="getBiasBadgeClass(getTfData(tf)?.ema_alignment)"
              >
                {{ getTfData(tf)?.ema_alignment }}
              </span>
              <span v-else class="text-muted">Unavailable</span>
            </td>


            <!-- RSI 14 -->
            <td class="font-mono">
              <span v-if="getTfData(tf)?.rsi14 !== null && getTfData(tf)?.rsi14 !== undefined" :class="getRsiClass(getTfData(tf)?.rsi14)">
                {{ formatNumber(getTfData(tf)?.rsi14, 0) }}
              </span>
              <span v-else class="text-muted">Unavailable</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Active Timeframe Reasons Box -->
    <div v-if="getTfData(activeDetailsTf)" class="tf-details-card">
      <div class="tf-details-header">
        <span class="tf-inspect-title">
          [{{ activeDetailsTf }}] ALIGNMENT RATIONALE & SIGNALS
        </span>
        <span class="tf-swings-count">
          Swings: {{ getTfData(activeDetailsTf)?.swings?.length ?? 0 }} detected
        </span>
      </div>
      <div v-if="getTfData(activeDetailsTf)?.reasons?.length" class="tf-reasons-list">
        <span
          v-for="(reason, idx) in getTfData(activeDetailsTf)?.reasons"
          :key="idx"
          class="reason-tag"
        >
          {{ reason.replace(/_/g, ' ') }}
        </span>
      </div>
      <div v-else class="text-muted text-xs">
        No specific directional reasons flagged for this timeframe.
      </div>
    </div>
  </div>
</template>
