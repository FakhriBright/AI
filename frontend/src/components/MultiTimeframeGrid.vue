<script setup>
import { computed } from 'vue'
import { getBiasBadgeClass } from '../utils/formatters'

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

const timeframesList = ['D1', 'H4', 'H1', 'M15', 'M5']

const timeframesData = computed(() => {
  return props.multiTimeframe?.timeframes || {}
})

function getTrend(tf) {
  const data = timeframesData.value[tf]
  if (!data) return 'Neutral'
  return data.trend || data.structure || 'Neutral'
}
</script>

<template>
  <div class="card-box">
    <div class="card-header">
      <span class="card-title">MULTI-TIMEFRAME ALIGNMENT</span>
    </div>
    <div class="card-body">
      <div class="mtf-row">
        <div v-for="tf in timeframesList" :key="tf" class="mtf-chip">
          <span class="mtf-label">{{ tf }}</span>
          <span class="badge badge-sm" :class="getBiasBadgeClass(getTrend(tf))">
            {{ getTrend(tf).toUpperCase() }}
          </span>
        </div>
      </div>
    </div>
  </div>
</template>
