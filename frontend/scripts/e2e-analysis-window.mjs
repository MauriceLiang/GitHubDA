import assert from 'node:assert/strict'
import { access, mkdir, mkdtemp, readFile, readdir, writeFile } from 'node:fs/promises'
import { constants } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { setTimeout as delay } from 'node:timers/promises'
import puppeteer from 'puppeteer-core'

const base = new URL(process.env.BASE_URL ?? 'http://127.0.0.1:5173')
const chrome = process.env.CHROME_PATH
assert.ok(chrome, '必须设置 CHROME_PATH，指向独立测试 Chromium 可执行文件')
await access(chrome, constants.X_OK).catch(() => { throw new Error(`CHROME_PATH 不存在或不可执行：${chrome}`) })
const artifacts = process.env.E2E_ARTIFACT_DIR ? resolve(process.env.E2E_ARTIFACT_DIR) : await mkdtemp(join(tmpdir(), 'repovantage-window-e2e-'))
await mkdir(artifacts, { recursive: true })
const report = { baseUrl: base.href, dataMode: 'mock', scenarios: [], realGitHubApi: 'not_run' }

function parseCsv(text) {
  const rows = []
  let row = [], cell = '', quoted = false
  for (let i = 0; i < text.length; i++) {
    const c = text[i]
    if (c === '"') {
      if (quoted && text[i + 1] === '"') { cell += '"'; i++ }
      else quoted = !quoted
    } else if (!quoted && (c === ',' || c === '\n')) {
      row.push(cell.replace(/\r$/, '')); cell = ''
      if (c === '\n') { rows.push(row); row = [] }
    } else cell += c
  }
  if (cell || row.length) { row.push(cell.replace(/\r$/, '')); rows.push(row) }
  const header = rows.shift().map((name) => name.replace(/^\ufeff/, ''))
  return rows.map((values) => Object.fromEntries(header.map((name, i) => [name, values[i]])))
}

const browser = await puppeteer.launch({ executablePath: chrome, headless: true, args: process.platform === 'linux' ? ['--no-sandbox'] : [] })
try {
  for (const theme of ['light', 'dark']) {
    const context = await browser.createBrowserContext()
    const page = await context.newPage()
    page.setDefaultTimeout(15000)
    await page.setViewport({ width: 1440, height: 1000 })
    await page.evaluateOnNewDocument((value) => {
      localStorage.setItem('repovantage-theme', value)
      localStorage.setItem('repovantage-analysis-window', '90')
    }, theme)
    const errors = [], apiRequests = []
    page.on('pageerror', (error) => errors.push(error.message))
    page.on('request', (request) => {
      if (request.url().includes('/api/browser/') || request.url().startsWith('https://api.github.com/')) apiRequests.push(request.url())
    })
    const click = async (selector) => {
      await page.waitForSelector(selector, { visible: true })
      await page.click(selector)
    }
    const text = (selector) => page.$eval(selector, (element) => element.textContent ?? '')
    const select = async (group, value) => {
      const selector = `[data-testid="${group}"] button[data-value="${value}"]`
      await click(selector)
      await page.waitForFunction((s) => document.querySelector(s)?.getAttribute('aria-pressed') === 'true', {}, selector)
    }
    const loadedWindow = async (days) => page.waitForFunction((value) => {
      const element = document.querySelector('[data-testid="repository-analysis"]')
      return element?.getAttribute('data-window-days') === String(value)
        && Boolean(document.querySelector(value === 180 ? '[data-testid="analysis-window-unavailable"]' : '[data-testid="analysis-content"]'))
    }, {}, days)
    const layout = async (selector) => {
      const element = await page.waitForSelector(selector, { visible: true })
      await element.scrollIntoView()
      const result = await element.evaluate((node) => {
        const r = node.getBoundingClientRect()
        const top = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2)
        return { fits: r.x >= 0 && r.right <= innerWidth + 1 && r.y >= 0 && r.bottom <= innerHeight + 1, visible: Boolean(top && (node.contains(top) || top.contains(node))) }
      })
      assert.deepEqual(result, { fits: true, visible: true }, `${theme} 控件溢出或被遮挡：${selector}`)
    }
    const navigate = async (path) => { await click(`a[href="${path}"]`); await page.waitForFunction((p) => location.pathname === p, {}, path) }

    await page.goto(new URL('/repositories/steady-core/overview', base).href, { waitUntil: 'networkidle0' })
    assert.equal(await page.$eval('[data-testid="app"]', (element) => element.getAttribute('data-mode')), 'mock', '必须使用 VITE_DATA_MODE=mock 的独立服务器')
    assert.equal(await page.evaluate(() => document.documentElement.classList.contains('dark')), theme === 'dark')
    for (const days of [30, 90, 180]) {
      await select('analysis-window', days)
      await loadedWindow(days)
      assert.match(await text('[data-testid="analysis-window-summary"]'), new RegExp(`${days} 天`))
      if (days === 180) {
        assert.equal(await page.$('[data-testid="analysis-content"]'), null, '180 天缺失时不能继续展示 90 天图表')
        assert.match(await text('[data-testid="analysis-window-unavailable"]'), /180 天/)
      }
    }
    for (const [mode, label] of [['quick', '快速采集'], ['window', '完整窗口采集']]) {
      await select('collection-mode', mode)
      assert.ok((await text('[data-testid="collect-repository"]')).includes(`${label} · 180 天`))
      assert.match(await text('[data-testid="collection-description"]'), mode === 'quick' ? /页数预算/ : /全部分页/)
    }
    await navigate('/tasks')
    await page.waitForSelector('[data-testid="task-row"]')
    assert.equal((await page.$$('[data-task-id^="mock-refresh-"]')).length, 0, '切换窗口和模式不得自动创建任务')
    await navigate('/repositories')
    await navigate('/repositories/steady-core/overview')
    const days = theme === 'light' ? 180 : 30
    const mode = theme === 'light' ? 'window' : 'quick'
    await select('analysis-window', days)
    await loadedWindow(days)
    await select('collection-mode', mode)
    for (const selector of ['[data-testid="analysis-window"]', '[data-testid="collection-mode"]', '[data-testid="collect-repository"]']) await layout(selector)
    await click('[data-testid="collect-repository"]')
    await page.waitForSelector(`[data-task-id^="mock-refresh-"][data-scope-kind="${mode}"][data-window-days="${days}"]`)
    assert.equal((await page.$$('[data-task-id^="mock-refresh-"]')).length, 1)
    assert.match(await text('[data-task-id^="mock-refresh-"]'), new RegExp(`${days} 天`))

    await navigate('/repositories')
    for (const id of ['steady-core', 'grid-lite']) await click(`[data-testid="repository-select"][data-repository-id="${id}"]`)
    await click('[data-testid="compare-selected"]')
    for (const selected of [30, 90, 180]) {
      await select('comparison-window', selected)
      await page.waitForFunction((value) => {
        const element = document.querySelector('[data-testid="comparison-description"]')
        return element?.getAttribute('data-window-days') === String(value) && element.getAttribute('aria-busy') === 'false'
      }, {}, selected)
      assert.equal((await page.$$('[data-testid="comparison-row"]')).length, 2)
      if (selected === 180) {
        assert.equal((await page.$$('[data-testid="comparison-window-unavailable"]')).length, 2)
        assert.equal((await page.$$('[data-testid="comparison-row"][data-window-available="false"]')).length, 2)
      }
    }
    await select('comparison-mode', 'individual_periods')
    await page.waitForFunction(() => document.querySelector('[data-testid="comparison-description"]')?.getAttribute('data-mode') === 'individual_periods')
    assert.equal(await page.$eval('[data-testid="comparison-window"] button[aria-pressed="true"]', (element) => element.getAttribute('data-value')), '180')

    const session = await page.createCDPSession()
    for (const selected of [30, 180]) {
      await select('comparison-window', selected)
      await page.waitForFunction((value) => document.querySelector('[data-testid="comparison-description"]')?.getAttribute('data-window-days') === String(value), {}, selected)
      const dir = await mkdtemp(join(artifacts, `${theme}-${selected}-download-`))
      await session.send('Browser.setDownloadBehavior', { behavior: 'allow', browserContextId: context.id, downloadPath: dir })
      await click('[data-testid="export-comparison"]')
      let file
      for (let attempt = 0; attempt < 100 && !file; attempt++) {
        file = (await readdir(dir)).find((name) => name.endsWith('.csv'))
        if (!file) await delay(100)
      }
      assert.ok(file, '未下载到比较 CSV')
      const rows = parseCsv(await readFile(join(dir, file), 'utf8'))
      assert.equal(rows.length, 2)
      const uiRows = await page.$$eval('[data-testid="comparison-row"]', (elements) => elements.map((element) => [...element.querySelectorAll('td')].map((cell) => cell.textContent.trim())))
      for (let index = 0; index < rows.length; index++) {
        const row = rows[index], cells = uiRows[index]
        assert.equal(row.window_days, String(selected))
        assert.equal(row.comparison_mode, 'individual_periods')
        assert.equal(row.repository, cells[0])
        assert.equal(row.issue_p50_days === '' ? '—' : `${row.issue_p50_days} 天`, cells[2])
        assert.equal(row.pr_p50_days === '' ? '—' : `${row.pr_p50_days} 天`, cells[3])
        if (selected === 180) {
          assert.equal(row.window_available, 'false')
          assert.match(row.window_reason, /180 天/)
          assert.equal(row.weekly_commit_mean, '')
          assert.equal(cells[1], '—')
        } else if (row.weekly_commit_mean !== '') {
          assert.equal(Math.round(Number(row.weekly_commit_mean) * Number(row.complete_weeks)), Number(cells[1].replaceAll(',', '')))
        }
      }
    }
    await layout('[data-testid="comparison-window"]')
    await layout('[data-testid="comparison-window-unavailable"]')
    await page.screenshot({ path: join(artifacts, `${theme}-comparison.png`) })
    await page.setViewport({ width: 390, height: 844 })
    await page.goto(new URL('/repositories/steady-core/overview', base).href, { waitUntil: 'networkidle0' })
    await select('analysis-window', 180)
    await loadedWindow(180)
    for (const selector of ['[data-testid="analysis-window"]', '[data-testid="collect-repository"]', '[data-testid="analysis-window-unavailable"]']) await layout(selector)
    await page.screenshot({ path: join(artifacts, `${theme}-mobile.png`) })
    assert.deepEqual(apiRequests, [], 'Mock smoke 不应访问后端或真实 GitHub API')
    assert.deepEqual(errors, [], '浏览器出现未处理错误')
    report.scenarios.push({ theme, status: 'passed', collectionMode: mode, collectionDays: days, checks: ['analysis-windows', 'no-automatic-task', 'collection-scope', 'comparison-windows', 'mode-preserves-window', 'csv-30-180', 'layout-desktop-mobile'] })
    await context.close()
    console.log(`PASS ${theme}: analysis, collection, comparison, CSV, layout`)
  }
} finally {
  await writeFile(join(artifacts, 'report.json'), JSON.stringify(report, null, 2) + '\n')
  await browser.close()
  console.log(`Artifacts: ${artifacts}`)
}
