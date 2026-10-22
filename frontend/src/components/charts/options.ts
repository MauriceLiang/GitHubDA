import type { EChartsOption } from 'echarts'
import type { HistogramBucket, NamedSeries, ReleaseRecord, ResearchScatterPoint, TimePoint } from '@/services/types'
import { fontFamily, MONO, type ChartTheme } from './theme'

const mmdd = (iso: string) => iso.slice(5)
const tip = (t: ChartTheme) => ({
  backgroundColor: t.panel,
  borderColor: t.border,
  borderWidth: 1,
  padding: [9, 11] as [number, number],
  textStyle: { color: t.ink, fontSize: 11.5, fontFamily },
  extraCssText: `border-radius:8px;box-shadow:${t.dark ? '0 8px 24px rgba(0,0,0,.5)' : '0 6px 18px rgba(0,0,0,.12)'};`,
})
const axis = (t: ChartTheme) => ({
  axisLine: { lineStyle: { color: t.border } },
  axisTick: { show: false },
  axisLabel: { color: t.muted, fontSize: 10, fontFamily: MONO },
  splitLine: { lineStyle: { color: t.grid } },
})

export function timeSeriesOption(points: TimePoint[], unit: string, color: string, t: ChartTheme, dense = false): EChartsOption {
  return {
    animation: false,
    grid: { left: 44, right: 12, top: 16, bottom: 26 },
    tooltip: {
      ...tip(t),
      trigger: 'axis',
      axisPointer: { type: 'line', lineStyle: { color: t.border, width: 1 } },
      formatter: (params: unknown) => {
        const p = (params as { axisValue: string; dataIndex: number; value: number | null }[])[0]
        const point = points[p.dataIndex]
        const observed = point?.value === null && point.observedValue != null
        const value = observed ? point.observedValue : p.value
        const note = observed ? `<div style="color:${t.ink};font-size:10px;margin-top:3px">仅显示已观察数量，覆盖不完整</div>` : ''
        return `<div style="color:${t.muted};font-size:10.5px;font-family:${MONO};margin-bottom:3px">${p.axisValue}</div><b>${value ?? '未覆盖'}</b> ${value === null ? '' : unit}${note}`
      },
    },
    xAxis: { type: 'category', data: points.map((p) => mmdd(p.date)), ...axis(t), axisLine: { lineStyle: { color: t.border } }, splitLine: { show: false } },
    yAxis: { type: 'value', ...axis(t), axisLine: { show: false } },
    series: [{
      type: dense ? 'line' : 'bar',
      data: points.map((p) => ({
        value: p.value ?? p.observedValue ?? null,
        ...(p.value === null && p.observedValue != null ? { itemStyle: { opacity: 0.55 } } : {}),
      })),
      itemStyle: { color, borderRadius: dense ? undefined : [3, 3, 0, 0] },
      lineStyle: { color, width: 2 },
      symbol: 'circle', symbolSize: 4, showSymbol: false,
      areaStyle: dense ? { opacity: 0.12, color } : undefined,
      emphasis: { itemStyle: { color } },
    }],
  }
}

export function groupedOption(series: NamedSeries[], unit: string, colors: string[], t: ChartTheme, legend = true, compact = false): EChartsOption {
  const dates = series[0]?.points.map((p) => p.date) ?? []
  return {
    animation: false,
    grid: { left: compact ? 10 : 44, right: 12, top: 12, bottom: legend ? 46 : 26 },
    legend: legend ? {
      bottom: 0, left: 0, icon: 'roundRect', itemWidth: 8, itemHeight: 8, itemGap: 16,
      textStyle: { color: t.muted, fontSize: 11, fontFamily }, selectedMode: true,
    } : undefined,
    tooltip: {
      ...tip(t), trigger: 'axis', axisPointer: { type: 'line', lineStyle: { color: t.border, width: 1 } },
      formatter: (params: unknown) => {
        const rows = params as { axisValue: string; dataIndex: number; seriesName: string; value: number | null; color: string }[]
        return `<div style="color:${t.muted};font-size:10.5px;font-family:${MONO};margin-bottom:4px">${rows[0]?.axisValue}</div>` +
          rows.map((r) => {
            const point = series.find((item) => item.label === r.seriesName)?.points[r.dataIndex]
            const observed = point?.value === null && point.observedValue != null
            const value = observed ? point.observedValue : r.value
            return `<div style="display:flex;justify-content:space-between;gap:16px"><span><i style="display:inline-block;width:8px;height:8px;border-radius:2px;background:${r.color};margin-right:6px"></i>${r.seriesName}</span><b>${value === null ? '未覆盖' : `${value} ${unit}`}</b></div>${observed ? `<div style="color:${t.ink};font-size:10px;margin:2px 0 4px 14px">仅显示已观察数量，覆盖不完整</div>` : ''}`
          }).join('')
      },
    },
    xAxis: { type: 'category', data: dates.map(mmdd), ...axis(t), splitLine: { show: false } },
    yAxis: compact
      ? { type: 'value', show: false }
      : { type: 'value', ...axis(t), axisLine: { show: false } },
    series: series.map((s, i) => ({
      name: s.label, type: 'bar', barGap: '12%', barMaxWidth: 12,
      data: s.points.map((p) => ({
        value: p.value ?? p.observedValue ?? null,
        ...(p.value === null && p.observedValue != null ? { itemStyle: { opacity: 0.55 } } : {}),
      })),
      itemStyle: { color: colors[i] ?? t.series[i], borderRadius: [2, 2, 0, 0] },
    })),
  }
}

export function histogramOption(buckets: HistogramBucket[], color: string, t: ChartTheme, unit = '条记录'): EChartsOption {
  return {
    animation: false,
    grid: { left: 40, right: 12, top: 22, bottom: 30 },
    tooltip: {
      ...tip(t), trigger: 'axis', axisPointer: { type: 'line', lineStyle: { color: t.border, width: 1 } },
      formatter: (params: unknown) => {
        const p = (params as { axisValue: string; value: number }[])[0]
        return `<div style="color:${t.muted};font-size:10.5px;margin-bottom:3px">${p.axisValue}</div><b>${p.value}</b> ${unit}`
      },
    },
    xAxis: { type: 'category', data: buckets.map((b) => b.label), ...axis(t), splitLine: { show: false }, axisLabel: { color: t.muted, fontSize: 10, fontFamily } },
    yAxis: { type: 'value', ...axis(t), axisLine: { show: false } },
    series: [{
      type: 'bar', barMaxWidth: 46,
      data: buckets.map((b) => b.count),
      itemStyle: { color, borderRadius: [3, 3, 0, 0] },
      label: { show: true, position: 'top', color: t.muted, fontSize: 10, fontFamily: MONO },
    }],
  }
}

export function timelineOption(releases: ReleaseRecord[], t: ChartTheme, compact = false): EChartsOption {
  const formal = releases.filter((r) => !r.prerelease)
  const pre = releases.filter((r) => r.prerelease)
  const releaseTimes = releases.map((release) => Date.parse(release.publishedAt)).filter(Number.isFinite)
  const earliest = Math.min(...releaseTimes)
  const latest = Math.max(...releaseTimes)
  const span = latest - earliest
  const start = span > 90 * 24 * 60 * 60 * 1000 ? Math.max(0, (latest - 90 * 24 * 60 * 60 * 1000 - earliest) / span * 100) : 0
  const releasesByDate = new Map<string, ReleaseRecord[]>()
  for (const release of releases) {
    const date = release.publishedAt.slice(0, 10)
    releasesByDate.set(date, [...(releasesByDate.get(date) ?? []), release])
  }
  const verticalOffset = new Map<ReleaseRecord, number>()
  for (const sameDay of releasesByDate.values()) {
    const step = Math.min(0.18, 1.3 / Math.max(1, sameDay.length - 1))
    sameDay.forEach((release, index) => verticalOffset.set(release, (index - (sameDay.length - 1) / 2) * step))
  }
  const data = (rows: ReleaseRecord[]) => rows.map((r) => ({ name: r.tag, value: [r.publishedAt, 1 + (verticalOffset.get(r) ?? 0)], itemStyle: { color: r.prerelease ? t.panel : t.series[2], borderColor: r.prerelease ? t.series[3] : t.series[2], borderWidth: 2 } }))
  return {
    animation: false,
    grid: { left: 20, right: 20, top: 22, bottom: compact ? 28 : 50 },
    tooltip: {
      ...tip(t),
      trigger: 'item',
      formatter: (params: unknown) => {
        const p = (Array.isArray(params) ? params[0] : params) as { name?: string; seriesName?: string; value?: [string | number, number] } | undefined
        if (!p) return ''
        const escape = (value: string) => value.replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char]!)
        const date = String(p.value?.[0] ?? '').slice(0, 10)
        return `<div style="font-family:${MONO};font-size:11px">${escape(p.name ?? 'Release')}</div><div style="color:${t.ink};font-size:11px;margin-top:2px">${escape(date)} · ${escape(p.seriesName ?? '')}</div>`
      },
    },
    xAxis: {
      type: 'time', ...axis(t), splitLine: { show: false },
      splitNumber: 5,
      axisLabel: {
        show: !compact,
        hideOverlap: true,
        color: t.ink,
        formatter: (value: number) => {
          const date = new Date(value)
          return `${String(date.getUTCMonth() + 1).padStart(2, '0')}-${String(date.getUTCDate()).padStart(2, '0')}`
        },
      },
      axisTick: { show: !compact },
    },
    yAxis: { type: 'value', min: 0, max: 2, show: false },
    dataZoom: compact || releases.length < 2 ? undefined : [
      { type: 'inside', xAxisIndex: 0, filterMode: 'none', start, end: 100, zoomOnMouseWheel: true, moveOnMouseWheel: true, moveOnMouseMove: true },
      {
        type: 'slider', xAxisIndex: 0, filterMode: 'none', start, end: 100,
        height: 14, bottom: 1, showDetail: false, showDataShadow: false, brushSelect: false,
        borderColor: t.border, backgroundColor: t.soft,
        fillerColor: t.dark ? 'rgba(242,148,194,.2)' : 'rgba(206,63,124,.16)',
        handleStyle: { color: t.series[2], borderColor: t.border },
      },
    ],
    series: [
      { name: '正式发布', type: 'scatter', symbolSize: compact ? 9 : 11, data: data(formal), emphasis: { scale: true }, label: { show: !compact && formal.length <= 8, position: 'top', formatter: (p: { name: string }) => p.name, color: t.muted, fontSize: 9.5, fontFamily: MONO } },
      { name: '预发布', type: 'scatter', symbolSize: compact ? 8 : 10, data: data(pre), emphasis: { scale: true } },
    ],
  }
}

export function comparisonOption(entries: { label: string; color: string; points: TimePoint[] }[], t: ChartTheme): EChartsOption {
  const dates = [...new Set(entries.flatMap((entry) => entry.points.map((point) => point.date)))].sort()
  return {
    animation: false,
    grid: { left: 44, right: 12, top: 12, bottom: 46 },
    legend: { bottom: 0, left: 0, icon: 'roundRect', itemWidth: 8, itemHeight: 8, itemGap: 16, textStyle: { color: t.muted, fontSize: 11, fontFamily } },
    tooltip: {
      ...tip(t), trigger: 'axis',
      formatter: (params: unknown) => {
        const rows = params as { axisValue: string; seriesName: string; value: number; color: string }[]
        return `<div style="color:${t.muted};font-size:10.5px;font-family:${MONO};margin-bottom:4px">${rows[0]?.axisValue}</div>` +
          rows.filter((r) => r.value != null).map((r) => `<div style="display:flex;justify-content:space-between;gap:16px"><span><i style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${r.color};margin-right:6px"></i>${r.seriesName}</span><b>${r.value}</b></div>`).join('')
      },
    },
    xAxis: { type: 'category', data: dates.map(mmdd), ...axis(t), splitLine: { show: false } },
    yAxis: { type: 'value', ...axis(t), axisLine: { show: false } },
    series: entries.map((e) => {
      const map = new Map(e.points.map((p) => [p.date, p.value]))
      return {
        name: e.label, type: 'line', connectNulls: false, symbol: 'circle', symbolSize: 4,
        data: dates.map((d) => map.get(d) ?? null),
        lineStyle: { color: e.color, width: 2 }, itemStyle: { color: e.color },
      }
    }),
  }
}

export function scatterOption(points: ResearchScatterPoint[], groups: string[], colors: string[], t: ChartTheme): EChartsOption {
  return {
    animation: false,
    grid: { left: 44, right: 16, top: 16, bottom: 46 },
    legend: { bottom: 0, left: 0, icon: 'circle', itemWidth: 8, itemHeight: 8, itemGap: 16, textStyle: { color: t.muted, fontSize: 11, fontFamily } },
    tooltip: {
      ...tip(t),
      formatter: (params: unknown) => {
        const p = (params as { data: { name: string; value: number[] } }[])[0]
        return `<div style="font-family:${MONO};font-size:11px">${p.data.name}</div><div style="color:${t.muted};font-size:11px;margin-top:3px">Issue 关闭中位数 ${p.data.value[0]} 天</div><div style="font-size:11px">PR 合并中位数 ${p.data.value[1]} 天</div>`
      },
    },
    xAxis: { type: 'value', name: 'Issue 关闭天数', nameTextStyle: { color: t.muted, fontSize: 10 }, ...axis(t) },
    yAxis: { type: 'value', name: 'PR 合并天数', nameTextStyle: { color: t.muted, fontSize: 10 }, ...axis(t), axisLine: { show: false } },
    series: groups.map((g, i) => ({
      name: g, type: 'scatter', symbolSize: 7,
      data: points.filter((p) => p.group === g).map((p) => ({ name: p.repository, value: [p.issueCloseDays, p.prMergeDays] })),
      itemStyle: { color: colors[i] ?? t.series[i], opacity: 0.8 },
    })),
  }
}

export function calendarOption(points: TimePoint[], t: ChartTheme): EChartsOption {
  const max = Math.max(...points.flatMap((p) => p.value === null ? [] : [p.value]), 1)
  const start = points[0]?.date ?? ''
  const end = points[points.length - 1]?.date ?? ''
  return {
    animation: false,
    tooltip: {
      ...tip(t),
      formatter: (params: unknown) => {
        const p = (params as { value: [string, number] }[])[0]
        return `<div style="font-family:${MONO};font-size:11px">${p.value[0]}</div><div style="font-size:11px;margin-top:2px">${p.value[1]} 次提交</div>`
      },
    },
    visualMap: { show: false, min: 0, max, inRange: { color: t.heat } },
    calendar: {
      range: [start, end], left: 24, right: 8, top: 10, bottom: 12,
      cellSize: ['auto', 14], splitLine: { show: false },
      itemStyle: { color: t.panel, borderColor: t.panel, borderWidth: 2 },
      dayLabel: { color: t.muted, fontSize: 9, nameMap: ['日', '一', '二', '三', '四', '五', '六'] },
      monthLabel: { show: false },
      yearLabel: { show: false },
    },
    series: [{
      type: 'heatmap', coordinateSystem: 'calendar',
      data: points.flatMap((p) => p.value === null ? [] : [[p.date, p.value]]),
      itemStyle: { borderRadius: 2, borderColor: t.panel, borderWidth: 2 },
    }],
  }
}
