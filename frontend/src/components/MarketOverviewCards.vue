<script setup>
import { computed } from 'vue'
import { getBiasBadgeClass, getStatusBadgeClass } from '../utils/formatters'

const props = defineProps({
  symbol: { type: String, default: 'EURUSDm' },
  marketBias: { type: Object, default: null },
  selectedScenario: { type: Object, default: null },
  confirmation: { type: Object, default: null },
  tradePlan: { type: Object, default: null },
  stopPlan: { type: Object, default: null },
})

const overallBias = computed(() => props.marketBias?.overall || 'Unavailable')
const scenarioName = computed(() => {
  if (!props.selectedScenario?.name) return 'Unavailable'
  return props.selectedScenario.name.replace(/_/g, ' ').toUpperCase()
})
const planStatus = computed(() => props.tradePlan?.status || 'waiting')
const isConfirmed = computed(() => Boolean(props.confirmation?.confirmed))

const atrValue = computed(() => {
  if (props.selectedScenario?.atr_reference !== null && props.selectedScenario?.atr_reference !== undefined) {
    return props.selectedScenario.atr_reference
  }
  if (props.stopPlan?.atr_reference !== null && props.stopPlan?.atr_reference !== undefined) {
    return props.stopPlan.atr_reference
  }
  return null
})
</script>

<template>
  <section class="market-state-section">
    <div class="state-header">
      <h2 class="section-title">MARKET STATE</h2>
    </div>
    
    <div class="state-content">
      <div class="state-row">
        <span class="state-label">Bias:</span>
        <span class="state-val font-bold" :class="getBiasBadgeClass(overallBias)">
          {{ overallBias === 'Unavailable' ? 'Unavailable' : overallBias.toUpperCase() }}
        </span>
      </div>
      
      <div class="state-row">
        <span class="state-label">Scenario:</span>
        <span class="state-val">{{ scenarioName }}</span>
      </div>
      
      <div class="state-row">
        <span class="state-label">Status:</span>
        <span class="state-val font-bold" :class="getStatusBadgeClass(planStatus)">
          {{ planStatus.toUpperCase() }}
        </span>
      </div>

      <div v-if="atrValue" class="state-row">
        <span class="state-label">ATR:</span>
        <span class="state-val font-mono">{{ atrValue }}</span>
      </div>
    </div>

    <div class="state-explanation mt-3">
      <h3 class="subsection-title text-muted text-xs uppercase mb-1">CURRENT STATUS</h3>
      <p v-if="isConfirmed" class="text-green font-bold">
        Setup is confirmed. Ready for execution review.
      </p>
      <p v-else-if="planStatus === 'waiting'" class="text-amber">
        Waiting for confirmation before considering an entry. Trigger not yet met.
      </p>
      <p v-else class="text-muted">
        No active setup at this time.
      </p>
    </div>
  </section>
</template>
