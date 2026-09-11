<script setup>
// 版本总览：产品 → 版本列表，进入详情/比较/反查的入口
import { onMounted, ref } from 'vue'
import { api } from '../api'

const versions = ref([])
const error = ref('')

onMounted(async () => {
  try {
    versions.value = await api.versions()
  } catch (e) {
    error.value = e.message
  }
})
</script>

<template>
  <div>
    <div class="card">
      <h2>产品 BOM 版本</h2>
      <p v-if="error" class="error-text">{{ error }}</p>
      <table class="grid" v-if="versions.length">
        <thead>
          <tr>
            <th>产品</th><th>版本</th><th>状态</th><th>清单行</th><th>替代规则</th>
            <th>发布时间</th><th>备注</th><th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="v in versions" :key="v.id">
            <td class="mono">{{ v.product_code }} <span class="muted">{{ v.product_name }}</span></td>
            <td class="mono">{{ v.version }}</td>
            <td><span class="badge" :class="v.status">{{ v.status_display }}</span></td>
            <td>{{ v.line_count }}</td>
            <td>{{ v.rule_count }}</td>
            <td class="muted">{{ v.published_at ? new Date(v.published_at).toLocaleString() : '—' }}</td>
            <td class="muted">{{ v.note }}</td>
            <td><RouterLink :to="`/versions/${v.id}`"><button class="sm">打开</button></RouterLink></td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="card">
      <h2>演示路径</h2>
      <p class="hint">
        1. 在「版本比较」选择 <code>V1.0 → V2.0</code> 查看树形差异（新增散热片、整流桥换代、用量变更）。<br>
        2. 打开 <code>V2.0</code> 详情：多级替代规则 <code>CAP-100→CAP-100B [1000,1999]</code>、
        <code>CAP-100B→CAP-100C [1500,2500]</code> 校验通过后可发布。<br>
        3. 打开 <code>V3.0</code> 详情：区间冲突 <code>[1500,2000]</code> 与替代环
        <code>IC-OLD↔IC-NEW</code> 会阻止发布并给出冲突路径。<br>
        4. 在「发料反查」输入序列号边界值 <code>999 / 1000 / 1499 / 1500 / 1999 / 2000</code>
        观察替代链变化；<code>1005 / 1006</code> 已发料，永远保持 V1.0 快照。
      </p>
    </div>
  </div>
</template>
