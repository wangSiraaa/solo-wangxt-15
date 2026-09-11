<script setup>
// 发料解析树（递归）：展示某序列号下每个节点的 原物料→生效物料 与替代链
import { ref } from 'vue'

defineProps({
  node: { type: Object, required: true },
  depth: { type: Number, default: 0 },
})
const open = ref(true)
</script>

<template>
  <div class="tnode">
    <div
      class="trow"
      :class="{ substituted: node.substituted }"
      :style="{ paddingLeft: depth * 20 + 8 + 'px' }"
    >
      <span v-if="node.children && node.children.length" class="caret" @click="open = !open">
        {{ open ? '▾' : '▸' }}
      </span>
      <span v-else class="caret placeholder"></span>
      <template v-if="node.substituted">
        <span class="code"><s>{{ node.original.code }}</s></span>
        <span>→</span>
        <span class="code" style="color:#c2410c">{{ node.effective.code }}</span>
        <span class="name">{{ node.effective.name }}</span>
        <span class="chain">
          <span v-for="hop in node.chain" :key="hop.rule_id" class="hop"
                :title="`规则 #${hop.rule_id}：序列号 ${hop.serial_start} ~ ${hop.serial_end}`">
            {{ hop.from.code }}→{{ hop.to.code }} [{{ hop.serial_start }}-{{ hop.serial_end }}]
          </span>
        </span>
      </template>
      <template v-else>
        <span class="code">{{ node.original.code }}</span>
        <span class="name">{{ node.original.name }}</span>
      </template>
      <span class="qty">× {{ node.quantity }} {{ node.unit }}</span>
    </div>
    <div v-show="open">
      <ResolveTree
        v-for="(child, i) in node.children"
        :key="i"
        :node="child"
        :depth="depth + 1"
      />
    </div>
  </div>
</template>
