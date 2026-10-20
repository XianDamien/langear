import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import AIFeedbackPanel from '@/components/study/modules/AIFeedbackPanel.vue'

describe('AIFeedbackPanel improvement-only feedback', () => {
  it('shows a concise suggestion without a duplicate issue list or summary cards', () => {
    const wrapper = mount(AIFeedbackPanel, { props: {
      feedback: { feedback: {
        pronunciation: '发音整体清晰。', completeness: '内容完整。', fluency: '语流自然。',
        suggestions: [{ text: '练习时把重音自然放在第二音节。', target_word: 'behind', timestamp: 1.2 }],
        issues: [{ problem: '重音不正确。', timestamp: 1.2 }],
      } }, loading: false,
    } })

    expect(wrapper.text()).toContain('可以试试')
    expect(wrapper.text()).toContain('练习时把重音自然放在第二音节。')
    expect(wrapper.text()).not.toContain('问题点')
    expect(wrapper.text()).not.toContain('重音不正确')
    expect(wrapper.text()).not.toContain('发音整体清晰')
    wrapper.unmount()
  })

  it('uses legacy inline suggestions when old feedback has only issues', () => {
    const wrapper = mount(AIFeedbackPanel, { props: {
      feedback: { feedback: {
        issues: [{ problem: '重音不正确。', suggestion: '注意自然地重读第二音节。', timestamp: 1.2, target_word: 'behind' }],
      } }, loading: false,
    } })

    expect(wrapper.text()).toContain('注意自然地重读第二音节。')
    expect(wrapper.text()).not.toContain('重音不正确。')
    wrapper.unmount()
  })

  it('shows no correction when neither field contains a reliable improvement', () => {
    const timestampClick = vi.fn()
    const wrapper = mount(AIFeedbackPanel, { props: {
      feedback: { feedback: { issues: [], suggestions: [] } }, loading: false,
    }, attrs: { onTimestampClick: timestampClick } })

    expect(wrapper.text()).toContain('这次没有明确需要调整的地方')
    expect(wrapper.findAll('li')).toHaveLength(0)
    wrapper.unmount()
  })
})
