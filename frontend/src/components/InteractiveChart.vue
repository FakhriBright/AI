<script setup>
import { ref, onMounted, onUnmounted, watch, computed } from 'vue'
import { getMarketCandles } from '../services/api'
import { formatPrice, formatDateTimeUtc } from '../utils/formatters'

const props = defineProps({
  symbol: {
    type: String,
    default: 'EURUSDm',
  },
  keyLevels: {
    type: Object,
    default: () => ({}),
  },
  selectedScenario: {
    type: Object,
    default: null,
  },
})

const canvasRef = ref(null)
const chartContainerRef = ref(null)
const activeTf = ref('M5')
const timeframes = ['M1', 'M5', 'M15', 'M30', 'H1', 'H4', 'D1']

const candles = ref([])
const isLoading = ref(false)
const error = ref('')

const hoveredCandle = ref(null)
const mousePos = ref({ x: -1, y: -1 })

async function fetchCandles() {
  isLoading.value = true
  error.value = ''
  hoveredCandle.value = null

  try {
    const res = await getMarketCandles(props.symbol, activeTf.value, 80)
    if (res?.candles && Array.isArray(res.candles)) {
      candles.value = res.candles
    } else {
      candles.value = []
    }
  } catch (err) {
    error.value = err.message || 'Failed to fetch candles'
    candles.value = []
  } finally {
    isLoading.value = false
    renderChart()
  }
}

function handleTimeframeChange(tf) {
  if (activeTf.value === tf) return
  activeTf.value = tf
  fetchCandles()
}

watch(
  () => props.symbol,
  () => {
    fetchCandles()
  }
)

watch(
  () => [props.keyLevels, props.selectedScenario],
  () => {
    renderChart()
  },
  { deep: true }
)

function renderChart() {
  const canvas = canvasRef.value
  if (!canvas) return
  const ctx = canvas.getContext('2d')
  if (!ctx) return

  const container = chartContainerRef.value
  const dpr = window.devicePixelRatio || 1
  const width = container ? container.clientWidth : 800
  const height = 500

  canvas.width = width * dpr
  canvas.height = height * dpr
  canvas.style.width = `${width}px`
  canvas.style.height = `${height}px`

  ctx.scale(dpr, dpr)

  // Clear background
  ctx.fillStyle = '#0f172a'
  ctx.fillRect(0, 0, width, height)

  const candleList = candles.value
  if (!candleList || candleList.length === 0) {
    ctx.fillStyle = '#64748b'
    ctx.font = '13px sans-serif'
    ctx.textAlign = 'center'
    ctx.fillText(
      isLoading.value ? 'Loading MT5 market candles...' : (error.value || 'No candle data available'),
      width / 2,
      height / 2
    )
    return
  }

  const padding = { top: 25, bottom: 45, left: 10, right: 65 }
  const chartWidth = width - padding.left - padding.right
  const chartHeight = height - padding.top - padding.bottom

  // Min and Max prices
  let minPrice = Infinity
  let maxPrice = -Infinity
  let maxVol = 0

  for (const c of candleList) {
    if (c.low < minPrice) minPrice = c.low
    if (c.high > maxPrice) maxPrice = c.high
    if (c.tick_volume > maxVol) maxVol = c.tick_volume
  }

  // Include scenario trigger and invalidation in price bounds if near
  const triggerRef = props.selectedScenario?.trigger_reference
  const invalidationRef = props.selectedScenario?.invalidation_reference
  if (triggerRef && Math.abs(triggerRef - minPrice) / (maxPrice - minPrice || 1) < 2) {
    minPrice = Math.min(minPrice, triggerRef)
    maxPrice = Math.max(maxPrice, triggerRef)
  }
  if (invalidationRef && Math.abs(invalidationRef - minPrice) / (maxPrice - minPrice || 1) < 2) {
    minPrice = Math.min(minPrice, invalidationRef)
    maxPrice = Math.max(maxPrice, invalidationRef)
  }

  const priceRange = maxPrice - minPrice || 1
  const priceMargin = priceRange * 0.08
  const chartMin = minPrice - priceMargin
  const chartMax = maxPrice + priceMargin
  const adjustedRange = chartMax - chartMin

  function getY(price) {
    return padding.top + chartHeight - ((price - chartMin) / adjustedRange) * chartHeight
  }

  // Horizontal Grid & Price Axis
  const gridSteps = 5
  ctx.lineWidth = 1
  ctx.strokeStyle = '#1e293b'
  ctx.fillStyle = '#64748b'
  ctx.font = '10px monospace'
  ctx.textAlign = 'left'

  for (let i = 0; i <= gridSteps; i++) {
    const y = padding.top + (chartHeight / gridSteps) * i
    const priceVal = chartMax - (adjustedRange / gridSteps) * i

    ctx.beginPath()
    ctx.moveTo(padding.left, y)
    ctx.lineTo(width - padding.right, y)
    ctx.stroke()

    ctx.fillText(formatPrice(priceVal, props.symbol), width - padding.right + 8, y + 3)
  }

  // Draw Key Levels Overlay
  const supports = props.keyLevels?.supports || []
  const resistances = props.keyLevels?.resistances || []

  // Resistances (red lines)
  ctx.lineWidth = 1
  ctx.setLineDash([4, 4])
  ctx.strokeStyle = 'rgba(239, 68, 68, 0.45)'
  for (const r of resistances.slice(0, 3)) {
    const y = getY(r.price)
    if (y >= padding.top && y <= height - padding.bottom) {
      ctx.beginPath()
      ctx.moveTo(padding.left, y)
      ctx.lineTo(width - padding.right, y)
      ctx.stroke()
    }
  }

  // Supports (green lines)
  ctx.strokeStyle = 'rgba(16, 185, 129, 0.45)'
  for (const s of supports.slice(0, 3)) {
    const y = getY(s.price)
    if (y >= padding.top && y <= height - padding.bottom) {
      ctx.beginPath()
      ctx.moveTo(padding.left, y)
      ctx.lineTo(width - padding.right, y)
      ctx.stroke()
    }
  }

  // Scenario Trigger Line (Cyan)
  if (triggerRef) {
    const y = getY(triggerRef)
    if (y >= padding.top && y <= height - padding.bottom) {
      ctx.strokeStyle = '#06b6d4'
      ctx.lineWidth = 1.5
      ctx.setLineDash([6, 3])
      ctx.beginPath()
      ctx.moveTo(padding.left, y)
      ctx.lineTo(width - padding.right, y)
      ctx.stroke()

      ctx.fillStyle = '#06b6d4'
      ctx.fillText('TRIGGER', width - padding.right + 8, y - 4)
    }
  }

  // Scenario Invalidation Line (Amber)
  if (invalidationRef) {
    const y = getY(invalidationRef)
    if (y >= padding.top && y <= height - padding.bottom) {
      ctx.strokeStyle = '#f59e0b'
      ctx.lineWidth = 1.5
      ctx.setLineDash([6, 3])
      ctx.beginPath()
      ctx.moveTo(padding.left, y)
      ctx.lineTo(width - padding.right, y)
      ctx.stroke()

      ctx.fillStyle = '#f59e0b'
      ctx.fillText('INVAL', width - padding.right + 8, y - 4)
    }
  }

  ctx.setLineDash([]) // reset

  // Candlestick rendering
  const count = candleList.length
  const candleSpacing = chartWidth / count
  const candleWidth = Math.max(2, candleSpacing * 0.7)

  for (let i = 0; i < count; i++) {
    const c = candleList[i]
    const x = padding.left + i * candleSpacing + candleSpacing / 2

    const openY = getY(c.open)
    const closeY = getY(c.close)
    const highY = getY(c.high)
    const lowY = getY(c.low)

    const isBullish = c.close >= c.open
    const color = isBullish ? '#10b981' : '#ef4444'

    // Volume bars at bottom
    if (maxVol > 0) {
      const volHeight = (c.tick_volume / maxVol) * 45
      ctx.fillStyle = isBullish ? 'rgba(16, 185, 129, 0.2)' : 'rgba(239, 68, 68, 0.2)'
      ctx.fillRect(x - candleWidth / 2, height - padding.bottom - volHeight, candleWidth, volHeight)
    }

    // High / Low Wick
    ctx.strokeStyle = color
    ctx.lineWidth = 1.2
    ctx.beginPath()
    ctx.moveTo(x, highY)
    ctx.lineTo(x, lowY)
    ctx.stroke()

    // Body
    ctx.fillStyle = color
    const bodyTop = Math.min(openY, closeY)
    const bodyHeight = Math.max(1.5, Math.abs(closeY - openY))
    ctx.fillRect(x - candleWidth / 2, bodyTop, candleWidth, bodyHeight)
  }

  // Crosshair
  if (mousePos.value.x >= padding.left && mousePos.value.x <= width - padding.right) {
    ctx.strokeStyle = 'rgba(148, 163, 184, 0.4)'
    ctx.setLineDash([2, 2])
    ctx.lineWidth = 1

    // Vertical line
    ctx.beginPath()
    ctx.moveTo(mousePos.value.x, padding.top)
    ctx.lineTo(mousePos.value.x, height - padding.bottom)
    ctx.stroke()

    // Horizontal line
    if (mousePos.value.y >= padding.top && mousePos.value.y <= height - padding.bottom) {
      ctx.beginPath()
      ctx.moveTo(padding.left, mousePos.value.y)
      ctx.lineTo(width - padding.right, mousePos.value.y)
      ctx.stroke()

      // Price Tag on axis
      const hoveredPrice = chartMin + ((height - padding.bottom - mousePos.value.y) / chartHeight) * adjustedRange
      ctx.fillStyle = '#334155'
      ctx.fillRect(width - padding.right + 2, mousePos.value.y - 8, 60, 16)
      ctx.fillStyle = '#f8fafc'
      ctx.font = '10px monospace'
      ctx.fillText(formatPrice(hoveredPrice, props.symbol), width - padding.right + 5, mousePos.value.y + 4)
    }

    ctx.setLineDash([])
  }
}

function handleMouseMove(e) {
  const canvas = canvasRef.value
  if (!canvas || !candles.value.length) return

  const rect = canvas.getBoundingClientRect()
  const x = e.clientX - rect.left
  const y = e.clientY - rect.top

  mousePos.value = { x, y }

  const padding = { left: 10, right: 65 }
  const chartWidth = rect.width - padding.left - padding.right
  const candleSpacing = chartWidth / candles.value.length

  const idx = Math.floor((x - padding.left) / candleSpacing)
  if (idx >= 0 && idx < candles.value.length) {
    hoveredCandle.value = candles.value[idx]
  } else {
    hoveredCandle.value = null
  }

  renderChart()
}

function handleMouseLeave() {
  mousePos.value = { x: -1, y: -1 }
  hoveredCandle.value = null
  renderChart()
}

function handleResize() {
  renderChart()
}

onMounted(() => {
  fetchCandles()
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
})
</script>

<template>
  <div class="panel-container">
    <div class="panel-header">
      <div class="panel-title-wrap">
        <svg class="panel-icon" viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
          <path d="M5 9.2h3V19H5zM10.6 5h2.8v14h-2.8zm5.6 8H19v6h-2.8z" />
        </svg>
        <h2 class="panel-title">INTERACTIVE TECHNICAL CHART</h2>
        <span class="live-tag">LIVE MT5 FEED</span>
      </div>

      <!-- Timeframe Buttons -->
      <div class="chart-controls">
        <div class="tf-btn-group">
          <button
            v-for="tf in timeframes"
            :key="tf"
            class="tf-tab-btn"
            :class="{ active: activeTf === tf }"
            @click="handleTimeframeChange(tf)"
          >
            {{ tf }}
          </button>
        </div>
      </div>
    </div>

    <!-- Candle Hover Data Readout Header -->
    <div class="candle-stat-bar">
      <div v-if="hoveredCandle" class="stat-readout">
        <span class="stat-item"><span class="stat-lbl">Time:</span> {{ formatDateTimeUtc(hoveredCandle.time_utc) }}</span>
        <span class="stat-item"><span class="stat-lbl">O:</span> <span class="font-mono">{{ formatPrice(hoveredCandle.open, symbol) }}</span></span>
        <span class="stat-item"><span class="stat-lbl">H:</span> <span class="font-mono">{{ formatPrice(hoveredCandle.high, symbol) }}</span></span>
        <span class="stat-item"><span class="stat-lbl">L:</span> <span class="font-mono">{{ formatPrice(hoveredCandle.low, symbol) }}</span></span>
        <span class="stat-item"><span class="stat-lbl">C:</span> <span class="font-mono" :class="hoveredCandle.close >= hoveredCandle.open ? 'text-green' : 'text-red'">{{ formatPrice(hoveredCandle.close, symbol) }}</span></span>
        <span class="stat-item"><span class="stat-lbl">Vol:</span> {{ hoveredCandle.tick_volume }}</span>
        <span class="stat-item"><span class="stat-lbl">Spread:</span> {{ hoveredCandle.spread ?? '—' }} pts</span>
      </div>
      <div v-else class="stat-readout text-muted">
        <span>Hover over candles to view precise bar data (Open, High, Low, Close, Volume).</span>
      </div>
      <div class="chart-legend-row">
        <span class="legend-chip"><span class="chip-line chip-res"></span>Resistance</span>
        <span class="legend-chip"><span class="chip-line chip-sup"></span>Support</span>
        <span class="legend-chip"><span class="chip-line chip-trig"></span>Trigger</span>
        <span class="legend-chip"><span class="chip-line chip-inv"></span>Inval</span>
      </div>
    </div>

    <!-- Canvas Container -->
    <div
      ref="chartContainerRef"
      class="canvas-wrap"
      @mousemove="handleMouseMove"
      @mouseleave="handleMouseLeave"
    >
      <canvas ref="canvasRef" class="trading-canvas"></canvas>
    </div>
  </div>
</template>
