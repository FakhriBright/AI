<script setup>
import { ref } from 'vue'
import { login } from './services/api'

const email = ref('')
const password = ref('')
const loading = ref(false)
const error = ref('')
const loggedIn = ref(false)

async function handleLogin() {
  error.value = ''
  loading.value = true

  try {
    const data = await login(email.value, password.value)

    sessionStorage.setItem('access_token', data.access_token)
    loggedIn.value = true
  } catch (err) {
    error.value = err.message
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div v-if="!loggedIn" class="login-page">
    <div class="login-card">
      <div class="brand-mark">AI</div>

      <p class="eyebrow">AI TRADING ANALYSIS</p>
      <h1>Welcome back</h1>
      <p class="subtitle">
        Sign in to access your market analysis dashboard.
      </p>

      <form @submit.prevent="handleLogin">
        <label>
          Email
          <input
            v-model="email"
            type="email"
            autocomplete="email"
            placeholder="Enter your email"
            required
          />
        </label>

        <label>
          Password
          <input
            v-model="password"
            type="password"
            autocomplete="current-password"
            placeholder="Enter your password"
            required
          />
        </label>

        <p v-if="error" class="error">{{ error }}</p>

        <button type="submit" :disabled="loading">
          {{ loading ? 'Signing in...' : 'Sign in' }}
        </button>
      </form>
    </div>
  </div>

  <div v-else class="success-page">
    <div>
      <div class="brand-mark">✓</div>
      <h1>Login berhasil</h1>
      <p>Authentication ke backend sudah berhasil.</p>
    </div>
  </div>
</template>
