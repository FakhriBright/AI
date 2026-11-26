<script setup>
import { computed } from 'vue'
import {
  engineText,
  formatPrice,
  formatPips,
  formatNumber,
  getBiasBadgeClass,
} from '../utils/formatters'

const props = defineProps({
  scenariosData: {
    type: Object,
    default: () => ({}),
  },
  selectedScenario: {
    type: Object,
    default: null,
  },
  confirmation: {
    type: Object,
    default: null,
  },
  symbol: {
    type: String,
    default: 'XAUUSDm',
  },
})

// Engine candidates (analysis/scenario.py): scalp + intraday lists. Read-only.
const scenariosList = computed(() => {
  const data = props.scenariosData || {}
  const tag = (list, group) => (list || []).map((s) => ({ ...s, group }))
  return [...tag(data.scalp_scenarios, 'scalp'), ...tag(data.intraday_scenarios, 'intraday')]
})

function isScenarioSelected(scenario) {
  return props.selectedScenario?.name === scenario.name
}

function getScenarioIcon(direction) {
  if (direction === 'bullish') {
    return 'M7 14l5-5 5 5z'
  }
  if (direction === 'bearish') {
    return 'M7 10l5 5 5-5z'
  }
  return 'M5 12h14'
}
</script>

<template>
  <div class="panel-container">
    <div class="panel-header">
      <div class="panel-title-wrap">
        <svg class="panel-icon" viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
          <path d="M12 2l4.5 9h-9L12 2zm0 3.84L9.93 9h4.14L12 5.84zM17.5 13l4.5 9h-9l4.5-9zm0 3.84L15.43 20h4.14L17.5 16.84zM6.5 13l4.5 9h-9l4.5-9zm0 3.84L4.43 20h4.14L6.5 16.84z" />
        </svg>
        <h2 class="panel-title">SCENARIO EVALUATION ENGINE</h2>
      </div>
      <span class="panel-subtitle">Deterministic conditional scenarios · {{ scenariosList.length }} candidates</span>
    </div>

    <div v-if="!scenariosList.length" class="text-muted text-sm">
      No scenario candidates in this analysis.
    </div>

    <!-- Scenarios Grid -->
    <div class="scenarios-cards-grid">
      <div
        v-for="scenario in scenariosList"
        :key="scenario.name"
        class="scenario-card"
        :class="[
          'scenario-' + (scenario.direction || 'neutral'),
          { 'scenario-active-card': isScenarioSelected(scenario) }
        ]"
      >
        <!-- Card Top Bar -->
        <div class="scenario-card-header">
          <div class="scenario-title-group">
            <span class="scenario-dir-icon" :class="'icon-' + scenario.direction">
              <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor">
                <path :d="getScenarioIcon(scenario.direction)" />
              </svg>
            </span>
            <div>
              <h3 class="scenario-name-text">
                {{ scenario.name.replace(/_/g, ' ').toUpperCase() }}
              </h3>
              <span class="scenario-status-pill uppercase">
                {{ scenario.group }} · Status: {{ scenario.status }}
              </span>
            </div>
          </div>

          <div class="scenario-header-badges">
            <span v-if="isScenarioSelected(scenario)" class="badge badge-cyan font-bold">
              ACTIVE SELECTION
            </span>
            <span class="badge" :class="getBiasBadgeClass(scenario.direction)">
              {{ scenario.direction.toUpperCase() }}
            </span>
          </div>
        </div>

        <!-- Conditional Path Details -->
        <div class="scenario-conditions-box">
          <!-- Trigger Section -->
          <div class="condition-row">
            <div class="cond-label-wrap">
              <span class="cond-dot dot-cyan"></span>
              <span class="cond-name">TRIGGER LOGIC:</span>
            </div>
            <div class="cond-body">
              <span class="cond-rule">{{ engineText(scenario.trigger, symbol) }}</span>
              <div v-if="scenario.trigger_reference" class="cond-ref-wrap">
                <span class="cond-ref-label">Trigger Level:</span>
                <span class="font-mono font-bold">{{ formatPrice(scenario.trigger_reference, symbol) }}</span>
                <span v-if="scenario.trigger_distance !== null" class="text-xs text-muted">
                  (Dist: {{ formatPips(scenario.trigger_distance, symbol) }} / {{ formatNumber(scenario.trigger_distance_atr, 1) }}x ATR)
                </span>
              </div>
            </div>
          </div>

          <!-- Invalidation Section -->
          <div class="condition-row">
            <div class="cond-label-wrap">
              <span class="cond-dot dot-amber"></span>
              <span class="cond-name">INVALIDATION:</span>
            </div>
            <div class="cond-body">
              <span class="cond-rule">{{ engineText(scenario.invalidation, symbol) }}</span>
              <div v-if="scenario.invalidation_reference" class="cond-ref-wrap">
                <span class="cond-ref-label">Inval Level:</span>
                <span class="font-mono font-bold">{{ formatPrice(scenario.invalidation_reference, symbol) }}</span>
                <span v-if="scenario.invalidation_distance !== null" class="text-xs text-muted">
                  (Dist: {{ formatPips(scenario.invalidation_distance, symbol) }} / {{ formatNumber(scenario.invalidation_distance_atr, 1) }}x ATR)
                </span>
              </div>
            </div>
          </div>

          <!-- Confirmation Requirement & State -->
          <div class="condition-row">
            <div class="cond-label-wrap">
              <span class="cond-dot" :class="scenario.trigger_confirmed ? 'dot-green' : 'dot-purple'"></span>
              <span class="cond-name">CONFIRMATION:</span>
            </div>
            <div class="cond-body">
              <div class="confirm-status-row">
                <span
                  class="badge badge-sm"
                  :class="scenario.trigger_confirmed ? 'badge-bullish' : 'badge-neutral'"
                >
                  {{ scenario.trigger_confirmed ? 'CONFIRMED' : 'AWAITING TRIGGER CANDLE' }}
                </span>
                <span v-if="scenario.near_trigger" class="badge badge-sm badge-cyan">
                  NEAR TRIGGER ZONE (&le;0.25 ATR)
                </span>
              </div>
            </div>
          </div>
        </div>

        <!-- Rationale List -->
        <div v-if="scenario.rationale?.length" class="scenario-rationale-box">
          <span class="rationale-heading">STRUCTURAL RATIONALE:</span>
          <div class="rationale-tags">
            <span
              v-for="(item, rIdx) in scenario.rationale"
              :key="rIdx"
              class="rationale-pill"
            >
              {{ item.replace(/_/g, ' ') }}
            </span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.panel-header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.panel-title-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
}

.panel-title {
  margin: 0;
  font-size: 13px;
  letter-spacing: 0.06em;
}

.panel-subtitle {
  font-size: 11px;
  color: var(--text-muted);
}

.scenarios-cards-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 12px;
}

.scenario-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px;
  border: 1px solid var(--border-main);
  border-radius: var(--radius-sm);
}

.scenario-active-card {
  border-color: var(--accent-primary);
}

.scenario-card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 8px;
}

.scenario-title-group {
  display: flex;
  gap: 8px;
}

.scenario-name-text {
  margin: 0;
  font-size: 12px;
}

.scenario-status-pill {
  font-size: 10px;
  color: var(--text-muted);
}

.scenario-header-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  justify-content: flex-end;
}

.scenario-conditions-box {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.condition-row {
  display: grid;
  grid-template-columns: 110px 1fr;
  gap: 8px;
  font-size: 12px;
}

.cond-label-wrap {
  display: flex;
  align-items: center;
  gap: 6px;
}

.cond-name,
.rationale-heading {
  font-size: 10px;
  letter-spacing: 0.05em;
  color: var(--text-muted);
}

.cond-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--text-muted);
}

.dot-cyan { background: #5FB7D9; }
.dot-amber { background: #E0A84A; }
.dot-green { background: var(--accent-primary); }

.cond-ref-wrap {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: baseline;
  margin-top: 2px;
}

.cond-ref-label {
  color: var(--text-muted);
}

.confirm-status-row,
.rationale-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.rationale-pill {
  padding: 1px 6px;
  border: 1px solid var(--border-main);
  border-radius: var(--radius-sm);
  font-size: 11px;
  color: var(--text-secondary);
}
</style>
