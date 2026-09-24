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
})

const emit = defineEmits(['select-symbol', 'refresh', 'open-settings', 'logout'])

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
  return 'Not available'
})
</script>

<template>
  <header class="top-bar">
    <div class="topbar-left">
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

      <button
        class="btn btn-secondary btn-sm"
        title="Settings"
        @click="emit('open-settings')"
      >
        <span>Settings</span>
      </button>
    </div>
  </header>
</template>
