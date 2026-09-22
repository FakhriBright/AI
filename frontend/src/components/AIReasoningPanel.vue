<script setup>
import { computed } from 'vue'

const props = defineProps({
  aiData: {
    type: Object,
    default: null,
  },
  symbol: {
    type: String,
    default: 'EURUSDm',
  },
})

const provider = computed(() => props.aiData?.provider || 'gemini')
const model = computed(() => props.aiData?.model || 'gemini-3.6-flash')
const rawAnalysis = computed(() => props.aiData?.analysis || '')

const paragraphs = computed(() => {
  if (!rawAnalysis.value) return []
  return rawAnalysis.value
    .split(/\n\n+/)
    .map(p => p.trim())
    .filter(Boolean)
})

function formatParagraph(text) {
  // Simple clean formatting for headers and bold items
  return text
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/__(.*?)__/g, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/g, '<em>$1</em>')
}
</script>

<template>
  <div class="market-state-section">
    <!-- AI Header -->
    <div class="state-header flex justify-between items-center">
      <h2 class="section-title">AI ANALYSIS</h2>
      <span class="text-muted text-xs font-mono" title="Provider Info">
        {{ provider.toUpperCase() }}
      </span>
    </div>

    <!-- AI Core Intelligence Content -->
    <div class="state-content">
      <div v-if="rawAnalysis" class="ai-stream-view">
        <div
          v-for="(para, idx) in paragraphs"
          :key="idx"
          class="ai-block text-dim mb-2 text-sm leading-relaxed"
        >
          <!-- eslint-disable-next-line vue/no-v-html -->
          <div v-html="formatParagraph(para)"></div>
        </div>
      </div>

      <div v-else class="text-muted text-sm">
        Synthesizing multi-timeframe market context...
      </div>
    </div>

    <!-- Footer Disclaimer -->
    <div class="mt-4 pt-2 border-t border-subtle text-xs text-muted">
      <span>
        Decision support only. Human trader bears full responsibility for trade verification and execution.
      </span>
    </div>
  </div>
</template>
