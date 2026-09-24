<script setup>
import { ref, onMounted, onUnmounted, watch, computed } from 'vue'
import {
  login,
  logout,
  getStoredToken,
  getAnalysis,
  getMarketSymbols,
  getMarketHealth,
} from './services/api'

import NavigationSidebar from './components/NavigationSidebar.vue'
import TopBar from './components/TopBar.vue'
import AIChatAssistant from './components/AIChatAssistant.vue'
import LoginView from './components/LoginView.vue'

// Auth State
const loginLoading = ref(false)
const loginError = ref('')
const loggedIn = ref(Boolean(getStoredToken()))

// Data State
const symbols = ref(['EURUSDm', 'XAUUSDm'])
const selectedSymbol = ref('EURUSDm')
const analysisData = ref(null)
const isAnalysisLoading = ref(false)
const analysisError = ref('')
const bridgeHealth = ref({})

const isBridgeOffline = computed(() => {
  return bridgeHealth.value?.bridge_status !== 'ok' || bridgeHealth.value?.data_source_connected === false
})

let refreshTimer = null

async function handleLogin(credentials) {
  loginError.value = ''
  loginLoading.value = true

  const userEmail = credentials?.email || ''
  const userPassword = credentials?.password || ''

  try {
    const data = await login(userEmail, userPassword)
    if (data?.access_token) {
      loggedIn.value = true
      initTerminal()
    }
  } catch (err) {
    loginError.value = err.message || 'Login failed'
  } finally {
    loginLoading.value = false
  }
}

function handleLogout() {
  logout()
  loggedIn.value = false
  analysisData.value = null
  stopAutoRefresh()
}

function onAuthExpired(event) {
  loginError.value = event.detail || 'Session expired. Please log in again.'
  handleLogout()
}

async function fetchSymbols() {
  try {
    const res = await getMarketSymbols()
    if (res?.symbols && Array.isArray(res.symbols) && res.symbols.length) {
      symbols.value = res.symbols.slice()
    }
  } catch (err) {
    console.warn('Could not load symbols:', err.message)
  }
}

async function checkBridgeHealth() {
  try {
    const res = await getMarketHealth()
    bridgeHealth.value = res || {}
  } catch (err) {
    bridgeHealth.value = { bridge_status: 'down', data_source_connected: false }
  }
}

async function fetchAnalysis() {
  if (!loggedIn.value) return

  isAnalysisLoading.value = true
  analysisError.value = ''

  try {
    const data = await getAnalysis(selectedSymbol.value)
    analysisData.value = data
  } catch (err) {
    analysisError.value = 'Unable to load market data.'
    if (err.message && err.message.toLowerCase().includes('session expired')) {
      handleLogout()
    }
  } finally {
    isAnalysisLoading.value = false
  }
}

function handleSelectSymbol(newSymbol) {
  if (selectedSymbol.value === newSymbol) return
  selectedSymbol.value = newSymbol
  fetchAnalysis()
}

function startAutoRefresh() {
  stopAutoRefresh()
  refreshTimer = setInterval(() => {
    if (loggedIn.value && !isAnalysisLoading.value) {
      fetchAnalysis()
      checkBridgeHealth()
    }
  }, 30000)
}

function stopAutoRefresh() {
  if (refreshTimer) {
    clearInterval(refreshTimer)
    refreshTimer = null
  }
}

async function initTerminal() {
  await checkBridgeHealth()
  await fetchSymbols()
  await fetchAnalysis()
  startAutoRefresh()
}

onMounted(() => {
  window.addEventListener('auth:expired', onAuthExpired)
  if (loggedIn.value) {
    initTerminal()
  }
})

onUnmounted(() => {
  window.removeEventListener('auth:expired', onAuthExpired)
  stopAutoRefresh()
})

watch(loggedIn, (isAuth) => {
  if (isAuth) {
    initTerminal()
  } else {
    stopAutoRefresh()
  }
})
</script>

<template>
  <!-- 1. LOGIN VIEW -->
  <LoginView
    v-if="!loggedIn"
    :loading="loginLoading"
    :error="loginError"
    @login="handleLogin"
  />

  <!-- 2. QUANTTERMINAL APPLICATION SHELL (3-COLUMN SPA WITH ROUTER) -->
  <div v-else class="app-shell">
    <!-- LEFT SIDEBAR -->
    <NavigationSidebar
      :bridge-health="bridgeHealth"
      @logout="handleLogout"
    />

    <!-- MAIN VIEWPORT -->
    <div class="main-viewport">
      <!-- TOP BAR -->
      <TopBar
        :symbols="symbols"
        :selected-symbol="selectedSymbol"
        :current-price="analysisData?.key_levels?.current_price"
        :latest-candle="analysisData?.latest_candle"
        :is-loading="isAnalysisLoading"
        :bridge-health="bridgeHealth"
        @select-symbol="handleSelectSymbol"
        @refresh="fetchAnalysis"
        @logout="handleLogout"
      />

      <!-- WORKSPACE AREA (ROUTE VIEWPORT + RIGHT AI PANEL) -->
      <main class="cockpit-body">
        <!-- ROUTE VIEWPORT -->
        <router-view
          :symbol="selectedSymbol"
          :symbols="symbols"
          :analysis-data="analysisData"
          :bridge-health="bridgeHealth"
          :is-bridge-offline="isBridgeOffline"
          @select-symbol="handleSelectSymbol"
          @retry="initTerminal"
          @logout="handleLogout"
        />

        <!-- RIGHT SIDE PANEL (AI ANALYST + COMPACT MARKET CONTEXT) -->
        <AIChatAssistant
          :symbol="selectedSymbol"
          :analysis-data="analysisData"
        />
      </main>
    </div>
  </div>
</template>
