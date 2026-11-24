<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import {
  getAISettings,
  saveAISettings,
  getAIProviderModels,
  testAIConnection,
} from '../services/api'

const loading = ref(true)
const loadError = ref('')
const saved = ref(null) // settings as last loaded/saved on the server

const selectedProvider = ref('')
const modelSelections = ref({}) // provider -> model, including unsaved edits
const autoSwitch = ref(false)
const fallbackOrder = ref([]) // [{ id, enabled }]

const modelLists = ref({}) // provider -> { loading, models, source, verified, error }
const modelFilter = ref('')

const isSaving = ref(false)
const saveStatus = ref(null) // { type: 'ok' | 'error', message }
const isTesting = ref(false)
const testStatus = ref(null) // { ok, message, latency_ms, error_kind }

const providers = computed(() => saved.value?.providers || [])

function providerLabel(id) {
  return providers.value.find((p) => p.id === id)?.label || id
}

function providerInfo(id) {
  return providers.value.find((p) => p.id === id) || null
}

const currentList = computed(() => modelLists.value[selectedProvider.value] || null)

const selectedModel = computed({
  get: () => modelSelections.value[selectedProvider.value] || '',
  set: (value) => {
    modelSelections.value = { ...modelSelections.value, [selectedProvider.value]: value }
  },
})

const selectedModelListed = computed(() =>
  Boolean(currentList.value?.models?.some((m) => m.id === selectedModel.value))
)

const filteredModels = computed(() => {
  const models = currentList.value?.models || []
  const query = modelFilter.value.trim().toLowerCase()
  if (!query) return models
  return models.filter(
    (m) =>
      m.id === selectedModel.value ||
      m.id.toLowerCase().includes(query) ||
      (m.name || '').toLowerCase().includes(query)
  )
})

const isDirty = computed(() => {
  if (!saved.value) return false
  if (saved.value.source !== 'user') return true
  return (
    selectedProvider.value !== saved.value.provider ||
    selectedModel.value !== saved.value.model ||
    autoSwitch.value !== saved.value.auto_switch ||
    JSON.stringify(enabledFallbacks()) !== JSON.stringify(saved.value.fallback_order) ||
    JSON.stringify(cleanSelections()) !== JSON.stringify(saved.value.model_by_provider)
  )
})

const canSave = computed(
  () =>
    !isSaving.value &&
    Boolean(providerInfo(selectedProvider.value)?.configured) &&
    selectedModelListed.value
)

const canTest = computed(
  () => !isTesting.value && Boolean(providerInfo(selectedProvider.value)?.configured) && Boolean(selectedModel.value)
)

function enabledFallbacks() {
  return fallbackOrder.value.filter((f) => f.enabled).map((f) => f.id)
}

function cleanSelections() {
  const result = {}
  for (const p of providers.value) {
    const model = modelSelections.value[p.id]
    if (model && p.configured) result[p.id] = model
  }
  return result
}

function fallbackModel(id) {
  return modelSelections.value[id] || providerInfo(id)?.default_model || ''
}

function applySettings(data) {
  saved.value = data
  const ids = data.providers.map((p) => p.id)

  if (ids.includes(data.provider)) {
    selectedProvider.value = data.provider
  } else {
    // Server default is a provider outside the dropdown (e.g. AI_PROVIDER=mock).
    selectedProvider.value = data.providers.find((p) => p.configured)?.id || ids[0] || ''
  }

  modelSelections.value = { ...data.model_by_provider }
  autoSwitch.value = data.auto_switch

  const order = data.fallback_order.filter((id) => ids.includes(id))
  fallbackOrder.value = [
    ...order.map((id) => ({ id, enabled: true })),
    ...ids.filter((id) => !order.includes(id)).map((id) => ({ id, enabled: false })),
  ]
}

async function loadModels(provider, refresh = false) {
  if (!provider) return

  const info = providerInfo(provider)
  if (info && !info.configured) {
    modelLists.value = {
      ...modelLists.value,
      [provider]: {
        loading: false,
        models: [],
        error_kind: 'config',
        error: 'API key is not configured on the server.',
      },
    }
    return
  }

  modelLists.value = {
    ...modelLists.value,
    [provider]: { ...(modelLists.value[provider] || { models: [] }), loading: true },
  }

  try {
    const res = await getAIProviderModels(provider, refresh)
    modelLists.value = { ...modelLists.value, [provider]: { ...res, loading: false } }

    // Preselect only the server's default model, and only if this key can use
    // it. Never pick an arbitrary (possibly paid) model on the user's behalf.
    if (!modelSelections.value[provider] && res.models?.some((m) => m.id === info?.default_model)) {
      modelSelections.value = { ...modelSelections.value, [provider]: info.default_model }
    }
  } catch (err) {
    modelLists.value = {
      ...modelLists.value,
      [provider]: { loading: false, models: [], error: err.message },
    }
  }
}

async function loadSettings() {
  loading.value = true
  loadError.value = ''
  try {
    applySettings(await getAISettings())
    await loadModels(selectedProvider.value)
  } catch (err) {
    loadError.value = err.message || 'Could not load AI settings.'
  } finally {
    loading.value = false
  }
}

function moveFallback(index, delta) {
  const target = index + delta
  if (target < 0 || target >= fallbackOrder.value.length) return
  const next = fallbackOrder.value.slice()
  ;[next[index], next[target]] = [next[target], next[index]]
  fallbackOrder.value = next
}

async function handleSave() {
  if (!canSave.value) return
  isSaving.value = true
  saveStatus.value = null

  try {
    const data = await saveAISettings({
      provider: selectedProvider.value,
      model_by_provider: cleanSelections(),
      auto_switch: autoSwitch.value,
      fallback_order: enabledFallbacks(),
    })
    applySettings(data)
    saveStatus.value = { type: 'ok', message: 'AI settings saved.' }
  } catch (err) {
    saveStatus.value = { type: 'error', message: err.message || 'Could not save AI settings.' }
  } finally {
    isSaving.value = false
  }
}

async function handleTest() {
  if (!canTest.value) return
  isTesting.value = true
  testStatus.value = null

  try {
    testStatus.value = await testAIConnection(selectedProvider.value, selectedModel.value)
  } catch (err) {
    testStatus.value = { ok: false, message: err.message || 'Connection test failed.' }
  } finally {
    isTesting.value = false
  }
}

watch(selectedProvider, (provider, previous) => {
  modelFilter.value = ''
  if (previous) testStatus.value = null
  if (provider && !modelLists.value[provider]) loadModels(provider)
})

watch(selectedModel, () => {
  testStatus.value = null
})

onMounted(loadSettings)
</script>

<template>
  <div class="card-box">
    <div class="card-header">
      <span class="card-title">AI PROVIDER</span>
      <span v-if="saved" class="badge badge-sm" :class="saved.source === 'user' ? 'badge-bullish' : 'badge-neutral'">
        {{ saved.source === 'user' ? 'SAVED' : 'SERVER DEFAULT' }}
      </span>
    </div>

    <div class="card-body ai-settings">
      <div v-if="loading" class="text-xs text-muted">Loading AI settings…</div>

      <div v-else-if="loadError" class="ai-row">
        <span class="text-xs text-red">{{ loadError }}</span>
        <button class="btn btn-secondary btn-sm" @click="loadSettings">Retry</button>
      </div>

      <template v-else-if="saved">
        <!-- Active indicators (what the AI endpoints use right now) -->
        <div class="ai-indicators">
          <div class="metric-card">
            <span class="metric-label">Active Provider</span>
            <span class="font-mono font-bold">{{ providerLabel(saved.provider) }}</span>
          </div>
          <div class="metric-card">
            <span class="metric-label">Active Model</span>
            <span class="font-mono font-bold ai-ellipsis" :title="saved.model">{{ saved.model || '—' }}</span>
          </div>
          <div class="metric-card">
            <span class="metric-label">Connection</span>
            <span
              class="font-mono font-bold"
              :class="!testStatus ? 'text-muted' : testStatus.ok ? 'text-green' : 'text-red'"
            >
              {{ isTesting ? 'Testing…' : !testStatus ? 'Not tested' : testStatus.ok ? 'Connected' : 'Failed' }}
            </span>
          </div>
        </div>

        <!-- Provider -->
        <div>
          <label class="ai-label" for="ai-provider-select">AI Provider</label>
          <select id="ai-provider-select" v-model="selectedProvider" class="ai-input">
            <option v-for="p in providers" :key="p.id" :value="p.id">
              {{ p.label }}{{ p.configured ? '' : ' — API key not configured' }}
            </option>
          </select>
        </div>

        <!-- Model -->
        <div>
          <div class="ai-row">
            <label class="ai-label" for="ai-model-select">AI Model</label>
            <button
              class="btn btn-secondary btn-sm"
              :disabled="currentList?.loading || !providerInfo(selectedProvider)?.configured"
              @click="loadModels(selectedProvider, true)"
            >
              {{ currentList?.loading ? 'Loading…' : 'Refresh Models' }}
            </button>
          </div>

          <div v-if="currentList?.error && !currentList?.models?.length" class="text-xs text-red ai-gap">
            {{ currentList.error }}
          </div>

          <template v-else>
            <input
              v-if="(currentList?.models?.length || 0) > 15"
              v-model="modelFilter"
              type="text"
              class="ai-input ai-gap"
              placeholder="Filter models…"
            />
            <select
              id="ai-model-select"
              v-model="selectedModel"
              class="ai-input ai-gap"
              :disabled="currentList?.loading || !currentList?.models?.length"
            >
              <option v-if="!currentList?.models?.length" value="">
                {{ currentList?.loading ? 'Loading models…' : 'No models available' }}
              </option>
              <option v-else value="" disabled>— Select a model —</option>
              <option v-for="m in filteredModels" :key="m.id" :value="m.id">
                {{ m.id }}{{ m.free ? ' (free)' : '' }}{{ m.context_length ? ` · ${Math.round(m.context_length / 1000)}k ctx` : '' }}
              </option>
            </select>
            <div class="text-xs text-muted ai-gap">
              <span v-if="currentList?.models?.length">
                {{ currentList.models.length }} model(s) available for this API key<span v-if="currentList.source === 'configured'"> · from configured list (unverified)</span>.
              </span>
              <span v-if="selectedModel && currentList?.models?.length && !selectedModelListed" class="text-amber">
                Saved model "{{ selectedModel }}" is not available for this key — choose another.
              </span>
            </div>
          </template>
        </div>

        <!-- Auto Switch -->
        <div class="ai-section">
          <label class="ai-row ai-check">
            <span>
              <span class="ai-label" style="margin: 0;">Auto Switch</span>
              <span class="text-xs text-muted">
                On rate limit, quota exhausted, timeout or provider server error, try the next provider below.
                When off, only the selected provider is used and its errors are shown.
              </span>
            </span>
            <input v-model="autoSwitch" type="checkbox" />
          </label>

          <div v-if="autoSwitch" class="ai-fallbacks">
            <span class="text-xs text-muted uppercase font-bold">Fallback order</span>
            <div v-for="(f, idx) in fallbackOrder" :key="f.id" class="metric-card ai-fallback-row">
              <label class="ai-check-inline">
                <input
                  v-model="f.enabled"
                  type="checkbox"
                  :disabled="f.id === selectedProvider || !providerInfo(f.id)?.configured"
                />
                <span class="font-bold">{{ idx + 1 }}. {{ providerLabel(f.id) }}</span>
              </label>
              <span class="font-mono text-xs text-muted ai-ellipsis">
                <template v-if="f.id === selectedProvider">selected provider</template>
                <template v-else-if="!providerInfo(f.id)?.configured">API key not configured</template>
                <template v-else>{{ fallbackModel(f.id) || 'no model chosen — skipped' }}</template>
              </span>
              <span class="ai-move">
                <button class="btn btn-secondary btn-sm" :disabled="idx === 0" @click="moveFallback(idx, -1)">↑</button>
                <button class="btn btn-secondary btn-sm" :disabled="idx === fallbackOrder.length - 1" @click="moveFallback(idx, 1)">↓</button>
              </span>
            </div>
            <span class="text-xs text-muted">
              A fallback provider uses the model chosen for it in the dropdown above (switch provider, pick a model,
              then switch back before saving).
            </span>
          </div>
        </div>

        <!-- Actions -->
        <div class="ai-row ai-section">
          <span class="text-xs" :class="isDirty ? 'text-amber' : 'text-muted'">
            {{ isDirty ? 'Unsaved changes' : 'Settings are up to date' }}
          </span>
          <span class="ai-actions">
            <button class="btn btn-secondary btn-sm" :disabled="!canTest" @click="handleTest">
              {{ isTesting ? 'Testing…' : 'Test Connection' }}
            </button>
            <button class="btn btn-primary btn-sm" :disabled="!canSave" @click="handleSave">
              {{ isSaving ? 'Saving…' : 'Save Settings' }}
            </button>
          </span>
        </div>

        <div v-if="testStatus" class="text-xs" :class="testStatus.ok ? 'text-green' : 'text-red'">
          {{ testStatus.ok ? '✓' : '✗' }} {{ providerLabel(testStatus.provider || selectedProvider) }}
          <span class="font-mono">{{ testStatus.model || selectedModel }}</span>: {{ testStatus.message }}
        </div>
        <div v-if="saveStatus" class="text-xs" :class="saveStatus.type === 'ok' ? 'text-green' : 'text-red'">
          {{ saveStatus.type === 'ok' ? '✓' : '✗' }} {{ saveStatus.message }}
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.ai-settings {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.ai-indicators {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.ai-label {
  font-weight: 600;
  font-size: 12px;
  color: var(--text-secondary);
  display: block;
  margin-bottom: 6px;
}

.ai-input {
  width: 100%;
  padding: 6px 10px;
  border: 1px solid var(--border-main);
  border-radius: var(--radius-sm);
  font-size: 12px;
}

.ai-gap {
  margin-top: 6px;
}

.ai-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.ai-section {
  border-top: 1px solid var(--border-main);
  padding-top: 12px;
}

.ai-check {
  cursor: pointer;
}

.ai-check > span {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.ai-check-inline {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}

.ai-fallbacks {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 12px;
}

.ai-fallback-row {
  flex-direction: row;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.ai-move,
.ai-actions {
  display: flex;
  gap: 6px;
  flex-shrink: 0;
}

.ai-ellipsis {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
