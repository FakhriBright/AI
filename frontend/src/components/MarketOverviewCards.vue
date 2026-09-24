<script setup>
import { computed } from 'vue'
import { getBiasBadgeClass, getStatusBadgeClass, formatPrice } from '../utils/formatters'

const props = defineProps({
  symbol: { type: String, default: 'EURUSDm' },
  marketBias: { type: Object, default: null },
  selectedScenario: { type: Object, default: null },
  confirmation: { type: Object, default: null },
  tradePlan: { type: Object, default: null },
  currentPrice: { type: [Number, String], default: null },
  latestCandle: { type: Object, default: null },
})

const symbolFullNames = {
  EURUSDm: 'Euro / US Dollar',
  XAUUSDm: 'Gold / US Dollar',
  GBPUSDm: 'British Pound / US Dollar',
  USDJPYm: 'US Dollar / Japanese Yen',
}

const fullName = computed(() => symbolFullNames[props.symbol] || props.symbol)

const formattedPrice = computed(() => {
  if (props.currentPrice !== null && props.currentPrice !== undefined) {
    return formatPrice(props.currentPrice, props.symbol)
  }
  if (props.latestCandle?.close) {
    return formatPrice(props.latestCandle.close, props.symbol)
  }
  return '—'
})

const bias = computed(() => props.marketBias?.overall || 'Neutral')
const marketCondition = computed(() => {
  if (props.selectedScenario?.name) {
    return props.selectedScenario.name.replace(/_/g, ' ').toUpperCase()
  }
  return 'Trending'
})
const planStatus = computed(() => props.tradePlan?.status || 'waiting')
</script>

<template>
  <div class="market-header-strip">
    <div class="market-header-info">
      <div>
        <h1 class="symbol-hero">{{ symbol }}</h1>
        <span class="symbol-subname">{{ fullName }}</span>
      </div>
      <span class="price-hero">{{ formattedPrice }}</span>
    </div>

    <div class="market-header-tags">
      <span class="badge" :class="getBiasBadgeClass(bias)">
        {{ String(bias).toUpperCase() }}
      </span>

      <span class="badge badge-neutral">
        {{ marketCondition }}
      </span>

      <span class="badge" :class="getStatusBadgeClass(planStatus)">
        {{ String(planStatus).replace(/_/g, ' ').toUpperCase() }}
      </span>
    </div>
  </div>
</template>
