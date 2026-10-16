import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { describe, expect, it, vi } from 'vitest'
import DeckReviewView from '@/views/DeckReviewView.vue'
import { contentResources, libraryContent } from '@/services/libraryContent'

vi.mock('@/services/libraryContent', () => ({
  contentResources: vi.fn(), libraryContent: { get: vi.fn() },
}))
const cards = [
  { id: 'a', deck_id: 'deck-a', note_id: 'n1', card_template_key: 'vocabulary_english_to_chinese', front: { word: 'journey' }, back: { meaning: '旅程' } },
  { id: 'b', deck_id: 'deck-a', note_id: 'n2', card_template_key: 'sentence_translation', front: { chinese: '你好' }, back: { english: 'Hello' } },
]
async function start() {
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/review/:deckId', component: DeckReviewView },
    { path: '/library', component: { template: '<div>Library</div>' } },
  ] })
  await router.push('/review/deck-a')
  const wrapper = mount(DeckReviewView, { global: { plugins: [router] } })
  await flushPromises()
  const click = async (text: string) => {
    await wrapper.findAll('button').find(b => b.text() === text)!.trigger('click')
    await flushPromises()
  }
  return { wrapper, router, click }
}
describe('deck flip practice', () => {
  it('hides answers until flipped, resets each card and supports completion and restart', async () => {
    vi.mocked(libraryContent.get).mockResolvedValue({ data: { id: 'deck-a', name: 'Practice' } })
    vi.mocked(contentResources).mockResolvedValue(cards)
    const { wrapper, click } = await start()
    expect(contentResources).toHaveBeenCalledWith('/cards', 'cards', { deck_id: 'deck-a', exclude_imported: true })
    expect(wrapper.text()).toContain('journey')
    expect(wrapper.text()).not.toContain('旅程')
    await click('显示答案')
    expect(wrapper.text()).toContain('旅程')
    await click('下一张')
    expect(wrapper.text()).toContain('你好')
    expect(wrapper.text()).not.toContain('Hello')
    await click('上一张')
    expect(wrapper.text()).not.toContain('旅程')
    await click('显示答案')
    await click('下一张')
    await click('显示答案')
    await click('完成本轮')
    expect(wrapper.text()).toContain('本轮翻卡完成')
    await click('再练一遍')
    expect(wrapper.text()).toContain('journey')
    expect(wrapper.text()).not.toContain('旅程')
    wrapper.unmount()
  })
  it('supports retry and empty decks without a false completion state', async () => {
    vi.mocked(libraryContent.get).mockResolvedValue({ data: { id: 'deck-a', name: 'Empty' } })
    vi.mocked(contentResources).mockRejectedValueOnce(new Error('offline')).mockResolvedValue([])
    const { wrapper, click } = await start()
    expect(wrapper.find('[role="alert"]').exists()).toBe(true)
    await click('重试')
    expect(wrapper.text()).toContain('这个牌组还没有卡片')
    expect(wrapper.text()).not.toContain('本轮翻卡完成')
    wrapper.unmount()
  })
  it('ignores late responses when navigating to another deck', async () => {
    vi.mocked(libraryContent.get).mockResolvedValue({ data: { id: 'deck-b', name: 'Second' } })
    let resolveOld!: (value: typeof cards) => void
    vi.mocked(contentResources).mockReturnValueOnce(new Promise(resolve => { resolveOld = resolve })).mockResolvedValue([])
    const { wrapper, router } = await start()
    await router.push('/review/deck-b')
    await flushPromises()
    resolveOld(cards)
    await flushPromises()
    expect(wrapper.text()).toContain('这个牌组还没有卡片')
    expect(wrapper.text()).not.toContain('journey')
    wrapper.unmount()
  })
})
