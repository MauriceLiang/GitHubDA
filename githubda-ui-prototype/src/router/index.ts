import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'overview', component: () => import('@/pages/Overview/OverviewPage.vue'), meta: { crumb: '工作台', title: '总览', nav: 'overview' } },
    { path: '/repositories', name: 'repositories', component: () => import('@/pages/Repositories/RepositoriesPage.vue'), meta: { crumb: '工作台', title: '仓库', nav: 'repositories' } },
    { path: '/repositories/:id/:tab?', name: 'repository', component: () => import('@/pages/RepositoryAnalysis/RepositoryAnalysisPage.vue'), meta: { crumb: '仓库', title: '仓库分析', nav: 'repositories' } },
    { path: '/compare', name: 'compare', component: () => import('@/pages/Comparison/ComparisonPage.vue'), meta: { crumb: '工作台', title: '项目比较', nav: 'compare' } },
    { path: '/research', name: 'research', component: () => import('@/pages/Research/ResearchPage.vue'), meta: { crumb: '工作台', title: '研究分析', nav: 'research' } },
    { path: '/settings', name: 'settings', component: () => import('@/pages/Settings/SettingsPage.vue'), meta: { crumb: '工作台', title: '设置', nav: 'settings' } },
    { path: '/tasks', name: 'tasks', component: () => import('@/pages/Tasks/TasksPage.vue'), meta: { crumb: '工作台', title: '任务', nav: 'repositories' } },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
  scrollBehavior: () => ({ top: 0 }),
})

router.afterEach((to) => {
  const title = to.meta.title ?? ''
  document.title = title ? `${title} · GitHubDA` : 'GitHubDA · 开源项目数据分析'
})

export default router
