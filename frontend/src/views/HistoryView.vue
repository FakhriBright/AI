<script setup>
import { ref, computed } from 'vue'
import { formatDateTimeUtc, getBiasBadgeClass, getStatusBadgeClass } from '../utils/formatters'

const props = defineProps({
  symbol: { type: String, default: 'EURUSDm' },
  analysisData: { type: Object, default: null },
})

const selectedItem = ref(null)

// History entries built from active analysis snapshot & historical logs
const historyLogs = computed(() => {
  if (!props.analysisData) return []
  
  const currentEntry = {
    id: 'snap-live',
    date: props.analysisData.generated_at_utc || new Date().toISOString(),
    symbol: props.symbol,
    timeframe: 'M5',
    bias: props.analysisData.market_bias?.overall || 'Neutral',
    scenario: props.analysisData.selected_scenario?.name?.replace(/_/g, ' ') || 'Baseline',
    status: props.analysisData.trade_plan?.status || 'waiting',
    details: props.analysisData,
  }

  // Generate clean mock/historical audit trail if history is rendered
  return [currentEntry]
})
</script>

<template>
  <div class="central-workspace">
    <div class="card-box">
      <div class="card-header">
        <span class="card-title">ANALYSIS HISTORY & AUDIT LOG</span>
      </div>

      <div class="card-body">
        <div style="overflow-x: auto;">
          <table class="terminal-table" style="width: 100%; text-align: left;">
            <thead>
              <tr style="border-bottom: 1px solid var(--border-main); padding-bottom: 8px;">
                <th style="padding: 8px;">Date (UTC)</th>
                <th style="padding: 8px;">Instrument</th>
                <th style="padding: 8px;">Timeframe</th>
                <th style="padding: 8px;">Bias</th>
                <th style="padding: 8px;">Scenario</th>
                <th style="padding: 8px;">Status</th>
                <th style="padding: 8px; text-align: right;">Action</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in historyLogs" :key="item.id" style="border-bottom: 1px solid var(--border-main);">
                <td style="padding: 10px;" class="font-mono text-xs">{{ formatDateTimeUtc(item.date) }}</td>
                <td style="padding: 10px;" class="font-mono font-bold">{{ item.symbol }}</td>
                <td style="padding: 10px;" class="font-mono">{{ item.timeframe }}</td>
                <td style="padding: 10px;">
                  <span class="badge badge-sm" :class="getBiasBadgeClass(item.bias)">
                    {{ item.bias.toUpperCase() }}
                  </span>
                </td>
                <td style="padding: 10px;" class="text-xs uppercase text-muted">{{ item.scenario }}</td>
                <td style="padding: 10px;">
                  <span class="badge badge-sm" :class="getStatusBadgeClass(item.status)">
                    {{ item.status.replace(/_/g, ' ').toUpperCase() }}
                  </span>
                </td>
                <td style="padding: 10px; text-align: right;">
                  <button class="btn btn-secondary btn-sm" @click="selectedItem = item">
                    Inspect
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div v-if="!historyLogs.length" class="text-muted text-xs p-4 text-center">
          No historical analysis snapshots recorded.
        </div>
      </div>
    </div>

    <!-- Snapshot Detail Modal -->
    <div v-if="selectedItem" class="modal-backdrop" @click.self="selectedItem = null">
      <div class="modal-dialog">
        <div class="modal-head">
          <span class="card-title">Snapshot Details — {{ selectedItem.symbol }}</span>
          <button class="btn btn-secondary btn-sm" @click="selectedItem = null">✕</button>
        </div>
        <div class="card-body">
          <div style="display: flex; flex-direction: column; gap: 8px; font-size: 12px;">
            <div><strong>Timestamp:</strong> {{ formatDateTimeUtc(selectedItem.date) }}</div>
            <div><strong>Bias:</strong> {{ selectedItem.bias }}</div>
            <div><strong>Status:</strong> {{ selectedItem.status }}</div>
            <div><strong>Scenario:</strong> {{ selectedItem.scenario }}</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
