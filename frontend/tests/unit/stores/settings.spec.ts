import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useSettingsStore } from '@/stores/settings'
import { fetchSettings, saveSettings } from '@/services/api/settings'
import { ElMessage } from 'element-plus'

vi.mock('@/services/api/settings', () => ({ fetchSettings: vi.fn(), saveSettings: vi.fn() }))
vi.mock('element-plus', () => ({ ElMessage: { success: vi.fn() } }))

const values = {
  desiredRetention: 0.91, learningSteps: '1,15', relearningSteps: '15',
  maximumInterval: 1200, defaultSourceScope: '1',
}

describe('settings persistence feedback', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('loads persisted settings and applies the saved response', async () => {
    vi.mocked(fetchSettings).mockResolvedValue({ data: values } as Awaited<ReturnType<typeof fetchSettings>>)
    vi.mocked(saveSettings).mockResolvedValue({ data: { ...values, maximumInterval: 900 } } as Awaited<ReturnType<typeof saveSettings>>)
    const store = useSettingsStore()
    await store.load()
    expect(store.maximumInterval).toBe(1200)
    expect(await store.save()).toBe(true)
    expect(store.maximumInterval).toBe(900)
    expect(ElMessage.success).toHaveBeenCalledTimes(1)
  })

  it('blocks saving when initial settings could not load', async () => {
    vi.mocked(fetchSettings).mockRejectedValue(new Error('unavailable'))
    const store = useSettingsStore()
    await store.load()
    expect(store.loadError).toContain('加载失败')
    expect(await store.save()).toBe(false)
    expect(saveSettings).not.toHaveBeenCalled()
  })

  it('shows save failures without reporting success', async () => {
    vi.mocked(saveSettings).mockRejectedValue(new Error('保存请求失败'))
    const store = useSettingsStore()
    expect(await store.save()).toBe(false)
    expect(store.saveError).toBe('保存请求失败')
    expect(store.saving).toBe(false)
    expect(ElMessage.success).not.toHaveBeenCalled()
  })

  it('rejects an unscoped response when loading a deck', async () => {
    vi.mocked(fetchSettings).mockResolvedValue({ data: values } as Awaited<ReturnType<typeof fetchSettings>>)
    const store = useSettingsStore()
    await store.load(18)
    expect(store.loadError).toBeTruthy()
    expect(await store.save()).toBe(false)
    expect(saveSettings).not.toHaveBeenCalled()
  })

  it('does not show success if a deck save returns global defaults', async () => {
    vi.mocked(fetchSettings).mockResolvedValue({ data: { ...values, deckId: 18, dailyNewLimit: 3, dailyReviewLimit: 7 } } as Awaited<ReturnType<typeof fetchSettings>>)
    vi.mocked(saveSettings).mockResolvedValue({ data: values } as Awaited<ReturnType<typeof saveSettings>>)
    const store = useSettingsStore()
    await store.load(18)
    expect(await store.save()).toBe(false)
    expect(store.deckId).toBe(18)
    expect(ElMessage.success).not.toHaveBeenCalled()
  })

  it('keeps the latest deck when an earlier request finishes late', async () => {
    let finish!: (response: Awaited<ReturnType<typeof fetchSettings>>) => void
    vi.mocked(fetchSettings).mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    vi.mocked(fetchSettings).mockResolvedValueOnce({ data: { ...values, deckId: 19, dailyNewLimit: 9 } } as Awaited<ReturnType<typeof fetchSettings>>)
    const store = useSettingsStore()
    const oldLoad = store.load(18)
    await store.load(19)
    finish({ data: { ...values, deckId: 18, dailyNewLimit: 3 } } as Awaited<ReturnType<typeof fetchSettings>>)
    await oldLoad
    expect(store.deckId).toBe(19)
    expect(store.dailyNewLimit).toBe(9)
  })
})
