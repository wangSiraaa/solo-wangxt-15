<script setup>
// 版本详情：BOM 树 + 替代规则管理 + 发布前校验（环/冲突路径）+ 发布
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api'
import BomTree from '../components/BomTree.vue'

const route = useRoute()
const versionId = route.params.id

const version = ref(null)
const tree = ref([])
const rules = ref([])
const materials = ref([])
const validation = ref(null)
const publishMsg = ref('')
const publishErr = ref('')
const ruleErr = ref('')
const publishing = ref(false)

const form = ref({ original: null, substitute: null, serial_start: null, serial_end: null, note: '' })
const isDraft = computed(() => version.value?.status === 'draft')

async function reload() {
  const [v, t, r] = await Promise.all([
    api.version(versionId),
    api.versionTree(versionId),
    api.rules(versionId),
  ])
  version.value = v
  tree.value = t.tree
  rules.value = r
  validation.value = await api.validate(versionId)
}

async function addRule() {
  ruleErr.value = ''
  try {
    await api.createRule({ version: Number(versionId), ...form.value })
    form.value = { original: null, substitute: null, serial_start: null, serial_end: null, note: '' }
    await reload()
  } catch (e) {
    ruleErr.value = e.data ? JSON.stringify(e.data) : e.message
  }
}

async function removeRule(id) {
  ruleErr.value = ''
  try {
    await api.deleteRule(id)
    await reload()
  } catch (e) {
    ruleErr.value = e.data ? JSON.stringify(e.data) : e.message
  }
}

async function publish() {
  publishing.value = true
  publishMsg.value = ''
  publishErr.value = ''
  try {
    await api.publish(versionId)
    publishMsg.value = '发布成功：清单快照与替代规则已冻结生效'
    await reload()
  } catch (e) {
    publishErr.value = e.data?.detail || e.message
    if (e.data) validation.value = { ok: false, cycles: e.data.cycles || [], conflicts: e.data.conflicts || [] }
  } finally {
    publishing.value = false
  }
}

onMounted(async () => {
  materials.value = await api.materials()
  await reload()
})
</script>

<template>
  <div v-if="version">
    <div class="card">
      <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap">
        <h2 style="margin:0">{{ version.product_code }} · {{ version.version }}</h2>
        <span class="badge" :class="version.status">{{ version.status_display }}</span>
        <span class="muted">{{ version.note }}</span>
        <span style="flex:1"></span>
        <button v-if="isDraft" @click="publish" :disabled="publishing || (validation && !validation.ok)">
          {{ publishing ? '发布中…' : '发布版本' }}
        </button>
      </div>
      <p v-if="publishMsg" class="alert ok" style="margin-top:10px">{{ publishMsg }}</p>
      <p v-if="publishErr" class="alert err" style="margin-top:10px">{{ publishErr }}</p>
    </div>

    <!-- 校验面板：替代环 + 区间冲突路径 -->
    <div v-if="validation" class="card">
      <h2>发布前校验</h2>
      <p v-if="validation.ok" class="alert ok">✓ 无替代环、无区间冲突，可以发布</p>

      <div v-for="(cyc, i) in validation.cycles" :key="'c' + i" class="cycle-item">
        <b>替代环 {{ i + 1 }}：</b>
        <span class="mono">{{ cyc.join(' → ') }}</span>
        <span class="muted">（替代关系形成闭环，禁止发布）</span>
      </div>

      <div v-for="(c, i) in validation.conflicts" :key="'k' + i" class="conflict-item">
        <b>区间冲突 {{ i + 1 }}：</b>
        原物料 <span class="mono">{{ c.original.code }}</span> 在序列号
        <span class="mono">[{{ c.overlap.serial_start }}, {{ c.overlap.serial_end }}]</span>
        上同时指向两种物料：
        <span class="mono">{{ c.rules[0].substitute.code }}</span>
        <span class="muted">[{{ c.rules[0].serial_start }}-{{ c.rules[0].serial_end }}]</span>
        <span class="vs">⚡</span>
        <span class="mono">{{ c.rules[1].substitute.code }}</span>
        <span class="muted">[{{ c.rules[1].serial_start }}-{{ c.rules[1].serial_end }}]</span>
        <div style="margin-top:6px">
          <span class="muted">冲突路径（原物料在 BOM 中的位置）：</span>
          <span v-for="loc in c.locations" :key="loc" class="loc">{{ loc }}</span>
          <span v-if="!c.locations.length" class="muted">（当前版本 BOM 未使用该物料）</span>
        </div>
      </div>
    </div>

    <div class="cols">
      <div class="card">
        <h2>BOM 快照树</h2>
        <div class="tree">
          <BomTree v-for="(node, i) in tree" :key="i" :node="node" />
        </div>
      </div>

      <div class="card">
        <h2>替代料区间规则</h2>
        <table class="grid" v-if="rules.length">
          <thead>
            <tr><th>原物料</th><th>替代物料</th><th>序列号区间</th><th>备注</th><th v-if="isDraft"></th></tr>
          </thead>
          <tbody>
            <tr v-for="r in rules" :key="r.id">
              <td class="mono">{{ r.original_code }}</td>
              <td class="mono">{{ r.substitute_code }}</td>
              <td class="mono">[{{ r.serial_start }}, {{ r.serial_end }}]</td>
              <td class="muted">{{ r.note }}</td>
              <td v-if="isDraft"><button class="sm danger" @click="removeRule(r.id)">删除</button></td>
            </tr>
          </tbody>
        </table>
        <p v-else class="muted">暂无规则</p>

        <template v-if="isDraft">
          <h3>新增规则</h3>
          <div class="toolbar">
            <div class="field">
              <label>原物料</label>
              <select v-model="form.original">
                <option v-for="m in materials" :key="m.id" :value="m.id">{{ m.code }} {{ m.name }}</option>
              </select>
            </div>
            <div class="field">
              <label>替代物料</label>
              <select v-model="form.substitute">
                <option v-for="m in materials" :key="m.id" :value="m.id">{{ m.code }} {{ m.name }}</option>
              </select>
            </div>
            <div class="field">
              <label>起始序列号</label>
              <input type="number" v-model.number="form.serial_start" min="0" />
            </div>
            <div class="field">
              <label>截止序列号</label>
              <input type="number" v-model.number="form.serial_end" min="0" />
            </div>
            <div class="field">
              <label>备注</label>
              <input v-model="form.note" />
            </div>
            <button class="ghost" @click="addRule">添加</button>
          </div>
          <p v-if="ruleErr" class="error-text">{{ ruleErr }}</p>
        </template>
        <p v-else class="hint">版本已发布，规则随快照冻结；新规则请建在下一个草稿版本上，且只影响未发料产品。</p>
      </div>
    </div>
  </div>
</template>
