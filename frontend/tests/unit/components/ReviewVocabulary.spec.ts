import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ReviewCardFront from '@/components/review/ReviewCardFront.vue'
import ReviewCardBack from '@/components/review/ReviewCardBack.vue'

describe('vocabulary card templates', () => {
  it.each([
    ['vocabulary_english_to_chinese', 'journey', '旅程'],
    ['vocabulary_chinese_to_english', '旅程', 'journey'],
  ])('shows only the prompt for %s', (key, prompt, answer) => {
    const wrapper = mount(ReviewCardFront, { props: { card: { card_template_key: key, front: { word: 'journey', meaning: '旅程' } } } })
    expect(wrapper.text()).toBe(prompt)
    expect(wrapper.text()).not.toContain(answer)
  })
  it('renders real vocabulary fields and omits absent optional fields', () => {
    const wrapper = mount(ReviewCardBack, { props: { backSnapshot: { english: 'journey', chinese: '旅程', phonetic: '/ˈdʒɜːni/', mnemonic: '联想到旅程' } } })
    expect(wrapper.text()).toContain('journey')
    expect(wrapper.text()).toContain('旅程')
    expect(wrapper.text()).toContain('/ˈdʒɜːni/')
    expect(wrapper.text()).toContain('助记')
    expect(wrapper.text()).toContain('联想到旅程')
    expect(wrapper.text()).not.toContain('笔记')
  })
})
