<script setup lang="ts">
import { ChevronRight, MoreHorizontal } from '@lucide/vue'
import type { Depth, Repository } from '@/services/domain'
import { metric, repoLetter } from '@/lib/format'
import StatusText from './StatusText.vue'

defineProps<{ repo: Repository; selectable?: boolean; selected?: boolean; disabled?: boolean; showMenu?: boolean }>()
defineEmits<{ select: [id: number]; refresh: [id: number, depth: Depth]; remove: [repo: Repository] }>()
</script>

<template>
  <div class="repository-line">
    <label v-if="selectable" class="row-check" :title="disabled ? '只有已采集数据的仓库可以比较' : '加入比较'">
      <input type="checkbox" :checked="selected" :disabled="disabled" :aria-label="`选择 ${repo.fullName} 进行比较`" @change="$emit('select', repo.repositoryId)" />
    </label>
    <div class="repo-mark">{{ repoLetter(repo) }}</div>
    <RouterLink class="repository-main" :to="`/repositories/${repo.repositoryId}`">
      <strong>{{ repo.fullName }}</strong><span>{{ repo.description || '暂无仓库简介' }}</span>
    </RouterLink>
    <span class="repo-language">{{ repo.language || '—' }}</span>
    <span class="repo-stars">{{ metric(repo.stars) }} <span>★</span></span>
    <StatusText :status="repo.analysisStatus" />
    <details v-if="showMenu" class="row-menu"><summary :aria-label="`${repo.fullName} 更多操作`"><MoreHorizontal :size="17" /></summary><div class="row-menu-items"><button @click="$emit('refresh', repo.repositoryId, 'basic')">基础刷新</button><button @click="$emit('refresh', repo.repositoryId, 'deep')">深度分析</button><button class="danger-menu" @click="$emit('remove', repo)">从个人库移除</button></div></details>
    <RouterLink class="row-open" :to="`/repositories/${repo.repositoryId}`" :aria-label="`查看 ${repo.fullName}`"><ChevronRight :size="17" /></RouterLink>
  </div>
</template>
