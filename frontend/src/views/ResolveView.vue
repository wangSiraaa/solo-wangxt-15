<script setup>
// 发料反查：输入 产品+序列号 → 应领物料树；未发料可执行发料冻结
import { onMounted, ref } from 'vue'
import { api } from '../api'
import ResolveTree from '../components/ResolveTree.vue'

const products = ref([])
const product = ref('')
const serial = ref(null)
const operator = ref('李工')
const result = ref(null)
const error = ref('')
const issues = ref([])
const loading = ref(false)

async function query() {
  if (!product.value || serial.value === null || serial.value === '') return
  loading.value = true
  error.value = ''
  try {
    result.value = await api.resolve(product.value, serial.value)
  } catch (e) {
    result.value = null
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function issue() {
  error.value = ''
  try {
    result.value = await api.issue({
      product: product.value,
      serial_no: serial.value,
      operator: operator.value,
    })
    await loadIssues()
  } catch (e) {
    error.value = e.data?.detail || e.message
    if (e.status === 409) await query() // 已发料 → 重新拉取冻结快照
    await loadIssues()
  }
}

async function loadIssues() {
  issues.value = await api.issues(product.value || undefined)
}

onMounted(async () => {
  products.value = await api.products()
  product.value = products.value[0]?.code || ''
  await loadIssues()
})
</script>

<template>
  <div>
    <div class="card">
      <h2>发料反查：这个序列号该领什么料？</h2>
      <div class="toolbar">
        <div class="field">
          <label>产品</label>
          <select v-model="product">
            <option v-for="p in products" :key="p.id" :value="p.code">{{ p.code }} {{ p.name }}</option>
          </select>
        </div>
        <div class="field">
          <label>产品序列号</label>
          <input type="number" v-model.number="serial" min="0" placeholder="如 1500" @keyup.enter="query" />
        </div>
        <div class="field">
          <label>操作人（发料时记录）</label>
          <input v-model="operator" />
        </div>
        <button @click="query" :disabled="loading">查询</button>
        <button v-if="result && result.source === 'live'" class="danger" @click="issue">
          按此结果发料（冻结）
        </button>
      </div>
      <p v-if="error" class="error-text">{{ error }}</p>

      <template v-if="result">
        <div class="summary-chips">
          <span class="chip">序列号 {{ result.serial_no }}</span>
          <span class="chip">版本 {{ result.version.version }}</span>
          <span class="badge" :class="result.source">
            {{ result.source === 'issued' ? '已发料 · 冻结快照' : '未发料 · 实时解析' }}
          </span>
          <span v-if="result.issue" class="chip">
            发料人 {{ result.issue.operator || '—' }} · {{ new Date(result.issue.issued_at).toLocaleString() }}
          </span>
        </div>
        <p v-if="result.source === 'issued'" class="hint">
          该序列号已发料，保持原版本结果，后续新规则不影响本次领料。
        </p>
        <div class="tree">
          <ResolveTree v-for="(node, i) in result.lines" :key="i" :node="node" />
        </div>
      </template>
    </div>

    <div class="card">
      <h2>发料记录</h2>
      <table class="grid" v-if="issues.length">
        <thead>
          <tr><th>序列号</th><th>产品</th><th>冻结版本</th><th>操作人</th><th>发料时间</th></tr>
        </thead>
        <tbody>
          <tr v-for="r in issues" :key="r.id">
            <td class="mono">{{ r.serial_no }}</td>
            <td class="mono">{{ r.product_code }}</td>
            <td class="mono">{{ r.version_label }}</td>
            <td>{{ r.operator || '—' }}</td>
            <td class="muted">{{ new Date(r.issued_at).toLocaleString() }}</td>
          </tr>
        </tbody>
      </table>
      <p v-else class="muted">暂无发料记录</p>
    </div>
  </div>
</template>
