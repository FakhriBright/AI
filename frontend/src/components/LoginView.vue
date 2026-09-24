<script setup>
import { ref } from 'vue'

const props = defineProps({
  loading: {
    type: Boolean,
    default: false,
  },
  error: {
    type: String,
    default: '',
  },
})

const emit = defineEmits(['login'])

const email = ref('')
const password = ref('')
const showPassword = ref(false)

function togglePasswordVisibility() {
  showPassword.value = !showPassword.value
}

function handleSubmit() {
  if (!email.value || !password.value || props.loading) return
  emit('login', {
    email: email.value,
    password: password.value,
  })
}
</script>

<template>
  <div class="simple-login-page">
    <!-- TOP LEFT APP LOGO -->
    <div class="simple-login-header">
      <div class="brand-logo-wrap">
        <div class="brand-logo-icon">
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2.5">
            <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
        </div>
        <span class="brand-logo-title font-mono">AI TRADE</span>
      </div>
    </div>

    <!-- CENTERED LOGIN CARD (MATCHING USER REFERENCE DESIGN) -->
    <div class="simple-login-card">
      <!-- CARD ICON BADGE -->
      <div class="card-icon-badge">
        <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M15 3h4a2 2 0 012 2v14a2 2 0 01-2 2h-4M10 17l5-5-5-5M15 12H3" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
      </div>

      <!-- HEADING & SUBTITLE -->
      <h2 class="card-title">Sign in with email</h2>
      <p class="card-subtitle">
        Enter your operator credentials to access live market analytics and AI decision support.
      </p>

      <!-- LOGIN FORM -->
      <form @submit.prevent="handleSubmit" class="simple-login-form">
        <!-- EMAIL FIELD -->
        <div class="simple-input-wrapper">
          <span class="simple-input-icon">
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/>
              <path d="M22 6l-10 7L2 6"/>
            </svg>
          </span>
          <input
            v-model="email"
            type="email"
            autocomplete="email"
            placeholder="Email address"
            required
            class="simple-input"
          />
        </div>

        <!-- PASSWORD FIELD WITH EYE TOGGLE -->
        <div class="simple-input-wrapper">
          <span class="simple-input-icon">
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2">
              <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
              <path d="M7 11V7a5 5 0 0110 0v4"/>
            </svg>
          </span>
          <input
            v-model="password"
            :type="showPassword ? 'text' : 'password'"
            autocomplete="current-password"
            placeholder="Password"
            required
            class="simple-input input-with-toggle"
          />
          <button
            type="button"
            class="simple-toggle-btn"
            :title="showPassword ? 'Hide Password' : 'Show Password'"
            @click="togglePasswordVisibility"
          >
            <!-- EYE OPEN ICON -->
            <svg v-if="!showPassword" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
              <circle cx="12" cy="12" r="3"/>
            </svg>
            <!-- EYE OFF ICON -->
            <svg v-else viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19m-6.72-1.07a3 3 0 11-4.24-4.24"/>
              <line x1="1" y1="1" x2="23" y2="23"/>
            </svg>
          </button>
        </div>

        <!-- ERROR ALERT BANNER -->
        <div v-if="error" class="simple-alert-error" role="alert">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="10"/>
            <line x1="12" y1="8" x2="12" y2="12"/>
            <line x1="12" y1="16" x2="12.01" y2="16"/>
          </svg>
          <span>{{ error }}</span>
        </div>

        <!-- SUBMIT BUTTON -->
        <button
          type="submit"
          class="simple-submit-btn"
          :disabled="loading || !email || !password"
        >
          <span v-if="loading" class="spinner font-mono">
            <svg class="animate-spin" viewBox="0 0 24 24" width="16" height="16" fill="none">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
            Authenticating...
          </span>
          <span v-else>Get Started</span>
        </button>
      </form>

      <!-- CARD FOOTER NOTE -->
      <div class="card-footer-note text-xs text-muted">
        <span>Protected Terminal Access • Registration Disabled</span>
      </div>
    </div>
  </div>
</template>
