<script setup>
import { ref, onMounted, onUnmounted, watch } from 'vue'
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
import MarketOverviewCards from './components/MarketOverviewCards.vue'
import InteractiveChart from './components/InteractiveChart.vue'
import MultiTimeframeGrid from './components/MultiTimeframeGrid.vue'
import MarketStructurePanel from './components/MarketStructurePanel.vue'
import KeyLevelsPanel from './components/KeyLevelsPanel.vue'
import TradePlanPanel from './components/TradePlanPanel.vue'
import AIReasoningPanel from './components/AIReasoningPanel.vue'
import AIChatAssistant from './components/AIChatAssistant.vue'
import SettingsView from './components/SettingsView.vue'
import RiskSettingsView from './components/RiskSettingsView.vue'



// Authentication State
const email = ref('')
const password = ref('')
const loginLoading = ref(false)
const loginError = ref('')
const loggedIn = ref(Boolean(getStoredToken()))


// Active Views: 'dashboard', 'analysis', 'risk', 'settings'
const currentView = ref('dashboard')

// Terminal Data State
const symbols = ref(['EURUSDm', 'XAUUSDm'])
const selectedSymbol = ref('EURUSDm')
const analysisData = ref(null)
const isAnalysisLoading = ref(false)
const analysisError = ref('')
const bridgeHealth = ref({})
const backendConnected = ref(true)

// Auto-refresh interval (0 = off, 15 = 15s, etc.)
const autoRefreshInterval = ref(30)
let refreshTimer = null

async function handleLogin() {
  loginError.value = ''
  loginLoading.value = true

  try {
    const data = await login(email.value, password.value)
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

// Global listener for expired tokens
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
    console.warn('Could not load symbols list from backend:', err.message)
  }
}

async function checkBridgeHealth() {
  try {
    const res = await getMarketHealth()
    bridgeHealth.value = res || {}
    backendConnected.value = true
  } catch (err) {
    bridgeHealth.value = { bridge_status: 'down', data_source_connected: false }
    backendConnected.value = false
  }
}

async function fetchAnalysis() {
  if (!loggedIn.value) return

  isAnalysisLoading.value = true
  analysisError.value = ''

  try {
    const data = await getAnalysis(selectedSymbol.value)
    analysisData.value = data
    backendConnected.value = true
  } catch (err) {
    analysisError.value = err.message || 'Failed to fetch market analysis'
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

function handleAutoRefreshChange(intervalSec) {
  autoRefreshInterval.value = intervalSec
  resetAutoRefresh()
}

function startAutoRefresh() {
  stopAutoRefresh()
  if (autoRefreshInterval.value > 0) {
    refreshTimer = setInterval(() => {
      if (loggedIn.value && !isAnalysisLoading.value) {
        fetchAnalysis()
        checkBridgeHealth()
      }
    }, autoRefreshInterval.value * 1000)
  }
}

function stopAutoRefresh() {
  if (refreshTimer) {
    clearInterval(refreshTimer)
    refreshTimer = null
  }
}

function resetAutoRefresh() {
  stopAutoRefresh()
  startAutoRefresh()
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
  <!-- 1. LOGIN SCREEN -->
  <div v-if="!loggedIn" class="login-page">
    <div class="login-card">
      <div class="brand-mark-glow">
        <span class="brand-logo-txt">AI</span>
      </div>

      <p class="eyebrow">QUANT TRADING ANALYSIS PLATFORM</p>
      <h1>Terminal Access</h1>
      <p class="subtitle">
        Authenticate against the FastAPI backend (:8000) to access live MT5 market analysis and decision support.
      </p>

      <form @submit.prevent="handleLogin">
        <label>
          Operator Email
          <input
            v-model="email"
            type="email"
            autocomplete="email"
            placeholder="trader@example.com"
            required
          />
        </label>

        <label>
          Secret Key / Password
          <input
            v-model="password"
            type="password"
            autocomplete="current-password"
            placeholder="Enter password"
            required
          />
        </label>

        <div v-if="loginError" class="login-error-alert">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
            <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z" />
          </svg>
          <span>{{ loginError }}</span>
        </div>

        <button type="submit" class="login-submit-btn" :disabled="loginLoading">
          <span v-if="loginLoading" class="btn-spinner"></span>
          <span>{{ loginLoading ? 'Authenticating...' : 'Sign In to Terminal' }}</span>
        </button>

      </form>

      <div class="login-footer-info">
        <span>MANUAL EXECUTION SYSTEM &bull; MT5 BRIDGE INTEGRATED</span>
      </div>
    </div>
  </div>

  <!-- 2. TRADING TERMINAL WORKSTATION -->
  <div v-else class="terminal-layout">
    <!-- Sidebar Navigation -->
    <NavigationSidebar
      :current-view="currentView"
      :bridge-health="bridgeHealth"
      :backend-connected="backendConnected"
      @change-view="currentView = $event"
      @logout="handleLogout"
    />

    <!-- Main Viewport Area -->
    <div class="terminal-main">
      <!-- Top Bar -->
      <TopBar
        :symbols="symbols"
        :selected-symbol="selectedSymbol"
        :current-price="analysisData?.key_levels?.current_price"
        :latest-candle="analysisData?.latest_candle"
        :generated-at="analysisData?.generated_at_utc"
        :is-loading="isAnalysisLoading"
        :bridge-health="bridgeHealth"
        :auto-refresh-interval="autoRefreshInterval"
        @select-symbol="handleSelectSymbol"
        @refresh="fetchAnalysis"
        @update-auto-refresh="handleAutoRefreshChange"
        @logout="handleLogout"
      />

      <!-- Content Container -->
      <main class="terminal-content">
        <!-- Error Banner if analysis failed -->
        <div v-if="analysisError" class="terminal-error-banner">
          <div class="error-banner-icon">
            <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
              <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z" />
            </svg>
          </div>
          <div class="error-banner-msg">
            <strong>ANALYSIS FEED ERROR:</strong> {{ analysisError }}
          </div>
          <button class="btn-sm btn-secondary" @click="fetchAnalysis">
            Retry Now
          </button>
        </div>

        <!-- VIEW 1: DASHBOARD (Comprehensive Workstation) -->
        <div v-if="currentView === 'dashboard'" class="dashboard-view">
          <!-- 1. Market Overview Cards -->
          <MarketOverviewCards
            :symbol="selectedSymbol"
            :market-bias="analysisData?.market_bias"
            :selected-scenario="analysisData?.selected_scenario"
            :confirmation="analysisData?.confirmation"
            :current-price="analysisData?.key_levels?.current_price"
            :latest-candle="analysisData?.latest_candle"
            :trade-plan="analysisData?.trade_plan"
            :stop-plan="analysisData?.stop_plan"
          />

          <!-- 2. Interactive Candlestick Chart (Hero Element) -->
          <InteractiveChart
            :symbol="selectedSymbol"
            :key-levels="analysisData?.key_levels"
            :selected-scenario="analysisData?.selected_scenario"
          />

          <!-- 3. Key Levels & Market Structure Side-by-Side -->
          <div class="two-column-layout mt-3">
            <KeyLevelsPanel
              :key-levels="analysisData?.key_levels"
              :selected-scenario="analysisData?.selected_scenario"
              :symbol="selectedSymbol"
            />
            <MarketStructurePanel
              :multi-timeframe="analysisData?.multi_timeframe"
              :symbol="selectedSymbol"
              initial-timeframe="M5"
            />
          </div>

          <!-- 4. Multi-Timeframe Analysis Matrix -->
          <MultiTimeframeGrid
            :multi-timeframe="analysisData?.multi_timeframe"
            :symbol="selectedSymbol"
          />

          <!-- 7. AI Reasoning Engine Panel -->
          <AIReasoningPanel
            :ai-data="analysisData?.ai"
            :symbol="selectedSymbol"
          />

          <!-- 8. Conversational AI Assistant Panel -->
          <AIChatAssistant
            :symbol="selectedSymbol"
            :analysis-data="analysisData"
          />
        </div>

        <!-- VIEW 2: DEDICATED AI CHAT ASSISTANT -->
        <div v-else-if="currentView === 'chat'" class="deep-dive-view">
          <AIChatAssistant
            :symbol="selectedSymbol"
            :analysis-data="analysisData"
          />
          <AIReasoningPanel
            :ai-data="analysisData?.ai"
            :symbol="selectedSymbol"
          />
        </div>

        <!-- VIEW 3: MARKET ANALYSIS DEEP DIVE -->
        <div v-else-if="currentView === 'analysis'" class="deep-dive-view">
          <InteractiveChart
            :symbol="selectedSymbol"
            :key-levels="analysisData?.key_levels"
            :selected-scenario="analysisData?.selected_scenario"
          />
          <MultiTimeframeGrid
            :multi-timeframe="analysisData?.multi_timeframe"
            :symbol="selectedSymbol"
          />
          <MarketStructurePanel
            :multi-timeframe="analysisData?.multi_timeframe"
            :symbol="selectedSymbol"
            initial-timeframe="M15"
          />
          <KeyLevelsPanel
            :key-levels="analysisData?.key_levels"
            :selected-scenario="analysisData?.selected_scenario"
            :symbol="selectedSymbol"
          />
        </div>

        <!-- VIEW 4: RISK & TRADE PLAN DEEP DIVE -->
        <div v-else-if="currentView === 'risk'" class="deep-dive-view">
          <TradePlanPanel
            :trade-plan="analysisData?.trade_plan"
            :stop-plan="analysisData?.stop_plan"
            :symbol="selectedSymbol"
          />
          <RiskSettingsView
            :trade-plan="analysisData?.trade_plan"
            :stop-plan="analysisData?.stop_plan"
            :symbol="selectedSymbol"
          />
        </div>

        <!-- VIEW 5: SYSTEM SETTINGS & DIAGNOSTICS -->
        <div v-else-if="currentView === 'settings'" class="settings-view">
          <SettingsView @logout="handleLogout" />
        </div>
      </main>
    </div>
  </div>
</template>
