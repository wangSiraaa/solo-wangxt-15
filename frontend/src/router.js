import { createRouter, createWebHashHistory } from 'vue-router'
import HomeView from './views/HomeView.vue'
import CompareView from './views/CompareView.vue'
import VersionDetailView from './views/VersionDetailView.vue'
import ResolveView from './views/ResolveView.vue'

// hash 路由：刷新/深链不需要后端额外配置
export const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', name: 'home', component: HomeView, meta: { title: '版本总览' } },
    { path: '/compare', name: 'compare', component: CompareView, meta: { title: '版本比较' } },
    { path: '/versions/:id', name: 'version', component: VersionDetailView, meta: { title: '版本详情' } },
    { path: '/resolve', name: 'resolve', component: ResolveView, meta: { title: '发料反查' } },
  ],
})
