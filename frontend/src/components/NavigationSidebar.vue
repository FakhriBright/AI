<script setup>
import { computed } from 'vue'
import { logout, getStoredUserEmail } from '../services/api'

const props = defineProps({
  currentView: {
    type: String,
    default: 'dashboard',
  },
  bridgeHealth: {
    type: Object,
    default: () => ({}),
  },
  backendConnected: {
    type: Boolean,
    default: true,
  },
})

const emit = defineEmits(['change-view', 'logout'])

const userEmail = computed(() => getStoredUserEmail())

const navItems = [
  { id: 'dashboard', label: 'Terminal Dashboard', icon: 'M3 13h8V3H3v10zm0 8h8v-6H3v6zm10 0h8V11h-8v10zm0-18v6h8V3h-8z' },
  { id: 'chat', label: 'AI Chat Assistant', icon: 'M20 2H4c-1.1 0-1.99.9-1.99 2L2 22l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zM6 9h12v2H6V9zm8 5H6v-2h8v2zm4-6H6V6h12v2z' },
  { id: 'analysis', label: 'Market Analysis', icon: 'M16 6l2.29 2.29-4.88 4.88-4-4L2 16.59 3.41 18l6-6 4 4 6.3-6.29L22 12V6z' },
  { id: 'risk', label: 'Risk & Trade Plan', icon: 'M12 1L3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5l-9-4zm-2 16l-4-4 1.41-1.41L10 14.17l6.59-6.59L18 9l-8 8z' },
  { id: 'settings', label: 'System Settings', icon: 'M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58a.49.49 0 00.12-.61l-1.92-3.32a.49.49 0 00-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54A.48.48 0 0014 2h-4a.48.48 0 00-.49.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96a.49.49 0 00-.59.22L2.63 8.47c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.08.63-.08.94s.02.64.07.94l-2.03 1.58a.49.49 0 00-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h4c.24 0 .44-.17.49-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z' },
]

function handleLogout() {
  logout()
  emit('logout')
}
</script>

<template>
  <aside class="terminal-sidebar">
    <!-- Brand Header -->
    <div class="sidebar-brand">
      <div class="brand-logo-glow">
        <span class="brand-symbol">AI</span>
      </div>
      <div class="brand-info">
        <span class="brand-name">QUANT<span class="text-accent">TERMINAL</span></span>
        <span class="brand-tag">MT5 DECISION SUPPORT</span>
      </div>
    </div>

    <!-- Navigation List -->
    <nav class="sidebar-nav">
      <div class="nav-section-title">NAVIGATION</div>
      <button
        v-for="item in navItems"
        :key="item.id"
        class="nav-btn"
        :class="{ active: currentView === item.id }"
        @click="emit('change-view', item.id)"
      >
        <svg class="nav-icon" viewBox="0 0 24 24" width="18" height="18" fill="currentColor">
          <path :d="item.icon" />
        </svg>
        <span class="nav-label">{{ item.label }}</span>
      </button>
    </nav>

    <!-- Execution Safety Notice -->
    <div class="sidebar-safety-notice">
      <div class="safety-icon">
        <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor">
          <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z" />
        </svg>
      </div>
      <div class="safety-text">
        <strong>MANUAL ONLY</strong>
        <span>AI analysis assistant. No automated order placement.</span>
      </div>
    </div>

    <!-- Connection Diagnostics Status -->
    <div class="sidebar-status-box">
      <div class="status-row">
        <span class="status-label">Backend API:</span>
        <span class="status-value" :class="backendConnected ? 'text-green' : 'text-red'">
          <span class="dot" :class="backendConnected ? 'dot-green' : 'dot-red'"></span>
          {{ backendConnected ? 'Online (:8000)' : 'Offline' }}
        </span>
      </div>
      <div class="status-row">
        <span class="status-label">MT5 Bridge:</span>
        <span class="status-value" :class="bridgeHealth.bridge_status === 'ok' ? 'text-green' : 'text-amber'">
          <span class="dot" :class="bridgeHealth.bridge_status === 'ok' ? 'dot-green' : 'dot-amber'"></span>
          {{ bridgeHealth.bridge_status === 'ok' ? 'Connected (:8765)' : 'Checking...' }}
        </span>
      </div>
    </div>

    <!-- User & Logout Footer -->
    <div class="sidebar-footer">
      <div class="user-chip">
        <div class="user-avatar">
          {{ userEmail.charAt(0).toUpperCase() }}
        </div>
        <div class="user-details">
          <span class="user-name">{{ userEmail }}</span>
          <span class="user-role">Trader (Manual)</span>
        </div>
      </div>
      <button class="logout-btn" title="Sign Out" @click="handleLogout">
        <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
          <path d="M17 7l-1.41 1.41L18.17 11H8v2h10.17l-2.58 2.58L17 17l5-5zM4 5h8V3H4c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h8v-2H4V5z" />
        </svg>
      </button>
    </div>
  </aside>
</template>
