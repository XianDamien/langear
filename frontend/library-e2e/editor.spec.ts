import { test, expect } from '@playwright/test'

test('原题库页添加牌组、混合卡片、失败重试、刷新与原导航', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  const deckName = `题库编辑验收 ${Date.now()}`
  let deckId = ''
  const noteIds: string[] = []
  page.on('response', async response => {
    if (response.request().method() === 'POST' && response.status() === 201 && response.url().endsWith('/content-api/v1/notes')) {
      const body = await response.json()
      noteIds.push(body.id)
    }
  })
  await page.goto('/login')
  await page.getByLabel('用户名', { exact: true }).fill('test')
  await page.getByLabel('密码', { exact: true }).fill('test123')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page).toHaveURL(/dashboard/)
  await page.getByRole('link', { name: '题库资源', exact: true }).click()
  await expect(page.getByRole('button', { name: '加入', exact: true }).first()).toBeVisible()
  try {
    await page.getByRole('button', { name: '添加牌组', exact: true }).click()
    let dialog = page.getByRole('dialog')
    await expect(dialog.getByRole('combobox')).toHaveCount(0)
    await dialog.getByLabel('新牌组名称').fill(deckName)
    const created = page.waitForResponse(r => r.url().endsWith('/content-api/v1/decks') && r.request().method() === 'POST')
    await dialog.getByRole('button', { name: '添加', exact: true }).click()
    deckId = (await (await created).json()).id
    const deck = page.locator('.personal-deck').filter({ hasText: deckName })
    await expect(deck).toBeVisible()
    await page.getByRole('button', { name: '添加卡片', exact: true }).click()
    dialog = page.getByRole('dialog')
    await expect(dialog.getByLabel('归属牌组')).toHaveValue(deckId)
    await dialog.getByLabel('单词', { exact: false }).fill('journey')
    await dialog.getByLabel('释义', { exact: false }).fill('旅程')
    await expect(dialog.locator('.template-chip')).toHaveText(['英译中'])
    await page.route('**/content-api/v1/notes', route => route.abort())
    await dialog.getByRole('button', { name: '添加', exact: true }).click()
    await expect(dialog.getByRole('alert')).toBeVisible()
    await expect(dialog.getByLabel('单词', { exact: false })).toHaveValue('journey')
    await page.unroute('**/content-api/v1/notes')
    await dialog.getByRole('button', { name: '添加', exact: true }).click()
    await expect(dialog).not.toBeVisible()
    await expect(deck.locator('.personal-card')).toHaveCount(1)
    await page.getByRole('button', { name: '添加卡片', exact: true }).click()
    dialog = page.getByRole('dialog')
    await dialog.getByLabel('卡片类型').selectOption('sentence_translation')
    await dialog.getByLabel('英文', { exact: false }).fill('Every journey begins with a single step.')
    await dialog.getByLabel('中文', { exact: false }).fill('千里之行，始于足下。')
    await expect(dialog.locator('.template-chip')).toHaveText(['翻译'])
    await dialog.getByRole('button', { name: '添加', exact: true }).click()
    await expect(deck.locator('.personal-card')).toHaveCount(2)
    for (const [key, label] of [
      ['vocabulary_chinese_to_english', '中译英'],
      ['sentence_retelling', '复述'],
      ['sentence_dictation', '听写'],
    ]) {
      await page.getByRole('button', { name: '添加卡片', exact: true }).click()
      dialog = page.getByRole('dialog')
      await expect(dialog.getByLabel('卡片类型').locator('option')).toHaveCount(5)
      await dialog.getByLabel('卡片类型').selectOption(key!)
      if (key!.startsWith('vocabulary')) {
        await dialog.getByLabel('单词', { exact: false }).fill('journey')
        await dialog.getByLabel('释义', { exact: false }).fill('旅程')
      } else {
        await dialog.getByLabel('英文', { exact: false }).fill('Every journey begins with a single step.')
        await expect(dialog.getByRole('button', { name: '添加', exact: true })).toBeDisabled()
        await expect(dialog.getByLabel('参考音频', { exact: false })).toHaveAttribute('required', '')
        await dialog.getByLabel('参考音频', { exact: false }).selectOption({ index: 1 })
      }
      await expect(dialog.locator('.template-chip')).toHaveText([label!])
      const saved = page.waitForResponse(r => r.url().endsWith('/content-api/v1/notes') && r.status() === 201)
      await dialog.getByRole('button', { name: '添加', exact: true }).click()
      const body = await (await saved).json()
      expect(body.cards).toHaveLength(1)
      expect(body.cards[0].card_template_key).toBe(key)
      await expect(dialog).not.toBeVisible()
    }
    await expect(deck.locator('.personal-card')).toHaveCount(5)
    await page.reload()
    await deck.getByRole('button').click()
    await expect(deck.locator('.personal-card')).toHaveCount(5)
    await page.screenshot({ path: '/tmp/langear-library-buttons-desktop.png', fullPage: false })
    await page.getByRole('button', { name: '添加牌组', exact: true }).click()
    dialog = page.getByRole('dialog')
    await dialog.getByLabel('新牌组名称').fill(deckName)
    await dialog.getByRole('button', { name: '添加', exact: true }).click()
    await expect(dialog.getByRole('alert')).toContainText('名称已存在')
    await dialog.getByRole('button', { name: '取消' }).click()
    await page.setViewportSize({ width: 390, height: 844 })
    await page.getByRole('button', { name: '添加卡片', exact: true }).click()
    await expect(page.getByRole('dialog').getByLabel('卡片类型')).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.screenshot({ path: '/tmp/langear-library-buttons-mobile.png' })
    await page.getByRole('dialog').getByRole('button', { name: '取消' }).click()
    await page.setViewportSize({ width: 1440, height: 1000 })
    for (const name of ['总览', '我的课程', '设置', '题库资源']) {
      await page.getByRole('link', { name, exact: true }).click()
      await expect(page).not.toHaveURL(/login/)
    }
    expect(errors).toEqual([])
  } finally {
    // Delete only the exact content created by this test, using normal confirmation APIs.
    await page.evaluate(async ({ noteIds, deckId }) => {
      const base = '/content-api/v1'
      const csrf = await (await fetch(`${base}/auth/csrf`)).json()
      const headers = { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf.csrf_token }
      for (const path of [...noteIds.map(id => `notes/${id}`), ...(deckId ? [`decks/${deckId}`] : [])]) {
        const preview = await fetch(`${base}/${path}/delete/preview`, { method: 'POST', headers })
        if (!preview.ok) throw new Error(`Cleanup preview failed: ${preview.status}`)
        const body = await preview.json()
        const removed = await fetch(`${base}/${path}/delete`, { method: 'POST', headers, body: JSON.stringify({ confirmation_token: body.confirmation_token }) })
        if (!removed.ok) throw new Error(`Cleanup failed: ${removed.status}`)
      }
    }, { noteIds, deckId })
  }
  await page.getByRole('button', { name: '退出', exact: true }).click()
  await expect(page).toHaveURL(/login/)
  expect((await page.request.get('/content-api/v1/auth/me')).status()).toBe(401)
})
