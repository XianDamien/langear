import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { describe, expect, it, vi } from 'vitest'
import ReviewSessionView from '@/views/ReviewSessionView.vue'
import { contentResources, libraryContent } from '@/services/libraryContent'

vi.mock('@/services/libraryContent', () => ({
  contentResources: vi.fn(), libraryContent: { get: vi.fn() },
}))
const cards = [
  { id: 'a', deck_id: 'deck-a', note_id: 'n1', card_template_key: 'vocabulary_english_to_chinese', front: { word: 'journey' }, back: { word: 'journey', meaning: '旅程' } },
  { id: 'b', deck_id: 'deck-a', note_id: 'n2', card_template_key: 'sentence_translation', front: { chinese: '你好' }, back: { english: 'Hello' } },
]
async function start() {
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/review/:deckId', component: ReviewSessionView },
    { path: '/library', component: { template: '<div>Library</div>' } },
  ] })
  await router.push('/review/deck-a')
  const wrapper = mount(ReviewSessionView, { global: { plugins: [router] } })
  await flushPromises()
  const click = async (text: string) => {
    await wrapper.findAll('button').find(b => b.text() === text)!.trigger('click')
    await flushPromises()
  }
  return { wrapper, router, click }
}
describe('deck flip practice', () => {
  it('shows the mnemonic only on the answer and offers no forward navigation for words', async () => {
    vi.mocked(libraryContent.get).mockResolvedValue({ data: { id: 'deck-a', name: 'Practice' } })
    vi.mocked(contentResources).mockResolvedValue([{ ...cards[0]!, back: { word: 'journey', meaning: '旅程', mnemonic: '记忆联想', note: '常用搭配' } }])
    const { wrapper, click } = await start()
    expect(contentResources).toHaveBeenCalledWith('/cards', 'cards', { deck_id: 'deck-a', exclude_imported: true, study_only: true })
    expect(wrapper.text()).toContain('journey')
    expect(wrapper.text()).not.toContain('记忆联想')
    await click('显示答案')
    expect(wrapper.text()).toContain('旅程')
    expect(wrapper.text()).toContain('记忆联想')
    expect(wrapper.text()).toContain('常用搭配')
    const ratings = wrapper.get('[aria-label="复习评分（尚未启用）"]')
    expect(ratings.findAll('button')).toHaveLength(4)
    for (const button of ratings.findAll('button')) expect(button.attributes('disabled')).toBeDefined()
    expect(wrapper.findAll('button').some(b => ['下一张', '上一张', '查看题面', '完成本轮'].includes(b.text()))).toBe(false)
    wrapper.unmount()
  })
  it('compares the typed translation without sentence navigation', async () => {
    vi.mocked(libraryContent.get).mockResolvedValue({ data: { id: 'deck-a', name: 'Mixed' } })
    vi.mocked(contentResources).mockResolvedValue([cards[1]!, cards[0]!])
    const { wrapper, click } = await start()
    expect(wrapper.get('[data-testid="translation-prompt"]').text()).toBe('你好')
    expect(wrapper.findAll('button').find(button => button.text() === '显示答案')!.attributes('disabled')).toBeDefined()
    await wrapper.get('textarea').setValue('   ')
    expect(wrapper.findAll('button').find(button => button.text() === '显示答案')!.attributes('disabled')).toBeDefined()
    await wrapper.get('textarea').setValue('Hi')
    await click('显示答案')
    expect(wrapper.text()).toContain('Hello')
    expect(wrapper.text()).toContain('Hi')
    expect(wrapper.text()).toContain('我的译文')
    expect(wrapper.text()).toContain('参考译文')
    expect(wrapper.find('[data-testid="text-difference-count"]').exists()).toBe(false)
    expect(wrapper.findAll('audio')).toHaveLength(0)
    expect(wrapper.findAll('button').some(b => ['下一张', '上一张', '查看题面'].includes(b.text()))).toBe(false)
    wrapper.unmount()
  })
  it('plays translation reference audio only after revealing the answer', async () => {
    vi.mocked(libraryContent.get).mockImplementation(async path => ({ data: path.startsWith('/media-assets') ? { url: '/translation-reference.wav' } : { id: 'deck-a', name: 'Translation' } }))
    vi.mocked(contentResources).mockResolvedValue([{
      ...cards[1]!, back: { english: 'Hello', reference_audio: 'translation-audio' },
    }])
    const { wrapper, click } = await start()
    expect(wrapper.findAll('audio')).toHaveLength(0)
    expect(wrapper.text()).not.toContain('Hello')
    await wrapper.get('textarea').setValue('Hi')
    await click('显示答案')
    expect(libraryContent.get).toHaveBeenCalledWith('/media-assets/translation-audio/url')
    const audio = wrapper.get('audio').element
    expect(audio.getAttribute('src')).toBe('/translation-reference.wav')
    const play = vi.spyOn(audio, 'play').mockResolvedValue()
    await wrapper.get('[aria-label="播放原音频"]').trigger('click')
    expect(play).toHaveBeenCalledOnce()
    expect(wrapper.find('[data-testid="text-difference-count"]').exists()).toBe(false)
    wrapper.unmount()
  })
  it('uses audio-only dictation prompts and compares case, punctuation and spacing after input', async () => {
    vi.mocked(libraryContent.get).mockImplementation(async path => ({ data: path.startsWith('/media-assets') ? { url: '/reference.wav' } : { id: 'deck-a', name: 'Dictation' } }))
    vi.mocked(contentResources).mockResolvedValue([{
      id: 'dictation', deck_id: 'deck-a', note_id: 'n3', card_template_key: 'sentence_dictation',
      front: { reference_audio: 'audio-1' }, back: { english: 'Hello, world!', chinese: '你好，世界！', note: '注意标点', reference_audio: 'audio-1' },
    }])
    const { wrapper, click } = await start()
    expect(wrapper.find('[data-testid="sentence-dictation-card"]').exists()).toBe(true)
    expect(wrapper.text()).not.toContain('Hello')
    expect(wrapper.text()).not.toContain('你好')
    expect(wrapper.get('[aria-label="播放原音频"]').attributes('disabled')).toBeUndefined()
    expect(wrapper.get('textarea').attributes('spellcheck')).toBe('false')
    await wrapper.get('textarea').setValue('hello  world')
    await click('显示答案')
    expect(wrapper.text()).toContain('标准答案')
    expect(wrapper.text()).toContain('我的听写')
    expect(wrapper.text()).toContain('注意标点')
    expect(wrapper.get('[data-testid="text-difference-count"]').text()).not.toBe('0 处差异')
    expect(wrapper.get('[data-testid="original-text"]').text()).toBe('Hello, world!')
    expect(wrapper.findAll('audio')).toHaveLength(1)
    expect(wrapper.findAll('button').some(button => ['上一张', '下一张'].includes(button.text()))).toBe(false)
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
