import { createRouter, createWebHistory } from 'vue-router'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: () => import('@/pages/OverviewPage.vue') },
    { path: '/repositories', component: () => import('@/pages/RepositoriesPage.vue') },
    { path: '/repositories/:repositoryId(\\d+)', component: () => import('@/pages/RepositoryDetailPage.vue') },
    { path: '/compare', component: () => import('@/pages/ComparePage.vue') },
    { path: '/research', component: () => import('@/pages/ResearchPage.vue') },
    { path: '/tasks', component: () => import('@/pages/TasksPage.vue') },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})
