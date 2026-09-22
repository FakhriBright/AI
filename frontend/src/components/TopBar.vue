<script setup>
import { computed } from 'vue'
import { formatDateTimeUtc, formatPrice } from '../utils/formatters'

const props = defineProps({
  symbols: {
    type: Array,
    default: () => ['EURUSDm', 'XAUUSDm'],
  },
  selectedSymbol: {
    type: String,
    default: 'EURUSDm',
  },
  currentPrice: {
    type: [Number, String],
    default: null,
  },
  latestCandle: {
    type: Object,
    default: null,
  },
  generatedAt: {
    type: String,
    default: null,
  },
  isLoading: {
    type: Boolean,
    default: false,
  },
  bridgeHealth: {
    type: Object,
    default: () => ({}),
  },
  autoRefreshInterval: {
    type: Number,
    default: 0,
  },
})

const emit = defineEmits([
  'select-symbol',
  'refresh',
  'update-auto-refresh',
  'logout',
])

const isConnected = computed(() => {
  return props.bridgeHealth?.bridge_status === 'ok' && props.bridgeHealth?.data_source_connected !== false
})

const formattedPrice = computed(() => {
  if (props.currentPrice !== null && props.currentPrice !== undefined) {
    return formatPrice(props.currentPrice, props.selectedSymbol)
  }
  if (props.latestCandle?.close) {
    return formatPrice(props.latestCandle.close, props.selectedSymbol)
  }
  return 'Unavailable'
})

const spreadInfo = computed(() => {
  if (props.latestCandle?.spread !== null && props.latestCandle?.spread !== undefined) {
    return `${props.latestCandle.spread} pts`
  }
  return null
})
</script>

<template>
  <header class="terminal-topbar">
    <!-- Left: Symbol Selector & Price Ticker -->
    <div class="topbar-left">
      <div class="symbol-selector-container">
        <label class="topbar-label" for="symbol-select">ACTIVE INSTRUMENT</label>
        <div class="symbol-select-wrap">
          <select
            id="symbol-select"
            class="symbol-select"
            :value="selectedSymbol"
            @change="emit('select-symbol', $event.target.value)"
          >
            <option v-for="sym in symbols" :key="sym" :value="sym">
              {{ sym }}
            </option>
          </select>
          <span class="select-chevron">▼</span>
        </div>
      </div>

      <!-- Quick Toggles for the two primary symbols -->
      <div class="quick-symbols">
        <button
          class="quick-sym-btn"
          :class="{ active: selectedSymbol === 'EURUSDm' }"
          @click="emit('select-symbol', 'EURUSDm')"
        >
          EURUSDm
        </button>
        <button
          class="quick-sym-btn"
          :class="{ active: selectedSymbol === 'XAUUSDm' }"
          @click="emit('select-symbol', 'XAUUSDm')"
        >
          XAUUSDm
        </button>
      </div>

      <!-- Price Readout -->
      <div class="topbar-price-box">
        <span class="price-title">MARKET PRICE</span>
        <div class="price-value-row">
          <span class="price-num">{{ formattedPrice }}</span>
          <span v-if="spreadInfo" class="spread-pill">Spread: {{ spreadInfo }}</span>
        </div>
      </div>
    </div>

    <!-- Right: Market Status, Refresh Controls & Timestamp -->
    <div class="topbar-right">
      <!-- Market Health Indicator -->
      <div class="market-status-pill" :class="isConnected ? 'status-online' : 'status-warning'">
        <span class="pulse-dot"></span>
        <span class="status-text">
          {{ isConnected ? 'MT5 FEED LIVE' : 'DATA RECONNECTING' }}
        </span>
      </div>

      <!-- Last Update Timestamp -->
      <div class="update-time-box">
        <span class="time-label">ANALYSIS UTC</span>
        <span class="time-value">{{ formatDateTimeUtc(generatedAt) }}</span>
      </div>

      <!-- Auto Refresh Selector -->
      <div class="auto-refresh-wrap">
        <label class="auto-refresh-label" for="auto-refresh-select">POLL</label>
        <select
          id="auto-refresh-select"
          class="auto-refresh-select"
          :value="autoRefreshInterval"
          @change="emit('update-auto-refresh', Number($event.target.value))"
        >
          <option :value="0">Off</option>
          <option :value="15">15s</option>
          <option :value="30">30s</option>
          <option :value="60">60s</option>
        </select>
      </div>

      <!-- Manual Refresh Button -->
      <button
        class="refresh-btn"
        :disabled="isLoading"
        title="Refresh Market Analysis"
        @click="emit('refresh')"
      >
        <svg
          class="refresh-icon"
          :class="{ spinning: isLoading }"
          viewBox="0 0 24 24"
          width="16"
          height="16"
          fill="currentColor"
        >
          <path d="M17.65 6.35A7.958 7.958 0 0012 4c-4.42 0-7.99 3.58-7.99 8s3.57 8 7.99 8c3.73 0 6.84-2.55 7.73-6h-2.08A5.99 5.99 0 0112 18c-3.31 0-6-2.69-6-6s2.69-6 6-6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z" />
        </svg>
        <span>{{ isLoading ? 'Analyzing...' : 'Refresh' }}</span>
      </button>
    </div>
  </header>
</template>
