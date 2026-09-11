<script setup>
// BOM 快照树（递归）：展示某版本的完整清单结构
import { ref } from 'vue'

defineProps({
  node: { type: Object, required: true },
  depth: { type: Number, default: 0 },
})
const open = ref(true)
</script>

<template>
  <div class="tnode">
    <div class="trow" :style="{ paddingLeft: depth * 20 + 8 + 'px' }">
      <span v-if="node.children && node.children.length" class="caret" @click="open = !open">
        {{ open ? '▾' : '▸' }}
      </span>
      <span v-else class="caret placeholder"></span>
      <span class="code">{{ node.code }}</span>
      <span class="name">{{ node.name }}</span>
      <span class="path-tip" :title="node.path">{{ node.spec }}</span>
      <span class="qty">× {{ node.quantity }} {{ node.unit }}</span>
    </div>
    <div v-show="open">
      <BomTree
        v-for="(child, i) in node.children"
        :key="i"
        :node="child"
        :depth="depth + 1"
      />
    </div>
  </div>
</template>
