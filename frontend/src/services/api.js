/**
 * Centralized API Service for AI Trading Analysis Platform
 * Connects to FastAPI Backend (:8000)
 */

export function getApiBaseUrl() {
  const customUrl = localStorage.getItem('trading_terminal_api_url')
  if (customUrl && customUrl.trim()) {
    return customUrl.trim().replace(/\/+$/, '')
  }

  const protocol = window.location.protocol || 'http:'
  const hostname = window.location.hostname || 'localhost'

  const envUrl = import.meta.env.VITE_API_BASE_URL
  if (envUrl && envUrl.trim()) {
    const cleanedEnvUrl = envUrl.trim().replace(/\/+$/, '')
    const envIsLocal = cleanedEnvUrl.includes('localhost') || cleanedEnvUrl.includes('127.0.0.1')
    const pageIsLocal = hostname === 'localhost' || hostname === '127.0.0.1'

    if (!envIsLocal || pageIsLocal) {
      return cleanedEnvUrl
    }
  }

  return `${protocol}//${hostname}:8000`
}

export function setApiBaseUrl(url) {
  if (url) {
    localStorage.setItem('trading_terminal_api_url', url.trim())
  } else {
    localStorage.removeItem('trading_terminal_api_url')
  }
}

async function request(endpoint, options = {}) {
  const baseUrl = getApiBaseUrl()
  const url = `${baseUrl}${endpoint.startsWith('/') ? '' : '/'}${endpoint}`

  const headers = {
    'Content-Type': 'application/json',
    ...(options.headers || {}),
  }

  const token = sessionStorage.getItem('access_token')
  if (token && !headers.Authorization) {
    headers.Authorization = `Bearer ${token}`
  }

  let response
  try {
    response = await fetch(url, {
      ...options,
      headers,
    })
  } catch (netErr) {
    throw new Error(
      `Network connection failure to backend (${baseUrl}): ${netErr.message}. Make sure backend server is running.`
    )
  }

  if (response.status === 401) {
    const errorData = await response.json().catch(() => ({}))
    const detail = errorData.detail || 'Session expired. Please log in again.'
    window.dispatchEvent(new CustomEvent('auth:expired', { detail }))
    throw new Error(detail)
  }

  let data
  try {
    data = await response.json()
  } catch {
    data = null
  }

  if (!response.ok) {
    const errorMsg =
      (typeof data?.detail === 'string'
        ? data.detail
        : typeof data?.detail?.message === 'string'
        ? data.detail.message
        : JSON.stringify(data?.detail)) ||
      `Request failed with HTTP status ${response.status}`
    throw new Error(errorMsg)
  }

  return data
}

/**
 * Authentication
 */
export async function login(email, password) {
  const data = await request('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  })

  if (data?.access_token) {
    sessionStorage.setItem('access_token', data.access_token)
    sessionStorage.setItem('user_email', email)
  }

  return data
}

export function logout() {
  sessionStorage.removeItem('access_token')
  sessionStorage.removeItem('user_email')
}

export function getStoredToken() {
  return sessionStorage.getItem('access_token')
}

export function getStoredUserEmail() {
  return sessionStorage.getItem('user_email') || 'Trader'
}

/**
 * Analysis Engine
 */
export async function getAnalysis(symbol, count = 300) {
  return await request(`/analysis/${encodeURIComponent(symbol)}?count=${count}`)
}

/**
 * Market Data Endpoints
 */
export async function getMarketSymbols() {
  return await request('/market/symbols')
}

export async function getMarketCandles(symbol, timeframe = 'M1', count = 100) {
  return await request(
    `/market/candles?symbol=${encodeURIComponent(symbol)}&timeframe=${encodeURIComponent(
      timeframe
    )}&count=${count}`
  )
}

export async function getMarketTick(symbol) {
  return await request(`/market/tick?symbol=${encodeURIComponent(symbol)}`)
}

export async function getSymbolInfo(symbol) {
  return await request(`/market/symbols/${encodeURIComponent(symbol)}/info`)
}

/**
 * Health Diagnostics
 */
export async function getBackendHealth() {
  return await request('/health')
}

export async function getMarketHealth() {
  return await request('/health/market-data')
}

/**
 * Conversational AI Assistant
 *
 * No client-side fallback: if the backend chat endpoint fails, the error is
 * thrown as-is so the UI can show a clear "AI unavailable" state instead of
 * a generated-looking answer built from stale local context.
 */
export async function sendAnalysisChat(symbol, message, history = [], analysisContext = null) {
  return await request(`/analysis/${encodeURIComponent(symbol)}/chat`, {
    method: 'POST',
    body: JSON.stringify({
      symbol,
      message,
      history,
      analysis_context: analysisContext,
    }),
  })
}

