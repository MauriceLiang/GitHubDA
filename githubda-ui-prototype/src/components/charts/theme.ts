/** Chart palette mirrors the CSS tokens in styles/theme.css. */
export interface ChartTheme {
  dark: boolean
  ink: string
  muted: string
  grid: string
  border: string
  panel: string
  soft: string
  series: string[]
  heat: string[]
}

export const chartTheme = (dark: boolean): ChartTheme => ({
  dark,
  ink: dark ? '#f5f5f5' : '#0a0a0a',
  muted: dark ? '#a1a1aa' : '#737373',
  grid: dark ? '#2b2b30' : '#ebebed',
  border: dark ? '#2a2a2e' : '#e5e5e5',
  panel: dark ? '#151518' : '#ffffff',
  soft: dark ? '#232327' : '#f2f2f3',
  series: dark ? ['#f5a183', '#f2c67d', '#f294c2', '#7fc6e8', '#93aeff'] : ['#e2683c', '#e5a03a', '#ce3f7c', '#2e8fcb', '#3b5bdb'],
  heat: dark ? ['#1b1f24', '#0e4429', '#006d32', '#26a641', '#39d353'] : ['#ebedf0', '#9be9a8', '#40c463', '#30a14e', '#216e39'],
})

export const MONO = "'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace"
export const fontFamily = "'Noto Sans SC', 'PingFang SC', 'Microsoft YaHei', system-ui, sans-serif"
