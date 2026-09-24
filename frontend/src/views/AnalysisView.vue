<script setup>
import { computed } from 'vue'
import MarketOverviewCards from '../components/MarketOverviewCards.vue'
import TradePlanPanel from '../components/TradePlanPanel.vue'
import InteractiveChart from '../components/InteractiveChart.vue'
import KeyLevelsPanel from '../components/KeyLevelsPanel.vue'
import MarketStructurePanel from '../components/MarketStructurePanel.vue'
import MultiTimeframeGrid from '../components/MultiTimeframeGrid.vue'
import ScenarioPanel from '../components/ScenarioPanel.vue'
import AIReasoningPanel from '../components/AIReasoningPanel.vue'

const props = defineProps({
  symbol: { type: String, default: 'EURUSDm' },
  analysisData: { type: Object, default: null },
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
      :current-price="analysisData?.key_levels?.current_price"
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

    <!-- Hero Interactive Candlestick Chart -->
    <InteractiveChart
      :symbol="symbol"
      :key-levels="analysisData?.key_levels"
      :selected-scenario="analysisData?.selected_scenario"
    />

    <!-- Single Coherent Trade Plan Module -->
    <TradePlanPanel
      :trade-plan="analysisData?.trade_plan"
      :stop-plan="analysisData?.stop_plan"
      :symbol="symbol"
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

    <!-- Progressive Disclosure Details Accordion -->
    <details class="details-accordion">
      <summary>View Technical Details & Scenarios</summary>
      <div class="card-body" style="display: flex; flex-direction: column; gap: 16px;">
        <ScenarioPanel
          :selected-scenario="analysisData?.selected_scenario"
          :scenario-analysis="analysisData?.scenario_analysis"
          :symbol="symbol"
        />
        <AIReasoningPanel
          :ai-data="analysisData?.ai"
          :symbol="symbol"
        />
      </div>
    </details>
  </div>
</template>
