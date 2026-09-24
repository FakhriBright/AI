<script setup>
import { computed } from 'vue'
import { formatPrice, getBiasBadgeClass } from '../utils/formatters'

const props = defineProps({
  symbol: { type: String, default: 'EURUSDm' },
  symbols: { type: Array, default: () => ['EURUSDm', 'XAUUSDm'] },
  analysisData: { type: Object, default: null },
  bridgeHealth: { type: Object, default: () => ({}) },
  isBridgeOffline: { type: Boolean, default: false },
})

const emit = defineEmits(['select-symbol', 'retry'])

const symbolInfoMap = {
  EURUSDm: { name: 'Euro / US Dollar', digits: 5, category: 'Forex Major' },
  XAUUSDm: { name: 'Gold / US Dollar', digits: 2, category: 'Metals' },
  GBPUSDm: { name: 'British Pound / US Dollar', digits: 5, category: 'Forex Major' },
  USDJPYm: { name: 'US Dollar / Japanese Yen', digits: 3, category: 'Forex Major' },
}

const activeInfo = computed(() => symbolInfoMap[props.symbol] || { name: props.symbol, digits: 5, category: 'Trading Instrument' })

const currentPrice = computed(() => {
  if (props.analysisData?.key_levels?.current_price !== null && props.analysisData?.key_levels?.current_price !== undefined) {
    return formatPrice(props.analysisData.key_levels.current_price, props.symbol)
  }
  if (props.analysisData?.latest_candle?.close) {
    return formatPrice(props.analysisData.latest_candle.close, props.symbol)
  }
  return '—'
})

const latestSpread = computed(() => props.analysisData?.latest_candle?.spread ?? '—')
const marketBias = computed(() => props.analysisData?.market_bias?.overall || 'Neutral')
</script>

<template>
  <div class="central-workspace">
    <!-- Market Workstation Banner -->
    <div class="card-box">
      <div class="card-header">
        <span class="card-title">MARKET WORKSTATION</span>
        <span class="badge" :class="isBridgeOffline ? 'badge-warning' : 'badge-bullish'">
          {{ isBridgeOffline ? 'FEED DISCONNECTED' : 'MT5 LIVE DATA FEED' }}
        </span>
      </div>
      <div class="card-body">
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 16px;">
          <div>
            <h1 style="font-size: 24px; font-weight: 700; font-family: var(--font-mono);">{{ symbol }}</h1>
            <span class="text-muted text-sm">{{ activeInfo.name }} &bull; {{ activeInfo.category }}</span>
          </div>
          <div>
            <span class="text-xs text-muted block uppercase">Current Price</span>
            <span style="font-size: 26px; font-weight: 700; font-family: var(--font-mono);" class="text-accent">
              {{ currentPrice }}
            </span>
          </div>
        </div>
      </div>
    </div>

    <!-- Supported Symbols Grid -->
    <div class="card-box">
      <div class="card-header">
        <span class="card-title">AVAILABLE INSTRUMENTS</span>
      </div>
      <div class="card-body">
        <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 12px;">
          <div
            v-for="sym in symbols"
            :key="sym"
            class="metric-card"
            style="cursor: pointer; transition: all 0.15s ease;"
            :style="{ borderColor: symbol === sym ? 'var(--accent-primary)' : 'var(--border-main)' }"
            @click="emit('select-symbol', sym)"
          >
            <div style="display: flex; justify-content: space-between; align-items: center;">
              <span class="font-mono font-bold text-sm">{{ sym }}</span>
              <span v-if="symbol === sym" class="badge badge-sm badge-bullish">Active</span>
            </div>
            <span class="text-xs text-muted" style="margin-top: 4px;">{{ symbolInfoMap[sym]?.name || 'Instrument' }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Data Connection Diagnostics Summary -->
    <div class="card-box">
      <div class="card-header">
        <span class="card-title">DATA CONNECTION STATUS</span>
      </div>
      <div class="card-body">
        <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px;">
          <div class="metric-card">
            <span class="metric-label">MT5 Bridge Status</span>
            <span class="metric-val text-sm font-mono" :class="isBridgeOffline ? 'text-amber' : 'text-green'">
              {{ bridgeHealth?.bridge_status === 'ok' ? 'CONNECTED' : 'DISCONNECTED' }}
            </span>
          </div>

          <div class="metric-card">
            <span class="metric-label">Data Source</span>
            <span class="metric-val text-sm font-mono" :class="bridgeHealth?.data_source_connected ? 'text-green' : 'text-amber'">
              {{ bridgeHealth?.data_source_connected ? 'MT5 TERMINAL LIVE' : 'UNAVAILABLE' }}
            </span>
          </div>

          <div class="metric-card">
            <span class="metric-label">Current Spread</span>
            <span class="metric-val text-sm font-mono">{{ latestSpread }} pts</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
