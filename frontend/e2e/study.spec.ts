import { expect, test } from '@playwright/test'
import { installBrowserMocks } from './helpers/installBrowserMocks'

const transcript = 'The quick brown fox jumps over the lazy dog.'
const transcriptPattern = /The\s*quick\s*brown\s*fox\s*jumps\s*over\s*the\s*lazy\s*dog\./

async function completeFirstStudyCard(page: import('@playwright/test').Page) {
  await page.goto('/study/1001')

  await expect(page.getByTestId('study-session-view')).toBeVisible()
  await expect(page.getByTestId('study-lesson-title')).toContainText('Lesson 1')
  await expect(page.getByTestId('study-task-nav')).toHaveCount(0)
  await expect(page.getByTestId('card-front-container')).toBeVisible()
  const remaining = page.getByRole('status', { name: '剩余卡片' })
  await expect(remaining.locator('dt')).toHaveText(['未学习', '学习中', '待复习'])
  await expect(page.getByRole('progressbar', { name: '句子练习进度' })).toHaveCount(0)

  await page.getByTestId('record-toggle').click()
  await expect(page.getByTestId('record-toggle')).toContainText('停止')
  await expect(page.getByTestId('live-transcript')).toContainText(transcript)

  await page.getByTestId('record-toggle').click()
  await expect(page.getByTestId('record-toggle')).toContainText('录音')

  await page.getByTestId('flip-button').click()

  await expect(page.getByTestId('card-back-container')).toBeVisible()
  await expect(page.getByTestId('feedback-panel')).toContainText('AI 评测反馈')
}

test('核心学习链路可以在 Mock E2E 模式下完成评测并展示反馈', async ({ page }) => {
  await installBrowserMocks(page)
  await completeFirstStudyCard(page)

  await expect(page.getByTestId('feedback-panel')).toContainText('本句转写与原文一致', {
    timeout: 15_000,
  })
  await expect(page.getByTestId('transcription-result')).toContainText(transcriptPattern)
  await expect(page.getByRole('status', { name: '剩余卡片' })).toBeInViewport()
  await expect(page.getByRole('progressbar', { name: '句子练习进度' })).toHaveCount(0)
})


test('原文下方展开和收起中文，播放器与对应文本配对', async ({ page }) => {
  await installBrowserMocks(page)
  await completeFirstStudyCard(page)

  const original = page.getByTestId('original-row')
  const transcriptRow = page.getByTestId('transcript-row')
  await expect(original.getByRole('slider', { name: '原音频进度' })).toBeVisible()
  await expect(transcriptRow.getByRole('slider', { name: '我的录音进度' })).toBeVisible()
  await original.getByRole('button', { name: '显示中文' }).click()
  const translation = page.getByTestId('original-translation')
  await expect(translation).toBeVisible()
  const originalBounds = await page.getByTestId('original-text').boundingBox()
  const translationBounds = await translation.boundingBox()
  expect(translationBounds!.y).toBeGreaterThan(originalBounds!.y + originalBounds!.height)
  await original.getByRole('button', { name: '隐藏中文' }).click()
  await expect(translation).toHaveCount(0)

  await page.setViewportSize({ width: 390, height: 844 })
  await expect(original.getByRole('button', { name: '显示中文' })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})

test('演示音频可播放，刷新恢复反馈，第二张卡使用自己的转写', async ({ page }) => {
  await installBrowserMocks(page)
  await completeFirstStudyCard(page)
  await expect(page.getByTestId('feedback-panel')).toContainText('本句转写与原文一致')
  const audios = page.locator('[data-testid="transcription-result"] audio')
  await expect.poll(async () => audios.evaluateAll(elements => elements.every(element => {
    const audio = element as HTMLAudioElement
    return Number.isFinite(audio.duration) && audio.duration > 0
  }))).toBe(true)
  await page.getByRole('button', { name: '播放原音频', exact: true }).click()
  await expect.poll(async () => audios.nth(0).evaluate(element => !(element as HTMLAudioElement).paused)).toBe(true)
  await page.getByRole('button', { name: '播放我的录音', exact: true }).click()
  await expect.poll(async () => audios.evaluateAll(elements =>
    (elements[0] as HTMLAudioElement).paused && !(elements[1] as HTMLAudioElement).paused,
  )).toBe(true)
  await page.getByRole('slider', { name: '我的录音进度' }).fill('1')
  await expect.poll(async () => audios.nth(1).evaluate(element => (element as HTMLAudioElement).currentTime)).toBeGreaterThanOrEqual(1)

  await page.reload()
  await expect(page.getByTestId('feedback-panel')).toContainText('本句转写与原文一致')
  await expect(page.getByTestId('transcript-row')).toContainText(transcriptPattern)
  await expect.poll(async () => audios.nth(1).evaluate(element => (element as HTMLAudioElement).duration)).toBeGreaterThan(1)

  await page.getByRole('button', { name: '良好', exact: false }).click()
  await page.getByTestId('record-toggle').click()
  await expect(page.getByTestId('live-transcript')).toContainText('Learning a language requires practice.')
  await page.getByTestId('record-toggle').click()
  await page.getByTestId('flip-button').click()
  await expect(page.getByTestId('feedback-panel')).toContainText('转写中缺少「patience and」')
  await expect(page.getByTestId('transcript-row')).toContainText('Learning a language requires practice.')
  await expect(page.getByTestId('feedback-panel')).not.toContainText('extra seats')
})

test('无句子导航，评分栏在短屏和手机上保持可见', async ({ page }) => {
  await installBrowserMocks(page)
  await page.setViewportSize({ width: 1280, height: 650 })
  await completeFirstStudyCard(page)
  await expect(page.getByRole('status', { name: '剩余卡片' })).toBeInViewport()

  await expect(page.getByTestId('study-task-nav')).toHaveCount(0)
  const assertRatingVisible = async () => {
    await expect(page.getByRole('status', { name: '剩余卡片' })).toBeInViewport()
    const bounds = await page.getByTestId('study-rating-bar').boundingBox()
    expect(bounds!.y).toBeGreaterThanOrEqual(0)
    expect(bounds!.y + bounds!.height).toBeLessThanOrEqual(page.viewportSize()!.height)
    expect(await page.evaluate(() => document.documentElement.scrollHeight <= innerHeight)).toBe(true)
  }
  await assertRatingVisible()
  await page.getByTestId('study-card-content').evaluate(element => { element.scrollTop = element.scrollHeight })
  await assertRatingVisible()

  await page.setViewportSize({ width: 390, height: 600 })
  await assertRatingVisible()
  await expect(page.locator('#study-sidebar')).toHaveCount(0)
  await expect(page.getByRole('button', { name: '句子导航', exact: true })).toHaveCount(0)
  await expect(page.getByTestId('task-nav-item-2')).toHaveCount(0)
  await page.getByRole('button', { name: '良好', exact: false }).click()
  await expect(page.getByTestId('card-front-container')).toBeVisible()
  await expect(page.getByTestId('study-lesson-title')).toContainText('Lesson 1')
  await expect(page.getByRole('progressbar', { name: '句子练习进度' })).toHaveCount(0)
})
