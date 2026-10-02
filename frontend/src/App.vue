<script setup>
import { ref, onMounted, onUnmounted, watch, computed } from 'vue'
import {
  login,
  logout,
  getStoredToken,
  getAnalysis,
  getMarketSymbols,
  getMarketHealth,
  getMarketTick,
} from './services/api'

import { getInitialTheme, applyTheme, toggleThemeCurrent } from './utils/themeManager'
import NavigationSidebar from './components/NavigationSidebar.vue'
import TopBar from './components/TopBar.vue'
import AIChatAssistant from './components/AIChatAssistant.vue'
import LoginView from './components/LoginView.vue'

// Auth State
const loginLoading = ref(false)
const loginError = ref('')
const loggedIn = ref(Boolean(getStoredToken()))

// Theme State
const currentTheme = ref(getInitialTheme())

function handleToggleTheme() {
  currentTheme.value = toggleThemeCurrent()
}

// Sidebar Collapse State
const isSidebarCollapsed = ref(false)

function toggleSidebar() {
  isSidebarCollapsed.value = !isSidebarCollapsed.value
}

// Resizable AI Panel Width State
const aiPanelWidth = ref(360)
const isResizing = ref(false)
let startX = 0
let startWidth = 0

function startResizing(e) {
  isResizing.value = true
  startX = e.clientX
  startWidth = aiPanelWidth.value
  window.addEventListener('mousemove', onMouseMove)
  window.addEventListener('mouseup', onMouseUp)
}

function onMouseMove(e) {
  if (!isResizing.value) return
  // Dragging left increases AI panel width, dragging right decreases it
  const delta = startX - e.clientX
  const newWidth = Math.min(Math.max(280, startWidth + delta), 650)
  aiPanelWidth.value = newWidth
}

function onMouseUp() {
  if (isResizing.value) {
    isResizing.value = false
    window.removeEventListener('mousemove', onMouseMove)
    window.removeEventListener('mouseup', onMouseUp)
  }
}

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
let tickTimer = null

const liveTick = ref(null)

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
  liveTick.value = null
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

const lastKnownCandleTime = ref(null)

async function fetchAnalysis() {
  if (!loggedIn.value) return

  isAnalysisLoading.value = true
  analysisError.value = ''
  const targetSymbol = selectedSymbol.value

  try {
    const data = await getAnalysis(targetSymbol)

    // Ignore stale response if user switched symbol while request was running.
    if (selectedSymbol.value !== targetSymbol) return

    analysisData.value = data
    if (data?.latest_candle?.time_utc) {
      lastKnownCandleTime.value = data.latest_candle.time_utc
    }
  } catch (err) {
    if (selectedSymbol.value !== targetSymbol) return

    analysisError.value = 'Unable to load market data.'
    if (err.message && err.message.toLowerCase().includes('session expired')) {
      handleLogout()
    }
  } finally {
    if (selectedSymbol.value === targetSymbol) {
      isAnalysisLoading.value = false
    }
  }
}

async function fetchLiveTick() {
  if (!loggedIn.value) return

  const targetSymbol = selectedSymbol.value

  try {
    const tick = await getMarketTick(targetSymbol)

    // Ignore stale response if user switched symbol while request was running.
    if (selectedSymbol.value !== targetSymbol) return

    if (tick) {
      liveTick.value = tick
    }
  } catch (err) {
    // Keep the last known tick. The next poll can recover automatically.
    console.warn('Could not load live tick:', err.message)
  }
}

function handleSelectSymbol(newSymbol) {
  if (selectedSymbol.value === newSymbol) return
  selectedSymbol.value = newSymbol
  lastKnownCandleTime.value = null
  analysisData.value = null
  liveTick.value = null
  fetchAnalysis()
  fetchLiveTick()
}

async function handleAutoRefresh() {
  if (!loggedIn.value || isAnalysisLoading.value) return
  await checkBridgeHealth()

  // Skip triggering full analysis/AI if market candle timestamp has not changed
  if (analysisData.value?.latest_candle?.time_utc) {
    const currentCandleTime = analysisData.value.latest_candle.time_utc
    if (lastKnownCandleTime.value && lastKnownCandleTime.value === currentCandleTime) {
      return
    }
  }

  await fetchAnalysis()
}

function startAutoRefresh() {
  stopAutoRefresh()

  refreshTimer = setInterval(() => {
    handleAutoRefresh()
  }, 30000)

  tickTimer = setInterval(() => {
    fetchLiveTick()
  }, 2000)
}

function stopAutoRefresh() {
  if (refreshTimer) {
    clearInterval(refreshTimer)
    refreshTimer = null
  }

  if (tickTimer) {
    clearInterval(tickTimer)
    tickTimer = null
  }
}

async function initTerminal() {
  await checkBridgeHealth()
  await fetchSymbols()
  await Promise.all([fetchAnalysis(), fetchLiveTick()])
  startAutoRefresh()
}

onMounted(() => {
  applyTheme(currentTheme.value)
  window.addEventListener('auth:expired', onAuthExpired)
  if (loggedIn.value) {
    initTerminal()
  }
})

onUnmounted(() => {
  window.removeEventListener('auth:expired', onAuthExpired)
  window.removeEventListener('mousemove', onMouseMove)
  window.removeEventListener('mouseup', onMouseUp)
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
      :collapsed="isSidebarCollapsed"
      @toggle-collapse="toggleSidebar"
      @logout="handleLogout"
    />

    <!-- MAIN VIEWPORT -->
    <div class="main-viewport">
      <!-- TOP BAR -->
      <TopBar
        :symbols="symbols"
        :selected-symbol="selectedSymbol"
        :current-price="liveTick?.bid ?? analysisData?.key_levels?.current_price"
        :live-tick="liveTick"
        :latest-candle="analysisData?.latest_candle"
        :is-loading="isAnalysisLoading"
        :bridge-health="bridgeHealth"
        :current-theme="currentTheme"
        @select-symbol="handleSelectSymbol"
        @refresh="fetchAnalysis"
        @toggle-theme="handleToggleTheme"
        @logout="handleLogout"
      />

      <!-- WORKSPACE AREA (MAIN CONTENT | RESIZE DIVIDER | RIGHT AI PANEL) -->
      <main class="cockpit-body">
        <!-- MAIN CONTENT (ROUTE VIEWPORT) -->
        <div class="cockpit-main-content">
          <router-view
            :symbol="selectedSymbol"
            :symbols="symbols"
            :analysis-data="analysisData"
            :live-tick="liveTick"
            :bridge-health="bridgeHealth"
            :is-bridge-offline="isBridgeOffline"
            @select-symbol="handleSelectSymbol"
            @retry="initTerminal"
            @logout="handleLogout"
          />
        </div>

        <!-- HORIZONTAL RESIZE DIVIDER (DRAG HANDLE) -->
        <div
          class="resize-divider"
          :class="{ 'is-resizing': isResizing }"
          title="Drag to resize AI Analyst panel"
          @mousedown.prevent="startResizing"
        ></div>

        <!-- RIGHT SIDE PANEL (AI ANALYST - RESIZABLE) -->
        <AIChatAssistant
          :symbol="selectedSymbol"
          :analysis-data="analysisData"
          :style="{ width: aiPanelWidth + 'px' }"
        />
      </main>
    </div>
  </div>
</template>
