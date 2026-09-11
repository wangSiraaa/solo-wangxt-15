<script setup>
// 版本比较：两版 BOM 的树形差异
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
import DiffTree from '../components/DiffTree.vue'

const versions = ref([])
const fromId = ref(null)
const toId = ref(null)
const result = ref(null)
const error = ref('')
const loading = ref(false)

const label = (v) => `${v.product_code} ${v.version}（${v.status_display}）`

async function run() {
  if (!fromId.value || !toId.value) return
  loading.value = true
  error.value = ''
  try {
    result.value = await api.compare(fromId.value, toId.value)
  } catch (e) {
    error.value = e.message
    result.value = null
  } finally {
    loading.value = false
  }
}

const summary = computed(() => result.value?.summary)

onMounted(async () => {
  versions.value = await api.versions()
  const v1 = versions.value.find((v) => v.version === 'V1.0')
  const v2 = versions.value.find((v) => v.version === 'V2.0')
  fromId.value = (v1 || versions.value[0])?.id ?? null
  toId.value = (v2 || versions.value[1])?.id ?? null
  await run()
})
</script>

<template>
  <div class="card">
    <h2>版本比较（树形差异）</h2>
    <div class="toolbar">
      <div class="field">
        <label>基准版本</label>
        <select v-model="fromId" @change="run">
          <option v-for="v in versions" :key="v.id" :value="v.id">{{ label(v) }}</option>
        </select>
      </div>
      <div class="field">
        <label>目标版本</label>
        <select v-model="toId" @change="run">
          <option v-for="v in versions" :key="v.id" :value="v.id">{{ label(v) }}</option>
        </select>
      </div>
      <button @click="run" :disabled="loading">比较</button>
    </div>

    <p v-if="error" class="error-text">{{ error }}</p>

    <template v-if="result">
      <div class="summary-chips">
        <span class="chip added">新增 {{ summary.added }}</span>
        <span class="chip removed">删除 {{ summary.removed }}</span>
        <span class="chip changed">变更 {{ summary.changed }}</span>
        <span class="chip">未变 {{ summary.unchanged }}</span>
      </div>
      <div class="tree">
        <DiffTree v-for="(node, i) in result.tree" :key="i" :node="node" />
      </div>
    </template>
  </div>
</template>
