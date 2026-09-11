<script setup>
// 版本比较差异树（递归）：added/removed/changed 高亮，含变更的子树默认展开
import { ref } from 'vue'

const props = defineProps({
  node: { type: Object, required: true },
  depth: { type: Number, default: 0 },
})
const open = ref(props.node.status !== 'unchanged' || props.node.has_descendant_change)
const statusText = { added: '新增', removed: '删除', changed: '变更' }
</script>

<template>
  <div class="tnode">
    <div class="trow" :class="node.status" :style="{ paddingLeft: depth * 20 + 8 + 'px' }">
      <span v-if="node.children && node.children.length" class="caret" @click="open = !open">
        {{ open ? '▾' : '▸' }}
      </span>
      <span v-else class="caret placeholder"></span>
      <span class="code">{{ node.code }}</span>
      <span class="name">{{ node.name }}</span>
      <span class="badge" v-if="statusText[node.status]" :class="node.status">
        {{ statusText[node.status] }}
      </span>
      <span class="qty">
        <template v-if="node.status === 'changed'">
          <s>{{ node.quantity_from }}</s> → <b>{{ node.quantity_to }}</b>
        </template>
        <template v-else>× {{ node.quantity }}</template>
      </span>
    </div>
    <div v-show="open">
      <DiffTree
        v-for="(child, i) in node.children"
        :key="i"
        :node="child"
        :depth="depth + 1"
      />
    </div>
  </div>
</template>
