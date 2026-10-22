import { describe, expect, it } from 'vitest'
import RetellingMethodTips from '@/components/study/modules/RetellingMethodTips.vue'
import { mountWithApp } from '../../helpers/mountWithApp'

describe('RetellingMethodTips', () => {
  it('expands the echo-method guidance and collapses it again', async () => {
    const wrapper = mountWithApp(RetellingMethodTips)
    const toggle = wrapper.get('[data-testid="retelling-method-toggle"]')

    expect(toggle.attributes('aria-expanded')).toBe('false')
    expect(toggle.text()).toContain('句子复述有问题？')
    expect(wrapper.find('[data-testid="retelling-method-tips"]').exists()).toBe(false)

    await toggle.trigger('click')
    expect(toggle.attributes('aria-expanded')).toBe('true')
    const tips = wrapper.get('[data-testid="retelling-method-tips"]')
    expect(tips.text()).toContain('史嘉琳教授')
    expect(tips.text()).toContain('回音法')
    expect(tips.text()).toContain('影子跟读')
    expect(tips.text()).toContain('完整听完一遍原音频')

    await toggle.trigger('click')
    expect(wrapper.find('[data-testid="retelling-method-tips"]').exists()).toBe(false)
  })
})
