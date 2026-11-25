<script setup>
import { ref, computed, watch, nextTick } from 'vue'
import { sendAnalysisChat } from '../services/api'
import { getBiasBadgeClass } from '../utils/formatters'
import { STALE_AFTER_MS, applyChartCommand, chartStore } from '../utils/chartOverlays'

const props = defineProps({
  symbol: {
    type: String,
    default: 'EURUSDm',
  },
  analysisData: {
    type: Object,
    default: null,
  },
})

const messages = ref([
  {
    role: 'assistant',
    content: `Hello! I am your AI Analyst Assistant for **${props.symbol}**. Ask me any questions regarding the current market setup or reasoning.`,
    time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
  },
])

const inputMessage = ref('')
const isLoading = ref(false)
const chatMessagesRef = ref(null)

// Each chip sends exactly one chat request when clicked (never automatically).
const quickActions = [
  'Explain current market bias.',
  'Explain current market structure.',
  'Why is the market mixed?',
  'Explain the current FVG.',
  'What invalidates this setup?',
  'Compare M5 and H1.',
  'Explain the current Trade Plan.',
]

const activeTf = computed(() => chartStore.activeTf || 'M5')
const analysisTime = computed(() => {
  const ts = Date.parse(props.analysisData?.generated_at_utc || '')
  return Number.isFinite(ts) ? new Date(ts).toISOString().slice(11, 16) + ' UTC' : '—'
})
const analysisStale = computed(() => {
  const ts = Date.parse(props.analysisData?.generated_at_utc || '')
  return Number.isFinite(ts) && Date.now() - ts > STALE_AFTER_MS
})

const marketBias = computed(() => props.analysisData?.market_bias?.overall || 'Neutral')
const marketStructure = computed(() => {
  const mtf = props.analysisData?.multi_timeframe?.timeframes?.M5
  return mtf?.structure || mtf?.trend || 'Lower Highs'
})

watch(
  () => props.symbol,
  (newSym) => {
    messages.value.push({
      role: 'assistant',
      content: `Active context updated to **${newSym}**. Ask about the latest technical setup.`,
      time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    })
    scrollToBottom()
  }
)

function scrollToBottom() {
  nextTick(() => {
    if (chatMessagesRef.value) {
      chatMessagesRef.value.scrollTop = chatMessagesRef.value.scrollHeight
    }
  })
}

async function handleSendMessage(textToSend) {
  const query = (textToSend || inputMessage.value).trim()
  if (!query || isLoading.value) return

  inputMessage.value = ''

  messages.value.push({
    role: 'user',
    content: query,
    time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
  })
  scrollToBottom()

  isLoading.value = true

  try {
    const historyPayload = messages.value.map(m => ({
      role: m.role,
      content: m.content,
    }))

    // The chart timeframe is part of the question's context (one request only).
    const res = await sendAnalysisChat(
      props.symbol,
      `${query}

(Timeframe chart aktif: ${activeTf.value})`,
      historyPayload
    )
    const snapshot = res.chart?.analysis_id?.split('@')[1]

    messages.value.push({
      role: 'assistant',
      content: res.reply || 'No response generated.',
      chartNote: chartNote(applyChartCommand(res.chart, props.symbol)),
      snapshot: snapshot ? `${props.symbol} · ${activeTf.value} · analysis ${snapshot.slice(11, 16)} UTC` : '',
      time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    })
  } catch (err) {
    const detail = String(err?.message || '').trim()

    messages.value.push({
      role: 'assistant',
      content: detail
        ? `AI Analyst unavailable: ${detail}`
        : 'AI Analyst unavailable. Check the backend service.',
      time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    })
  } finally {
    isLoading.value = false
    scrollToBottom()
  }
}

function chartNote(summary) {
  if (!summary) return ''
  const parts = []
  if (summary.cleared) parts.push('AI drawings cleared')
  if (summary.created.length) parts.push(`drawn: ${summary.created.join(', ')}`)
  if (summary.highlighted) parts.push(`${summary.highlighted} object(s) highlighted`)
  parts.push(...(summary.notes || []))
  return parts.length ? `Chart · ${parts.join(' · ')}` : ''
}

function renderMarkdown(text) {
  if (!text) return ''
  // Escape HTML first (AI output is rendered with v-html), then format.
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, '$1<em>$2</em>')
    .replace(/`(.*?)`/g, '<code>$1</code>')
    .replace(/\n\n/g, '<br><br>')
    .replace(/\n- /g, '<br>&bull; ')
    .replace(/\n/g, '<br>')
}
</script>

<template>
  <div class="right-panel">
    <!-- Compact Market Context Box -->
    <div class="card-box">
      <div class="card-header">
        <span class="card-title">CURRENT CONTEXT</span>
        <span class="font-mono text-xs font-bold text-accent">{{ symbol }}</span>
      </div>
      <div class="card-body" style="padding: 12px 16px;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
          <span class="text-xs text-muted">Market Bias:</span>
          <span class="badge badge-sm" :class="getBiasBadgeClass(marketBias)">
            {{ String(marketBias).toUpperCase() }}
          </span>
        </div>
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <span class="text-xs text-muted">Structure (M5):</span>
          <span class="font-mono text-xs text-main font-bold">{{ marketStructure.toUpperCase() }}</span>
        </div>
      </div>
    </div>

    <!-- AI Analyst Box -->
    <div class="card-box ai-panel-box">
      <div class="card-header">
        <span class="card-title">AI ANALYST</span>
        <span class="badge badge-sm" :class="isLoading ? 'badge-warning' : 'badge-bullish'" title="AI is only called when you send a message">
          {{ isLoading ? 'THINKING' : 'READY · ON DEMAND' }}
        </span>
      </div>
      <div class="ai-context-line text-xs">
        <span class="font-mono font-bold">{{ symbol }}</span>
        <span>· {{ activeTf }}</span>
        <span>· analysis {{ analysisTime }}</span>
        <span v-if="analysisStale" class="text-amber">· STALE</span>
      </div>

      <div ref="chatMessagesRef" class="chat-flow">
        <div
          v-for="(msg, idx) in messages"
          :key="idx"
          class="chat-bubble"
          :class="msg.role"
        >
          <!-- eslint-disable-next-line vue/no-v-html -->
          <div style="overflow-wrap: anywhere" v-html="renderMarkdown(msg.content)"></div>
          <div v-if="msg.chartNote" class="text-xs text-accent" style="margin-top: 6px;">{{ msg.chartNote }}</div>
          <div v-if="msg.snapshot" class="text-xs text-muted" style="margin-top: 2px;">Based on {{ msg.snapshot }}</div>
        </div>

        <div v-if="isLoading" class="chat-bubble assistant text-muted text-xs">
          Analyzing market setup...
        </div>
      </div>

      <div class="quick-actions-bar">
        <button
          v-for="(action, idx) in quickActions"
          :key="idx"
          type="button"
          class="action-chip"
          :disabled="isLoading"
          :title="`Ask the AI Analyst: ${action}`"
          @click="handleSendMessage(action)"
        >
          {{ action }}
        </button>
      </div>

      <form class="chat-input-row" @submit.prevent="handleSendMessage()">
        <input
          v-model="inputMessage"
          type="text"
          placeholder="Ask about this analysis..."
          :disabled="isLoading"
        />
        <button type="submit" class="btn btn-primary btn-sm" :disabled="!inputMessage.trim() || isLoading">
          Send
        </button>
      </form>
    </div>
  </div>
</template>

<style scoped>
.ai-context-line {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  padding: 6px 16px;
  border-bottom: 1px solid var(--border-main);
  color: var(--text-muted);
}

.quick-actions-bar {
  flex-wrap: wrap;
}

.action-chip:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
