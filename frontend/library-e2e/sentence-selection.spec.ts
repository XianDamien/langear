import { test, expect } from '@playwright/test'

test('原课程按账号选择部分句子，刷新保留原名称且练习不包含其余句子', async ({ page }) => {
  await page.goto('/login')
  await page.getByLabel('用户名', { exact: true }).fill('test')
  await page.getByLabel('密码', { exact: true }).fill('test123')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page).toHaveURL(/dashboard/)
  const original = await page.evaluate(async () => {
    const headers = { Authorization: `Bearer ${localStorage.getItem('langear_access_token')}` }
    const read = async (path: string) => {
      const response = await fetch(`/api/v1${path}`, { headers })
      if (!response.ok) throw new Error(`Read failed: ${response.status}`)
      return (await response.json()).data
    }
    const tree = await read('/decks/tree')
    for (const source of tree.sources) for (const unit of source.units) for (const lesson of unit.lessons) {
      if (lesson.total_cards < 2) continue
      return { source, unit, lesson, lessons: (await read('/my-courses/lessons')).lesson_ids, scope: (await read(`/my-courses/lessons/${lesson.id}/cards`)).card_ids, cards: (await read(`/decks/${lesson.id}/cards`)).cards }
    }
    throw new Error('No original lesson available')
  })
  try {
    await page.getByRole('link', { name: '题库资源', exact: true }).click()
    // Sources are initially expanded; units are collapsed.
    await page.getByRole('button', { name: original.unit.title, exact: true }).first().click()
    const row = page.locator('div.mb-2').filter({ has: page.getByRole('button', { name: original.lesson.title, exact: true }) })
    await row.getByRole('button', { name: /^(加入|已加入)$/ }).click()
    let dialog = page.getByRole('dialog')
    await expect(dialog.getByRole('checkbox')).toHaveCount(original.cards.length)
    // Cancel must not write a scope.
    await dialog.getByRole('button', { name: '取消', exact: true }).click()
    await row.getByRole('button', { name: /^(加入|已加入)$/ }).click()
    dialog = page.getByRole('dialog')
    await expect(dialog.getByRole('checkbox')).toHaveCount(original.cards.length)
    for (const box of await dialog.getByRole('checkbox').all()) await box.uncheck()
    await dialog.getByRole('checkbox').nth(1).check()
    const saved = page.waitForResponse(r => r.url().endsWith(`/my-courses/lessons/${original.lesson.id}/cards`) && r.request().method() === 'PUT')
    await dialog.getByRole('button', { name: '加入所选内容', exact: true }).click()
    expect((await saved).status()).toBe(200)
    await page.reload()
    await page.getByRole('button', { name: original.unit.title, exact: true }).first().click()
    await row.getByRole('button', { name: '已加入', exact: true }).click()
    dialog = page.getByRole('dialog')
    await expect(dialog.getByRole('checkbox').nth(0)).not.toBeChecked()
    await expect(dialog.getByRole('checkbox').nth(1)).toBeChecked()
    await expect(dialog.getByLabel('新牌组名称')).toHaveCount(0)
    await dialog.getByRole('button', { name: '取消', exact: true }).click()
    await page.getByRole('link', { name: '我的课程', exact: true }).click()
    // The course retains its original hierarchy/name.
    const unitButton = page.getByRole('button', { name: original.unit.title, exact: true }).first()
    await unitButton.locator('xpath=../..').locator('svg').first().click()
    const myRow = page.locator('div.mb-2').filter({ has: page.getByRole('button', { name: original.lesson.title, exact: true }) })
    const session = page.waitForResponse(r => r.url().includes('/study/session?') && r.url().includes(`lesson_id=${original.lesson.id}`))
    await myRow.getByRole('button', { name: '开始', exact: true }).click()
    const data = (await (await session).json()).data
    // Daily limits may omit a selected card, but must never include another one.
    expect(data.cards.every((card: { id: number }) => card.id === original.cards[1].id)).toBe(true)
    expect(data.lesson_name).toBe(original.lesson.title)
    await expect(page.getByTestId('study-task-nav')).toHaveCount(0)
    await expect(page.getByRole('button', { name: '句子导航', exact: true })).toHaveCount(0)
    await page.screenshot({ path: '/tmp/langear-original-course-selected-sentence.png' })
  } finally {
    await page.evaluate(async ({ lesson, lessons, scope }) => {
      const headers = { 'Content-Type': 'application/json', Authorization: `Bearer ${localStorage.getItem('langear_access_token')}` }
      for (const [path, body] of [[`/my-courses/lessons/${lesson.id}/cards`, { card_ids: scope }], ['/my-courses/lessons', { lesson_ids: lessons }]] as const) {
        const response = await fetch(`/api/v1${path}`, { method: 'PUT', headers, body: JSON.stringify(body) })
        if (!response.ok) throw new Error(`Restore failed: ${response.status}`)
      }
    }, original)
  }
})
