<script setup>
import { computed } from 'vue'
import { formatPrice } from '../utils/formatters'

const props = defineProps({
  keyLevels: { type: Object, default: () => ({}) },
  symbol: { type: String, default: 'EURUSDm' },
})

const supports = computed(() => props.keyLevels?.supports?.slice(0, 3) || [])
const resistances = computed(() => props.keyLevels?.resistances?.slice(0, 3) || [])
</script>

<template>
  <div class="panel-container">
    <div class="panel-header border-b border-subtle pb-2 mb-3">
      <h2 class="panel-title text-sm uppercase">KEY LEVELS (NEAR PRICE)</h2>
    </div>

    <div class="flex gap-4">
      <div class="flex-1">
        <h3 class="text-xs text-muted mb-2 uppercase">Resistance</h3>
        <ul class="text-sm font-mono space-y-1">
          <li v-for="(res, idx) in resistances" :key="'res-'+idx" class="text-red">
            {{ formatPrice(res.price, symbol) }}
            <span class="text-muted text-xs ml-1">({{ res.timeframes.join(',') }})</span>
          </li>
          <li v-if="!resistances.length" class="text-muted text-xs">None nearby</li>
        </ul>
      </div>

      <div class="flex-1">
        <h3 class="text-xs text-muted mb-2 uppercase">Support</h3>
        <ul class="text-sm font-mono space-y-1">
          <li v-for="(sup, idx) in supports" :key="'sup-'+idx" class="text-green">
            {{ formatPrice(sup.price, symbol) }}
            <span class="text-muted text-xs ml-1">({{ sup.timeframes.join(',') }})</span>
          </li>
          <li v-if="!supports.length" class="text-muted text-xs">None nearby</li>
        </ul>
      </div>
    </div>
  </div>
</template>
