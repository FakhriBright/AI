<script setup>
import { ref, onMounted } from 'vue'
import {
  getApiBaseUrl,
  setApiBaseUrl,
  getBackendHealth,
  getMarketHealth,
  getMarketSymbols,
  getStoredToken,
  getStoredUserEmail,
  logout,
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
  const defaultUrl = 'http://172.16.204.27:8000'
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

  // 1. Backend /health
  try {
    const bHealth = await getBackendHealth()
    testResults.value.backend = {
      status: bHealth?.status === 'ok' ? 'ok' : 'warning',
      message: bHealth?.status === 'ok' ? 'Connected' : 'Unavailable',
    }
  } catch (err) {
    testResults.value.backend = {
      status: 'error',
      message: 'Disconnected',
    }
  }

  // 2. MT5 Bridge /health/market-data
  try {
    const mHealth = await getMarketHealth()
    const ok = mHealth?.bridge_status === 'ok' && mHealth?.data_source_connected
    testResults.value.bridge = {
      status: ok ? 'ok' : 'warning',
      message: ok ? 'Connected' : 'Disconnected',
    }
  } catch (err) {
    testResults.value.bridge = {
      status: 'error',
      message: 'Disconnected',
    }
  }

  // 3. Symbols
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
  <div class="settings-view-container">
    <div class="panel-header">
      <div class="panel-title-wrap">
        <svg class="panel-icon" viewBox="0 0 24 24" width="18" height="18" fill="currentColor">
          <path d="M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58a.49.49 0 00.12-.61l-1.92-3.32a.49.49 0 00-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54A.48.48 0 0014 2h-4a.48.48 0 00-.49.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96a.49.49 0 00-.59.22L2.63 8.47c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.08.63-.08.94s.02.64.07.94l-2.03 1.58a.49.49 0 00-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h4c.24 0 .44-.17.49-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z" />
        </svg>
        <h2 class="panel-title">TERMINAL & BACKEND CONFIGURATION</h2>
      </div>
      <span class="panel-subtitle">Environment & Network Settings</span>
    </div>

    <div class="settings-grid">
      <!-- Backend URL Configuration -->
      <div class="settings-card">
        <h3 class="settings-card-title">BACKEND CONNECTION</h3>
        <p class="settings-desc">
          Configure the FastAPI backend API endpoint address.
        </p>

        <div class="form-group mt-3">
          <label class="input-label" for="backend-url-input">API Base URL</label>
          <div class="input-row">
            <input
              id="backend-url-input"
              v-model="apiUrlInput"
              type="text"
              class="terminal-input"
              placeholder="http://172.16.204.27:8000"
            />
            <button class="btn-primary" @click="handleSaveUrl">
              Save URL
            </button>
            <button class="btn-secondary" @click="handleResetUrl">
              Reset Default
            </button>
          </div>
        </div>

        <div v-if="savedSuccess" class="alert-success mt-2">
          ✓ Backend API URL updated successfully.
        </div>
      </div>

      <!-- Network & Bridge Diagnostics -->
      <div class="settings-card">
        <div class="card-header-flex">
          <h3 class="settings-card-title">LIVE CONNECTION DIAGNOSTICS</h3>
          <button class="btn-sm btn-secondary" :disabled="isTesting" @click="runDiagnostics">
            {{ isTesting ? 'Testing...' : 'Rerun Diagnostics' }}
          </button>
        </div>

        <div v-if="testResults" class="diagnostics-list mt-3">
          <!-- Backend Status -->
          <div class="diag-item">
            <div class="diag-header">
              <span class="dot" :class="testResults.backend.status === 'ok' ? 'dot-green' : 'dot-red'"></span>
              <span class="diag-name">Backend</span>
            </div>
            <div class="diag-val font-mono text-xs">{{ testResults.backend.message }}</div>
          </div>

          <!-- MT5 Bridge Status -->
          <div class="diag-item">
            <div class="diag-header">
              <span class="dot" :class="testResults.bridge.status === 'ok' ? 'dot-green' : 'dot-amber'"></span>
              <span class="diag-name">MT5 data feed</span>
            </div>
            <div class="diag-val font-mono text-xs">{{ testResults.bridge.message }}</div>
          </div>

          <!-- Symbols Availability -->
          <div class="diag-item">
            <div class="diag-header">
              <span class="dot" :class="testResults.symbols.status === 'ok' ? 'dot-green' : 'dot-red'"></span>
              <span class="diag-name">Market Symbols Available</span>
            </div>
            <div class="diag-val font-mono text-xs">
              {{ testResults.symbols.count }} symbols ready ({{ testResults.symbols.list || '...' }})
            </div>
          </div>
        </div>
      </div>

      <!-- User Session & Authentication -->
      <div class="settings-card">
        <h3 class="settings-card-title">AUTHENTICATION & SESSION</h3>

        <div class="session-info-list mt-3">
          <div class="session-row">
            <span class="session-label">Active User:</span>
            <span class="session-val font-mono">{{ userEmail }}</span>
          </div>
          <div class="session-row">
            <span class="session-label">Authentication:</span>
            <span class="session-val font-mono text-xs text-muted">
              {{ token ? 'Active' : 'Not Available' }}
            </span>
          </div>
          <div class="session-row">
            <span class="session-label">Execution Mode:</span>
            <span class="badge badge-amber font-bold">MANUAL ONLY</span>
          </div>
        </div>

        <div class="session-actions mt-4">
          <button class="btn-danger" @click="emit('logout')">
            End Session (Sign Out)
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
