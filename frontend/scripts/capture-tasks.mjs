import puppeteer from 'puppeteer-core'
const browser = await puppeteer.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: 'new' })
const page = await browser.newPage()
await page.setViewport({ width: 1440, height: 1000 })
for (const theme of ['light', 'dark']) {
  await page.evaluateOnNewDocument((t) => localStorage.setItem('repovantage-theme', t), theme)
  await page.goto('http://localhost:5178/tasks', { waitUntil: 'networkidle0' })
  await new Promise((r) => setTimeout(r, 1600))
  await page.screenshot({ path: `docs/screenshots/${theme}/tasks.png`, fullPage: true })
}
await browser.close()
console.log('captured')
