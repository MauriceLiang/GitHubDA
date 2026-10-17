import type { AnalysisStatus, Coverage, Repository, TaskStatus } from '@/services/domain'

export function metric(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return '—'
  return new Intl.NumberFormat('zh-CN', { notation: value >= 10000 ? 'compact' : 'standard', maximumFractionDigits: 1 }).format(value)
}

export function preciseMetric(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return '—'
  return new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 3 }).format(value)
}

export function dateTime(value: string | null | undefined) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }).format(date)
}

export function fullDate(value: string | null | undefined) {
  if (!value || Number.isNaN(new Date(value).getTime())) return '尚无记录'
  return new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date(value))
}

const taskLabels: Record<TaskStatus, string> = { queued: '排队中', running: '运行中', succeeded: '已完成', partial: '部分完成', failed: '失败', cancelled: '已取消' }
const analysisLabels: Record<AnalysisStatus, string> = { not_started: '尚未分析', queued: '排队中', processing: '分析中', completed: '已完成', partial: '部分完成', failed: '失败' }
const coverageLabels: Record<Coverage, string> = { complete: '完整覆盖', partial: '部分覆盖', not_collected: '未采集', unknown: '覆盖未知' }
export const taskLabel = (status: TaskStatus) => taskLabels[status]
export const analysisLabel = (status: AnalysisStatus) => analysisLabels[status]
export const coverageLabel = (coverage: Coverage) => coverageLabels[coverage]
export const repoLetter = (repo: Repository) => repo.fullName.split('/').at(-1)?.slice(0, 1).toLocaleUpperCase() ?? 'G'

export function download(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url; link.download = name; link.click()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}
