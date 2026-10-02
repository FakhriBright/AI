<script setup>
import { computed } from 'vue'
import { formatPrice } from '../utils/formatters'

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
  liveTick: {
    type: Object,
    default: null,
  },
  latestCandle: {
    type: Object,
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
  currentTheme: {
    type: String,
    default: 'light',
  },
})

const emit = defineEmits(['select-symbol', 'refresh', 'toggle-theme', 'logout'])

const isConnected = computed(() => {
  return props.bridgeHealth?.bridge_status === 'ok' && props.bridgeHealth?.data_source_connected !== false
})

const formattedPrice = computed(() => {
  if (props.liveTick?.bid !== null && props.liveTick?.bid !== undefined) {
    return formatPrice(props.liveTick.bid, props.selectedSymbol)
  }
  if (props.currentPrice !== null && props.currentPrice !== undefined) {
    return formatPrice(props.currentPrice, props.selectedSymbol)
  }
  if (props.latestCandle?.close) {
    return formatPrice(props.latestCandle.close, props.selectedSymbol)
  }
  return 'Not available'
})
</script>

<template>
  <header class="top-bar">
    <div class="topbar-left">
      <!-- Single Symbol Selector -->
      <div class="symbol-selector-wrap">
        <select
          id="symbol-select"
          :value="selectedSymbol"
          @change="emit('select-symbol', $event.target.value)"
        >
          <option v-for="sym in symbols" :key="sym" :value="sym">
            {{ sym }}
          </option>
        </select>
      </div>

      <div class="price-readout">
        <span class="text-xs text-muted uppercase">Live Price:</span>
        <span class="font-mono font-bold text-accent" style="margin-left: 6px;">{{ formattedPrice }}</span>
      </div>
    </div>

    <div class="topbar-right">
      <!-- Theme Switcher Toggle (Dark / Light Mode) -->
      <button
        class="theme-toggle-switch"
        :class="{ 'is-dark': currentTheme === 'dark' }"
        role="switch"
        :aria-checked="currentTheme === 'dark'"
        :title="currentTheme === 'dark' ? 'Switch to Light Mode' : 'Switch to Dark Mode'"
        @click="emit('toggle-theme')"
      >
        <div class="toggle-track">
          <div class="track-icon sun-icon" :class="{ active: currentTheme === 'light' }">
            <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="5" />
              <line x1="12" y1="1" x2="12" y2="3" />
              <line x1="12" y1="21" x2="12" y2="23" />
              <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
              <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
              <line x1="1" y1="12" x2="3" y2="12" />
              <line x1="21" y1="12" x2="23" y2="12" />
              <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
              <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
            </svg>
          </div>
          <div class="track-icon moon-icon" :class="{ active: currentTheme === 'dark' }">
            <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z" />
            </svg>
          </div>
          <div class="toggle-thumb">
            <svg v-if="currentTheme === 'dark'" class="thumb-icon moon" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.2">
              <path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z" />
            </svg>
            <svg v-else class="thumb-icon sun" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.2">
              <circle cx="12" cy="12" r="4" />
              <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" />
            </svg>
          </div>
        </div>
      </button>

      <!-- MT5 Connection Status Pill -->
      <div class="status-pill" :class="isConnected ? 'online' : 'offline'">
        <span class="dot-status"></span>
        <span>{{ isConnected ? 'MT5 ONLINE' : 'MT5 OFFLINE' }}</span>
      </div>

      <button
        class="btn btn-secondary btn-sm"
        :disabled="isLoading"
        title="Refresh Data"
        @click="emit('refresh')"
      >
        <span>{{ isLoading ? 'Loading...' : 'Refresh' }}</span>
      </button>
    </div>
  </header>
</template>
