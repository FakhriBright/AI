<script setup>
import { computed } from 'vue'
import { formatPrice, getBiasBadgeClass } from '../utils/formatters'
import { chartStore } from '../utils/chartOverlays'

const props = defineProps({
  tradePlan: {
    type: Object,
    default: null,
  },
  stopPlan: {
    type: Object,
    default: null,
  },
  symbol: {
    type: String,
    default: 'EURUSDm',
  },
  marketBias: {
    type: Object,
    default: null,
  },
  selectedScenario: {
    type: Object,
    default: null,
  },
  confirmation: {
    type: Object,
    default: null,
  },
})

const plan = computed(() => props.tradePlan || {})

// Presentation of the engine's own statuses (analysis/trade_plan.py). No new states.
const STATUS_VIEW = {
  waiting: { label: 'WAITING', cls: 'badge-warning', note: 'No trigger confirmed yet.' },
  confirmed_needs_stop: { label: 'SETUP FORMING', cls: 'badge-info', note: 'Trigger confirmed, but no valid stop yet.' },
  confirmed_needs_risk: { label: 'SETUP FORMING', cls: 'badge-info', note: 'Trigger confirmed, but risk settings are missing.' },
  confirmed_needs_target: { label: 'SETUP FORMING', cls: 'badge-info', note: 'Trigger confirmed, but no valid target / RR.' },
  ready_for_manual_review: { label: 'CONFIRMED', cls: 'badge-bullish', note: 'Ready for manual review. Execution stays manual.' },
}

const statusView = computed(() => {
  const s = plan.value.status
  if (!s) return { label: 'WAITING', cls: 'badge-warning', note: 'No analysis loaded yet.' }
  return STATUS_VIEW[s] || { label: String(s).replace(/_/g, ' ').toUpperCase(), cls: 'badge-neutral', note: '' }
})

const bias = computed(() => props.marketBias?.overall || plan.value.market_bias || 'neutral')
const direction = computed(() => plan.value.direction || null)

function price(value) {
  return value !== null && value !== undefined ? formatPrice(value, props.symbol) : null
}

const values = computed(() => [
  { label: 'Entry', value: price(plan.value.entry_price), cls: 'text-accent' },
  { label: 'Stop Loss', value: price(plan.value.stop_price), cls: 'text-red' },
  { label: 'Take Profit', value: price(plan.value.target_price ?? plan.value.take_profit), cls: 'text-green' },
  {
    label: 'Risk / Reward',
    value: plan.value.rr_ratio !== null && plan.value.rr_ratio !== undefined ? `1:${plan.value.rr_ratio}` : null,
    cls: 'text-green',
  },
])
const missingValues = computed(() => values.value.some((v) => !v.value))

const scenario = computed(() => props.selectedScenario || {})
const humanize = (s) => String(s || '').replace(/_/g, ' ')

const trigger = computed(() => {
  const ref = price(scenario.value.trigger_reference)
  return {
    text: scenario.value.trigger ? humanize(scenario.value.trigger) : null,
    ref,
    state: scenario.value.trigger_confirmed ? 'confirmed' : humanize(scenario.value.breakout_status || 'awaiting'),
  }
})

const invalidation = computed(() => ({
  text: scenario.value.invalidation ? humanize(scenario.value.invalidation) : null,
  ref: price(scenario.value.invalidation_reference),
}))

const confirmationView = computed(() => {
  const c = props.confirmation
  if (!c) return null
  return {
    confirmed: Boolean(c.confirmed),
    type: humanize(c.confirmation_type),
    reasons: c.reasons || [],
  }
})

// Entry-gate blockers computed by the engine (ai/desk.py build_entry_gate),
// delivered with the chart overlays; no extra request.
const blockers = computed(() => {
  const waiting = Object.values(chartStore.engine).find((o) => o.id.endsWith(':MTF:plan:waiting'))
  return waiting?.meta?.blockers || []
})

const reasoning = computed(() => {
  const items = [...(plan.value.reasons || []), ...(plan.value.warnings || []), ...(plan.value.conflicts || [])]
  return [...new Set(items.map((x) => String(x)))]
})
</script>

<template>
  <div class="card-box trade-plan-module">
    <div class="card-header">
      <span class="card-title">TRADE PLAN</span>
      <span class="tp-head-right">
        <span v-if="plan.scenario_name" class="text-xs text-muted">{{ humanize(plan.scenario_name) }}</span>
        <span class="badge" :class="statusView.cls">{{ statusView.label }}</span>
      </span>
    </div>

    <div class="card-body">
      <div class="trade-plan-grid">
        <div class="metric-card">
          <span class="metric-label">Market Bias</span>
          <div class="tp-bias">
            <span class="badge" :class="getBiasBadgeClass(bias)">{{ String(bias).toUpperCase() }}</span>
            <span v-if="direction" class="text-xs text-muted">plan: {{ String(direction).toUpperCase() }}</span>
          </div>
        </div>
        <div v-for="v in values" :key="v.label" class="metric-card">
          <span class="metric-label">{{ v.label }}</span>
          <span class="metric-val" :class="v.value ? v.cls : 'text-muted'">{{ v.value || '—' }}</span>
        </div>
      </div>

      <div class="tp-status-note text-xs">
        <span :class="statusView.cls === 'badge-bullish' ? 'text-green' : statusView.cls === 'badge-warning' ? 'text-amber' : 'text-muted'">
          {{ statusView.note }}
        </span>
        <span v-if="missingValues" class="text-muted"> Values shown as “—” are not provided by the engine; no qualified setup is available yet.</span>
      </div>

      <div class="tp-conditions">
        <div class="tp-cond">
          <span class="rule-label">Trigger</span>
          <span class="font-mono text-xs">
            {{ trigger.text || 'Not provided by engine' }}
            <template v-if="trigger.ref"> · {{ trigger.ref }}</template>
          </span>
          <span class="badge badge-sm" :class="trigger.state === 'confirmed' ? 'badge-bullish' : 'badge-warning'">{{ trigger.state.toUpperCase() }}</span>
        </div>
        <div v-if="confirmationView" class="tp-cond">
          <span class="rule-label">Confirmation</span>
          <span class="font-mono text-xs">{{ confirmationView.type || '—' }}</span>
          <span class="badge badge-sm" :class="confirmationView.confirmed ? 'badge-bullish' : 'badge-neutral'">
            {{ confirmationView.confirmed ? 'CONFIRMED' : 'NOT CONFIRMED' }}
          </span>
        </div>
        <div class="tp-cond">
          <span class="rule-label">Invalidation</span>
          <span class="font-mono text-xs">
            {{ invalidation.text || '—' }}
            <template v-if="invalidation.ref"> · {{ invalidation.ref }}</template>
            <template v-else> · engine provides no invalidation level for this scenario</template>
          </span>
        </div>
        <div v-if="blockers.length" class="tp-cond tp-blockers">
          <span class="rule-label">Why waiting</span>
          <ul>
            <li v-for="b in blockers" :key="b" class="text-xs">{{ b }}</li>
          </ul>
        </div>
      </div>

      <details v-if="reasoning.length || confirmationView?.reasons.length" class="tp-reasoning">
        <summary class="text-xs">System reasoning ({{ reasoning.length + (confirmationView?.reasons.length || 0) }})</summary>
        <ul>
          <li v-for="r in confirmationView?.reasons || []" :key="`c-${r}`" class="text-xs">{{ r }}</li>
          <li v-for="r in reasoning" :key="r" class="text-xs">{{ r }}</li>
        </ul>
      </details>
    </div>
  </div>
</template>

<style scoped>
.tp-head-right {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.tp-bias {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.tp-status-note {
  margin-top: 10px;
}

.tp-conditions {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid var(--border-main);
}

.tp-cond {
  display: grid;
  grid-template-columns: 110px 1fr auto;
  align-items: center;
  gap: 8px;
}

.tp-blockers {
  align-items: start;
}

.tp-blockers ul,
.tp-reasoning ul {
  margin: 0;
  padding-left: 16px;
  color: var(--text-secondary);
}

.tp-reasoning {
  margin-top: 10px;
}

.tp-reasoning summary {
  cursor: pointer;
  color: var(--text-muted);
}

.badge-info {
  background-color: var(--accent-light);
  color: var(--accent-primary);
  border: 1px solid var(--accent-primary);
}
</style>
