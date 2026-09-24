<script setup>
import { ref, onMounted } from 'vue'
import {
  getApiBaseUrl,
  setApiBaseUrl,
  getBackendHealth,
  getMarketHealth,
  getMarketSymbols,
  getStoredUserEmail,
  getStoredToken,
} from '../services/api'

const emit = defineEmits(['logout'])

const apiUrlInput = ref(getApiBaseUrl())
const savedSuccess = ref(false)
const testResults = ref(null)
const isTesting = ref(false)

const userEmail = ref(getStoredUserEmail())
const token = ref(getStoredToken())

function handleSaveUrl() {
  setApiBaseUrl(apiUrlInput.value)
  savedSuccess.value = true
  setTimeout(() => {
    savedSuccess.value = false
  }, 3000)
}

function handleResetUrl() {
  const protocol = window.location.protocol || 'http:'
  const hostname = window.location.hostname || 'localhost'
  const defaultUrl = `${protocol}//${hostname}:8000`
  apiUrlInput.value = defaultUrl
  setApiBaseUrl(defaultUrl)
  savedSuccess.value = true
  setTimeout(() => {
    savedSuccess.value = false
  }, 3000)
}

async function runDiagnostics() {
  isTesting.value = true
  testResults.value = {
    backend: { status: 'checking', message: '' },
    bridge: { status: 'checking', message: '' },
    symbols: { status: 'checking', count: 0 },
  }

  try {
    const bHealth = await getBackendHealth()
    testResults.value.backend = {
      status: bHealth?.status === 'ok' ? 'ok' : 'warning',
      message: bHealth?.status === 'ok' ? 'Backend Service Connected' : 'Unavailable',
    }
  } catch (err) {
    testResults.value.backend = {
      status: 'error',
      message: 'Backend Connection Failed',
    }
  }

  try {
    const mHealth = await getMarketHealth()
    const ok = mHealth?.bridge_status === 'ok' && mHealth?.data_source_connected
    testResults.value.bridge = {
      status: ok ? 'ok' : 'warning',
      message: ok ? 'MT5 Data Feed Live' : 'MT5 Bridge Disconnected',
    }
  } catch (err) {
    testResults.value.bridge = {
      status: 'error',
      message: 'MT5 Bridge Unreachable',
    }
  }

  try {
    const syms = await getMarketSymbols()
    testResults.value.symbols = {
      status: 'ok',
      count: syms?.symbols?.length || 0,
      list: (syms?.symbols || []).slice(0, 8).join(', '),
    }
  } catch (err) {
    testResults.value.symbols = {
      status: 'error',
      message: err.message,
    }
  }

  isTesting.value = false
}

onMounted(() => {
  runDiagnostics()
})
</script>

<template>
  <div class="central-workspace">
    <!-- SECTION 1: NORMAL SETTINGS -->
    <div class="card-box">
      <div class="card-header">
        <span class="card-title">APPLICATION SETTINGS</span>
      </div>

      <div class="card-body" style="display: flex; flex-direction: column; gap: 16px;">
        <!-- Connection Endpoint -->
        <div>
          <label style="font-weight: 600; font-size: 12px; color: var(--text-secondary); display: block; margin-bottom: 6px;">
            FastAPI Backend Endpoint URL
          </label>
          <div style="display: flex; gap: 8px;">
            <input
              v-model="apiUrlInput"
              type="text"
              style="flex: 1; padding: 6px 10px; border: 1px solid var(--border-main); border-radius: var(--radius-sm); font-size: 12px;"
              placeholder="http://localhost:8000"
            />
            <button class="btn btn-primary btn-sm" @click="handleSaveUrl">
              Save
            </button>
            <button class="btn btn-secondary btn-sm" @click="handleResetUrl">
              Reset
            </button>
          </div>
          <div v-if="savedSuccess" class="text-green text-xs" style="margin-top: 4px;">
            ✓ Backend API URL updated.
          </div>
        </div>

        <!-- Account Session Info -->
        <div style="border-top: 1px solid var(--border-main); padding-top: 12px;">
          <label style="font-weight: 600; font-size: 12px; color: var(--text-secondary); display: block; margin-bottom: 6px;">
            Operator Session
          </label>
          <div style="display: flex; justify-content: space-between; align-items: center;">
            <span class="font-mono text-xs text-muted">{{ userEmail }}</span>
            <button class="btn btn-secondary btn-sm text-red" @click="emit('logout')">
              Sign Out
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- SECTION 2: ADVANCED DIAGNOSTICS (VISUALLY SECONDARY) -->
    <details class="details-accordion">
      <summary>Advanced Diagnostics & Health</summary>
      <div class="card-body">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
          <span class="text-xs text-muted uppercase font-bold">System Health Checks</span>
          <button class="btn btn-secondary btn-sm" :disabled="isTesting" @click="runDiagnostics">
            {{ isTesting ? 'Testing...' : 'Run Diagnostics' }}
          </button>
        </div>

        <div v-if="testResults" style="display: flex; flex-direction: column; gap: 8px; font-size: 12px;">
          <div class="metric-card" style="flex-direction: row; justify-content: space-between; align-items: center;">
            <span>FastAPI Backend</span>
            <span class="font-mono font-bold" :class="testResults.backend.status === 'ok' ? 'text-green' : 'text-red'">
              {{ testResults.backend.message }}
            </span>
          </div>

          <div class="metric-card" style="flex-direction: row; justify-content: space-between; align-items: center;">
            <span>MT5 Data Bridge</span>
            <span class="font-mono font-bold" :class="testResults.bridge.status === 'ok' ? 'text-green' : 'text-amber'">
              {{ testResults.bridge.message }}
            </span>
          </div>

          <div class="metric-card" style="flex-direction: row; justify-content: space-between; align-items: center;">
            <span>Market Symbols Registry</span>
            <span class="font-mono font-bold text-main">
              {{ testResults.symbols.count }} symbols ready
            </span>
          </div>
        </div>
      </div>
    </details>
  </div>
</template>
