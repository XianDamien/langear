import { flushPromises, mount } from '@vue/test-utils'
import { expect, it, vi } from 'vitest'
import DialogueText from '@/components/dialogue/DialogueText.vue'

it('translates only on request, retries a failure, and reuses the translation when toggled', async () => {
  const translate = vi.fn().mockRejectedValueOnce(new Error('offline')).mockResolvedValue('能请你小声一点吗？')
  const wrapper = mount(DialogueText, { props: { english: 'Could you speak quietly?', translate } })
  expect(translate).not.toHaveBeenCalled()
  expect(wrapper.find('[lang="zh-CN"]').exists()).toBe(false)
  await wrapper.get('button').trigger('click'); await flushPromises()
  expect(wrapper.get('button').text()).toBe('重试中文')
  await wrapper.get('button').trigger('click'); await flushPromises()
  expect(wrapper.get('[lang="zh-CN"]').text()).toBe('能请你小声一点吗？')
  await wrapper.get('button').trigger('click')
  expect(wrapper.find('[lang="zh-CN"]').exists()).toBe(false)
  await wrapper.get('button').trigger('click')
  expect(translate).toHaveBeenCalledTimes(2)
  wrapper.unmount()
})
