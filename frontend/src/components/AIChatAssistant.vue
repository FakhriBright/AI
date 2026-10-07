<script setup>
import { ref, computed, watch, nextTick } from 'vue'
import { sendAnalysisChat } from '../services/api'
import { getBiasBadgeClass } from '../utils/formatters'

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

const quickActions = [
  'Explain setup',
  'Why bearish?',
  'What invalidates this?',
  'Summarize analysis',
]

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

    const res = await sendAnalysisChat(
      props.symbol,
      query,
      historyPayload
    )

    messages.value.push({
      role: 'assistant',
      content: res.reply || 'No response generated.',
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
        </div>

        <div v-if="isLoading" class="chat-bubble assistant text-muted text-xs">
          Analyzing market setup...
        </div>
      </div>

      <div class="quick-actions-bar">
        <span
          v-for="(action, idx) in quickActions"
          :key="idx"
          class="action-chip"
          @click="handleSendMessage(action)"
        >
          {{ action }}
        </span>
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
