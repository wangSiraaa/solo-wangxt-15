<script setup>
import { RouterLink, RouterView } from 'vue-router'
</script>

<template>
  <div class="layout">
    <header class="topbar">
      <div class="brand">
        <span class="logo">△</span>
        <div>
          <h1>变更工作台</h1>
          <p>替代料生效边界 · BOM 版本管理</p>
        </div>
      </div>
      <nav>
        <RouterLink to="/">版本总览</RouterLink>
        <RouterLink to="/compare">版本比较</RouterLink>
        <RouterLink to="/resolve">发料反查</RouterLink>
      </nav>
    </header>
    <main>
      <RouterView />
    </main>
  </div>
</template>
