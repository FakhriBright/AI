<script setup>
import { ref, computed, watch, nextTick } from 'vue'
import { sendAnalysisChat } from '../services/api'

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
    content: `Halo Trader! Saya adalah **AI Trading Analysis Assistant** yang terhubung langsung dengan engine analisa live untuk **${props.symbol}**.\n\nSaya dapat menjawab pertanyaan spesifik berdasarkan data teknikal saat ini (Market Bias, Multi-Timeframe, Key Levels, Skenario, Konfirmasi, Trade Plan & Risk).\n\n*Pilih salah satu pertanyaan di bawah atau ketik pertanyaan Anda.*`,
    time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
  },
])

const inputMessage = ref('')
const isLoading = ref(false)
const chatMessagesRef = ref(null)

const provider = computed(() => {
  return props.analysisData?.ai?.provider || 'gemini'
})

const model = computed(() => {
  return props.analysisData?.ai?.model || 'gemini-3.6-flash'
})

const quickPrompts = [
  'Why no entry?',
  'What confirms the setup?',
  'What invalidates it?',
  'Explain the higher timeframe.',
]

watch(
  () => props.symbol,
  (newSym) => {
    messages.value.push({
      role: 'assistant',
      content: `Instrumen aktif dialihkan ke **${newSym}**. Analisis dan data teknikal telah diperbarui sesuai snapshot live MT5 untuk **${newSym}**. Silakan tanyakan kondisi setup saat ini.`,
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
      historyPayload,
      props.analysisData
    )

    messages.value.push({
      role: 'assistant',
      content: res.reply,
      time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      provider: res.provider || provider.value,
      model: res.model || model.value,
    })
  } catch (err) {
    messages.value.push({
      role: 'assistant',
      content: 'Live AI analysis is unavailable. Check the backend and AI service connection.',
      time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      isError: true,
    })
  } finally {
    isLoading.value = false
    scrollToBottom()
  }
}

function renderMarkdown(text) {
  if (!text) return ''
  return text
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/`(.*?)`/g, '<code>$1</code>')
    .replace(/\*(.*?)\*/g, '<em>$1</em>')
    .replace(/\n\n/g, '<br><br>')
    .replace(/\n- /g, '<br>&bull; ')
    .replace(/\n1\. /g, '<br>1. ')
    .replace(/\n2\. /g, '<br>2. ')
    .replace(/\n3\. /g, '<br>3. ')
    .replace(/\n4\. /g, '<br>4. ')
}
</script>

<template>
  <div class="chat-assistant-container">
    <!-- Header -->
    <div class="chat-header">
      <div class="chat-title-group">
        <div>
          <h2 class="chat-main-title">AI ASSISTANT</h2>
          <span class="chat-sub-title">Based on current market analysis</span>
        </div>
      </div>

      <div class="chat-header-pills">
        <span class="badge font-mono font-bold">{{ symbol }}</span>
      </div>
    </div>

    <!-- Offline State -->
    <div v-if="!analysisData" class="chat-offline-state p-4 text-center">
      <div class="alert-warning mb-2">
        <span class="font-bold text-amber">Analysis Unavailable</span>
      </div>
      <p class="text-muted">Live market analysis is unavailable. Refresh the market data before asking for analysis.</p>
    </div>

    <template v-else>
      <!-- Quick Prompt Chips -->
    <div class="quick-prompts-bar">
      <span class="prompts-label">QUICK QUERIES:</span>
      <div class="prompts-scroll">
        <button
          v-for="(prompt, idx) in quickPrompts"
          :key="idx"
          class="prompt-chip-btn"
          :disabled="isLoading"
          @click="handleSendMessage(prompt)"
        >
          {{ prompt }}
        </button>
      </div>
    </div>

    <!-- Messages Flow -->
    <div ref="chatMessagesRef" class="chat-messages-wrap">
      <div
        v-for="(msg, idx) in messages"
        :key="idx"
        class="chat-bubble-row"
        :class="msg.role === 'user' ? 'bubble-user' : 'bubble-assistant'"
      >
        <div class="bubble-avatar">
          {{ msg.role === 'user' ? 'ME' : 'AI' }}
        </div>

        <div class="bubble-content-box">
          <div class="bubble-meta">
            <span class="bubble-author">
              {{ msg.role === 'user' ? 'Trader' : `AI Analyst (${msg.model || model})` }}
            </span>
            <span class="bubble-time font-mono">{{ msg.time }}</span>
          </div>

          <!-- eslint-disable-next-line vue/no-v-html -->
          <div class="bubble-text" v-html="renderMarkdown(msg.content)"></div>
        </div>
      </div>

      <!-- Typing indicator -->
      <div v-if="isLoading" class="chat-bubble-row bubble-assistant">
        <div class="bubble-avatar">AI</div>
        <div class="bubble-content-box typing-box">
          <span class="typing-dot"></span>
          <span class="typing-dot"></span>
          <span class="typing-dot"></span>
          <span class="typing-text">Menelaah data teknikal & skenario {{ symbol }}...</span>
        </div>
      </div>
    </div>

    <!-- Input Form -->
    <form class="chat-input-form" @submit.prevent="handleSendMessage()">
      <div class="input-container">
        <input
          v-model="inputMessage"
          type="text"
          class="chat-input-field"
          :placeholder="`Tanyakan analisis ${symbol} (misal: Kenapa belum ada entry?)...`"
          :disabled="isLoading"
        />
        <button type="submit" class="chat-send-btn" :disabled="!inputMessage.trim() || isLoading">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
            <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z" />
          </svg>
          <span>Kirim</span>
        </button>
      </div>
    </form>

    <!-- Grounding & Safety Footer -->
    <div class="chat-footer-policy">
      <span>
        Decision Support Only &bull; No Auto Execution
      </span>
    </div>
    </template>
  </div>
</template>
