import type { Comparison, Coverage, Metrics } from '@/services/domain'

export const metricDefinitions: Array<{ key: keyof Metrics; label: string; meaning: string; window: string }> = [
  { key: 'stars', label: 'Stars · 星标', meaning: '累计关注量，不能代表代码质量或实际使用量。', window: '采集时点的累计值' },
  { key: 'forks', label: 'Forks · 派生', meaning: '仓库被派生的累计次数，不等于活跃贡献者人数。', window: '采集时点的累计值' },
  { key: 'daysSincePush', label: '距最近推送', meaning: '以采集时点计算；推送不一定是新版本发布。', window: '最近推送至采集时点，单位：天' },
  { key: 'ageDays', label: '仓库年龄', meaning: '从仓库创建到采集时点的天数；不同年龄项目需谨慎比较累计值。', window: '创建至采集时点，单位：天' },
  { key: 'commits90d', label: '提交数', meaning: '默认分支在窗口内采集到的提交数，不衡量代码变更规模。', window: '采集时点前 90 天' },
  { key: 'issuesClosed90d', label: '关闭 Issues', meaning: '窗口内关闭的议题数，不是问题解决率。', window: '采集时点前 90 天' },
  { key: 'prsMerged90d', label: '合并 PR', meaning: '窗口内合并的拉取请求数，不等于贡献者人数。', window: '采集时点前 90 天' },
  { key: 'releases365d', label: 'Release 数', meaning: '窗口内发布的 GitHub Release 数，不包含仅有 Git tag 的发布。', window: '采集时点前 365 天' },
]

const exact = (value: number) => new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 1 }).format(value)
const valid = (value: number | null | undefined): value is number => typeof value === 'number' && Number.isFinite(value)
export const activityKeys = ['commits90d', 'issuesClosed90d', 'prsMerged90d', 'releases365d'] as const

export function repositoryReadout(metrics: Metrics | null, coverage: Coverage, archived: boolean) {
  const stars = metrics?.stars
  const forks = metrics?.forks
  const pushed = metrics?.daysSincePush
  const activity = activityKeys.filter((key) => valid(metrics?.[key]))
  const activityFacts = [
    valid(metrics?.commits90d) ? `90 天提交 ${exact(metrics.commits90d)} 次` : null,
    valid(metrics?.prsMerged90d) ? `90 天合并 ${exact(metrics.prsMerged90d)} 个 PR` : null,
    valid(metrics?.issuesClosed90d) ? `90 天关闭 ${exact(metrics.issuesClosed90d)} 个 Issues` : null,
    valid(metrics?.releases365d) ? `一年发布 ${exact(metrics.releases365d)} 个 Release` : null,
  ].filter((fact): fact is string => fact !== null)
  return [
    { title: '有多少人关注？', fact: valid(stars) ? `${exact(stars)} 个 Stars${valid(forks) ? `，${exact(forks)} 次 Forks` : ''}` : '尚无可用的关注度数据', explanation: '这是累计关注与派生记录，不能据此判断质量、口碑或实际用户数量。' },
    { title: '最近有更新吗？', fact: valid(pushed) ? `采集时距最近推送 ${exact(pushed)} 天` : '最近推送时间未采集', explanation: archived ? '仓库已归档。评估是否使用前，先核对上游说明与替代维护渠道。' : '结合版本发布与项目说明阅读；一次推送不能证明持续维护。' },
    { title: '维护活动有哪些？', fact: activityFacts.length ? activityFacts.slice(0, 2).join('；') : '还不能判断近期活动', explanation: activity.length ? `${activity.length} / 4 项活动指标有可用值。${coverage === 'partial' ? '本次仅部分采集完成。' : ''}不同活动不合成为质量分数；缺失项不作为 0。` : '切换“活动与协作”查看已有结果；没有结果时再采集活动数据。' },
  ]
}

export function comparisonReadout(rows: Comparison['repositories'], key: keyof Metrics) {
  const values = rows.map((row) => ({ name: row.fullName, value: row.metrics[key] })).filter((row): row is { name: string; value: number } => valid(row.value))
  if (values.length < 2) return { count: values.length, headline: '有效值不足，暂不能比较差异', detail: '至少需要两个仓库的该项数据；缺失值不作为 0。' }
  const low = Math.min(...values.map((row) => row.value))
  const high = Math.max(...values.map((row) => row.value))
  const leaders = values.filter((row) => row.value === high)
  return {
    count: values.length,
    headline: low === high ? `所选仓库的该项数值相同：${exact(high)}` : `${leaders.length === 1 ? leaders[0]!.name : `${leaders.length} 个仓库并列`}的该项数值最高：${exact(high)}`,
    detail: `有效值范围 ${exact(low)}–${exact(high)}，相差 ${exact(high - low)}。${values.length < rows.length ? `${rows.length - values.length} 个仓库缺失该项数据，未参与计算。` : ''}数值大小不代表项目质量或适合程度。`,
  }
}

export function observationChange(points: Array<{ date: string; value: number }>) {
  const usable = points.filter((point) => valid(point.value))
  if (usable.length < 2) return null
  const first = usable[0]!
  const last = usable[usable.length - 1]!
  const change = last.value - first.value
  return { from: first.date, to: last.date, change, percent: first.value > 0 ? change / first.value * 100 : null }
}

export function correlationReading(coefficient: number | null, n: number, note: string | null) {
  if (!valid(coefficient)) return note || '有效配对不足或数据为常量，未形成可解释的相关系数。'
  return `在 ${n} 个有效配对中，两项指标${coefficient > 0 ? '呈同向排序关联' : coefficient < 0 ? '呈反向排序关联' : '未呈现单调排序关联'}。该结果只描述当前样本，不能推出因果关系。`
}

export function pValueLabel(value: number | null) {
  if (!valid(value)) return '—'
  return value < 0.001 ? '< 0.001' : value.toFixed(3)
}

export function fieldLabel(key: string) {
  const labels: Record<string, string> = { stars: 'Stars', forks: 'Forks', age_days: '仓库年龄', days_since_push: '距最近推送天数', language: '主要语言', pushed_at: '最近推送时间', collected_at: '采集时间', created_at: '仓库创建时间' }
  return labels[key] ?? key
}
