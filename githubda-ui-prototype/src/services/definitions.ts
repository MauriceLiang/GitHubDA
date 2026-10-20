import type { DefinitionEntry } from './types'

/** Human-readable metric definitions shown in the 数据与口径 drawer. */
export const DEFINITIONS: Record<string, DefinitionEntry> = {
  M01: {
    metricId: 'M01',
    title: '每周 Commit 数',
    definition: '默认分支提交事件按周聚合，按提交 SHA 去重；窗口包含起点、不包含终点，时区 UTC。',
    source: 'GitHub Commits API（默认分支）',
    limitation: '不包含其他分支；未完成当周单独标注，不参与前后窗口对比。',
  },
  M03: {
    metricId: 'M03',
    title: '活跃作者',
    definition: '时间窗口内可可靠识别的作者身份去重；机器人单独标记，匿名身份不合并为多位作者。',
    source: 'Commit 作者身份',
    limitation: '身份解析失败时只说明数量，不推断人数。',
  },
  M04: {
    metricId: 'M04',
    title: 'Issue 新增与关闭',
    definition: '按 created_at / closed_at 所在周分别计数；同一周的新增与关闭不是同一批记录。',
    source: 'GitHub Issues API（排除 Pull Request 类型）',
    limitation: '更新时间过滤不能替代创建/关闭事件时间过滤。',
  },
  M06: {
    metricId: 'M06',
    title: 'Issue 关闭耗时',
    definition: '对窗口内关闭的 Issue 计算 closed_at − created_at，展示 P50 / P75 / P90 与有效样本 n。',
    source: 'GitHub Issues API',
    limitation: '重新打开只计最后一次关闭；缺少 closed_at 的记录不参与分位数。',
  },
  M08: {
    metricId: 'M08',
    title: 'PR 新建与合并',
    definition: '按 created_at / merged_at 分别计入周；合并数不等于合并率。',
    source: 'GitHub Pull Requests API',
    limitation: '合并耗时需覆盖跨窗口创建的 PR；未采集完整时不输出权威结论。',
  },
  M14: {
    metricId: 'M14',
    title: '数据完整度',
    definition: '逐模块记录覆盖、分页截断、错误、有效样本数与采集时间；未知不等于零。',
    source: '采集任务元数据',
    limitation: '部分完成不能当作全部成功。',
  },
}
