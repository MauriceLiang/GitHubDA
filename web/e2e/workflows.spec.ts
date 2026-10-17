import { expect, test } from '@playwright/test'

test.beforeEach(async ({ page }) => { await page.goto('/') })

test('overview adds a repository and opens its detail', async ({ page }) => {
  await page.getByRole('textbox', { name: '仓库地址' }).first().fill('example/new-project')
  await page.getByRole('button', { name: '开始分析' }).first().click()
  await expect(page).toHaveURL(/\/repositories\/20\d+/)
  await expect(page.getByText('排队中')).toBeVisible()
})

test('a duplicate repository does not create another task', async ({ page }) => {
  await page.getByRole('textbox', { name: '仓库地址' }).first().fill('vuejs/core')
  await page.getByRole('button', { name: '开始分析' }).first().click()
  await expect(page).toHaveURL(/\/repositories\/101$/)
  await page.goto('/tasks')
  await expect(page.getByText('vuejs/core')).toHaveCount(0)
})

test('selection carries into comparison and exports a CSV', async ({ page }) => {
  await page.goto('/repositories?tab=saved')
  await page.getByRole('checkbox', { name: '选择 vuejs/core 进行比较' }).check()
  await page.getByRole('checkbox', { name: '选择 facebook/react 进行比较' }).check()
  await page.getByRole('button', { name: '比较所选' }).click()
  await expect(page).toHaveURL(/\/compare$/)
  await expect(page.getByRole('heading', { name: '仓库比较' })).toBeVisible()
  await expect(page.getByRole('table')).toBeVisible()
  const download = page.waitForEvent('download')
  await page.getByRole('button', { name: '导出比较' }).click()
  await expect(download).resolves.toBeTruthy()
})

test('research switches to an empty sample without drawing fake statistics', async ({ page }) => {
  await page.goto('/research')
  await page.getByRole('combobox', { name: '选择研究数据集' }).selectOption('oss-empty')
  await expect(page.getByText('当前研究样本为空')).toBeVisible()
  await expect(page.getByRole('img', { name: /分组的样本数量/ })).toHaveCount(0)
})

test('failed task can be retried while retaining its history', async ({ page }) => {
  await page.goto('/tasks')
  await page.getByRole('button', { name: /shadcn-ui\/ui/ }).click()
  await page.getByRole('button', { name: '重新执行' }).click()
  await expect(page.getByText('已创建新的重试任务')).toBeVisible()
  await expect(page.getByText('重新排队中')).toBeVisible()
})

test('theme choice survives a page reload', async ({ page }) => {
  await page.getByRole('button', { name: '切换深色主题' }).click()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
  await page.reload()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
})

test('mobile navigation opens and closes without page overflow', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.getByRole('button', { name: '打开导航' }).click()
  await page.getByRole('link', { name: '任务' }).click()
  await expect(page).toHaveURL(/\/tasks$/)
  const width = await page.locator('body').evaluate((element) => element.scrollWidth)
  expect(width).toBeLessThanOrEqual(390)
})
