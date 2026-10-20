import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import AIFeedbackPanel from '@/components/study/modules/AIFeedbackPanel.vue'

describe('AIFeedbackPanel dimension feedback', () => {
  it('shows the three dimension evaluations with their matching suggestions', () => {
    const wrapper = mount(AIFeedbackPanel, { props: {
      feedback: { feedback: {
        pronunciation: '发音整体清晰，只有个别元音偏短。',
        completeness: '内容完整。',
        fluency: '语流自然。',
        suggestions: [
          { text: '练习 /eə/ 时把口型从 /e/ 滑到 /ə/。', target_word: 'hair', timestamp: 1.2, dimension: 'pronunciation' },
        ],
        issues: [],
      } }, loading: false,
    } })

    const sections = wrapper.findAll('[data-testid="feedback-dimension"]')
    expect(sections).toHaveLength(3)
    expect(wrapper.text()).toContain('发音')
    expect(wrapper.text()).toContain('完整度')
    expect(wrapper.text()).toContain('流利度')
    expect(wrapper.text()).toContain('发音整体清晰，只有个别元音偏短。')
    expect(wrapper.text()).toContain('练习 /eə/ 时把口型从 /e/ 滑到 /ə/。')
    expect(wrapper.text()).not.toContain('问题点')
    // 建议挂在对应维度下，而不是另外堆一个建议列表
    expect(sections[0].text()).toContain('改进建议：练习 /eə/ 时把口型从 /e/ 滑到 /ə/。')
    expect(sections[1].text()).not.toContain('练习 /eə/')
    wrapper.unmount()
  })

  it('keeps suggestions without a dimension in a shared block', () => {
    const wrapper = mount(AIFeedbackPanel, { props: {
      feedback: { feedback: {
        pronunciation: '发音清晰。',
        suggestions: [{ text: '注意句尾不要吞音。', target_word: null, timestamp: null }],
        issues: [],
      } }, loading: false,
    } })

    expect(wrapper.text()).toContain('改进建议')
    expect(wrapper.text()).toContain('注意句尾不要吞音。')
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
