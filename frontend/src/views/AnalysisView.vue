<script setup>
import { computed } from 'vue'
import MarketOverviewCards from '../components/MarketOverviewCards.vue'
import TradePlanPanel from '../components/TradePlanPanel.vue'
import InteractiveChart from '../components/InteractiveChart.vue'
import KeyLevelsPanel from '../components/KeyLevelsPanel.vue'
import MarketStructurePanel from '../components/MarketStructurePanel.vue'
import MultiTimeframeGrid from '../components/MultiTimeframeGrid.vue'
import ScenarioPanel from '../components/ScenarioPanel.vue'

const props = defineProps({
  symbol: { type: String, default: 'XAUUSDm' },
  analysisData: { type: Object, default: null },
  // Reason the latest GET /analysis failed (backend detail), '' when it succeeded.
  analysisError: { type: String, default: '' },
  liveTick: { type: Object, default: null },
  isBridgeOffline: { type: Boolean, default: false },
})

const emit = defineEmits(['retry'])
</script>

<template>
  <div class="central-workspace">
    <!-- Main Market Header -->
    <MarketOverviewCards
      :symbol="symbol"
      :market-bias="analysisData?.market_bias"
      :selected-scenario="analysisData?.selected_scenario"
      :confirmation="analysisData?.confirmation"
      :trade-plan="analysisData?.trade_plan"
      :current-price="liveTick?.bid ?? analysisData?.key_levels?.current_price"
      :latest-candle="analysisData?.latest_candle"
    />

    <!-- Friendly MT5 Disconnected Banner -->
    <div v-if="isBridgeOffline" class="mt5-offline-banner">
      <div>
        <strong>MT5 OFFLINE:</strong> Live market data feed unavailable. Start the MT5 Bridge on Windows host to stream live data.
      </div>
      <button class="btn btn-secondary btn-sm" @click="emit('retry')">
        Retry
      </button>
    </div>

    <!-- Analysis request failed: show the backend's reason (no silent empty panels) -->
    <div v-if="analysisError" class="mt5-offline-banner">
      <div>
        <strong>ANALYSIS UNAVAILABLE:</strong> {{ analysisError }}
        <span v-if="analysisData"> Showing the last successful analysis ({{ analysisData.generated_at_utc?.slice(11, 16) }} UTC).</span>
      </div>
      <button class="btn btn-secondary btn-sm" @click="emit('retry')">
        Retry
      </button>
    </div>

    <!-- Hero Interactive Candlestick Chart -->
    <InteractiveChart
      :symbol="symbol"
      :key-levels="analysisData?.key_levels"
      :selected-scenario="analysisData?.selected_scenario"
      :overlay-payload="analysisData?.chart_overlays"
      :generated-at="analysisData?.generated_at_utc"
      :analysis-candle="analysisData?.latest_candle"
      :live-tick="liveTick"
      :trade-plan="analysisData?.trade_plan"
      :market-bias="analysisData?.market_bias"
      :scenarios="analysisData?.scenarios"
      :multi-timeframe="analysisData?.multi_timeframe"
    />

    <!-- Single Coherent Trade Plan Module -->
    <TradePlanPanel
      :trade-plan="analysisData?.trade_plan"
      :stop-plan="analysisData?.stop_plan"
      :symbol="symbol"
      :market-bias="analysisData?.market_bias"
      :selected-scenario="analysisData?.selected_scenario"
      :confirmation="analysisData?.confirmation"
    />

    <!-- Key Analysis Grid -->
    <div class="two-col-grid">
      <KeyLevelsPanel
        :key-levels="analysisData?.key_levels"
        :selected-scenario="analysisData?.selected_scenario"
        :symbol="symbol"
      />
      <MarketStructurePanel
        :multi-timeframe="analysisData?.multi_timeframe"
        :symbol="symbol"
        initial-timeframe="M5"
      />
    </div>

    <!-- Multi-Timeframe Alignment Row -->
    <MultiTimeframeGrid
      :multi-timeframe="analysisData?.multi_timeframe"
      :symbol="symbol"
    />

    <!-- Progressive Disclosure Details Accordion (deterministic engine scenarios) -->
    <details class="details-accordion">
      <summary>View Technical Details & Scenarios</summary>
      <div class="card-body" style="display: flex; flex-direction: column; gap: 16px;">
        <ScenarioPanel
          :scenarios-data="analysisData?.scenarios"
          :selected-scenario="analysisData?.selected_scenario"
          :confirmation="analysisData?.confirmation"
          :symbol="symbol"
        />
      </div>
    </details>
  </div>
</template>
