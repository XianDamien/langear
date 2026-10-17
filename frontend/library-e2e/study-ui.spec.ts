import { test, expect } from '@playwright/test'

test('复述 UI 使用 staging 真实课程，正常启动忽略旧 mock 开关', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('langear-use-mock', 'true'))
  await page.goto('/login?mock=true')
  await page.getByLabel('用户名', { exact: true }).fill('test')
  await page.getByLabel('密码', { exact: true }).fill('test123')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page).toHaveURL(/dashboard/)
  await page.getByRole('link', { name: '我的课程', exact: true }).click()
  const lessonId = await page.evaluate(async () => {
    const response = await fetch('/api/v1/my-courses/lessons', { headers: { Authorization: `Bearer ${localStorage.getItem('langear_access_token')}` } })
    return (await response.json()).data.lesson_ids[0]
  })
  expect(lessonId).toBeTruthy()
  await page.goto(`/study/${lessonId}`)
  await expect(page).toHaveURL(/\/study\/\d+/)
  await expect(page.getByTestId('study-session-view')).toBeVisible()
  await expect(page.getByTestId('study-task-nav')).toHaveCount(0)
  // Existing real attempts may restore this card directly to its answer side.
  await expect(page.getByTestId('card-front-container').or(page.getByTestId('card-back-container'))).toBeVisible()
  await expect(page.getByText('模拟模式 · 演示数据')).toHaveCount(0)
  if (await page.getByTestId('card-back-container').count()) {
    await expect(page.getByTestId('transcription-result')).toBeVisible()
    await expect(page.getByTestId('study-rating-bar')).toBeVisible()
  } else {
    await expect(page.getByRole('button', { name: '录音', exact: true })).toBeVisible()
  }
  await page.screenshot({ path: '/tmp/langear-real-retelling-ui.png', animations: 'disabled' })
  await page.setViewportSize({ width: 390, height: 600 })
  await expect(page.locator('#study-sidebar')).toHaveCount(0)
  await expect(page.getByRole('button', { name: '句子导航', exact: true })).toHaveCount(0)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})
