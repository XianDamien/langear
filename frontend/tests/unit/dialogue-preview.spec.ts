import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, expect, it, vi } from 'vitest'
import DialoguePreviewView from '@/views/DialoguePreviewView.vue'
import { dialogueApi } from '@/services/dialogue'
import { reviewHttp } from '@/services/review'
import { createRecordingSession } from '@/adapters/browser/recording'
import router from '@/router'

vi.mock('@/services/dialogue', () => ({
  dialogueApi: { create: vi.fn(), get: vi.fn(), finish: vi.fn(), review: vi.fn() },
  dialogueError: () => '请求失败', dialogueSocketUrl: () => 'wss://testserver/dialogue',
}))
vi.mock('@/services/review', () => ({ reviewHttp: { get: vi.fn() } }))
vi.mock('@/adapters/browser/recording', () => ({ createRecordingSession: vi.fn() }))

beforeEach(() => {
  vi.spyOn(HTMLDialogElement.prototype, 'showModal').mockImplementation(function () { this.open = true })
})

it('guides a recap into refinement, a task, and roleplay without network or microphone calls', async () => {
  const socket = vi.fn()
  vi.stubGlobal('WebSocket', socket)
  const wrapper = mount(DialoguePreviewView, { attachTo: document.body })
  const button = (text: string) => wrapper.findAll('button').find(item => item.text().includes(text))!

  expect(wrapper.text()).toContain('What happened at the theatre?')
  expect(wrapper.find('textarea').exists()).toBe(true)
  expect(wrapper.text()).not.toContain('更清楚的版本')
  expect(wrapper.text()).not.toContain('本次任务')
  await wrapper.get('textarea').setValue('People were talking loudly.')
  await wrapper.get('form').trigger('submit')
  expect(wrapper.text()).toContain('You mentioned the noise.')
  expect(wrapper.text()).toContain('更清楚的版本')
  expect(wrapper.text()).not.toContain('Good evening.')
  await button('试试真实场景任务').trigger('click')
  expect(wrapper.text()).toContain('本次任务')
  expect(wrapper.text()).toContain('试试这些表达')
  expect(wrapper.text()).not.toContain('Good evening.')
  await button('我准备好了，开始吧！').trigger('click')
  expect(wrapper.text()).toContain('Good evening.')
  for (let turn = 0; turn < 2; turn++) {
    await button('预览语音').trigger('click')
    expect(wrapper.get('[role="status"]').text()).toContain('未使用麦克风录音')
    await button('发送示例语音').trigger('click')
  }
  expect(wrapper.text()).toContain('You made a polite request.')
  expect(socket).not.toHaveBeenCalled()
  expect(createRecordingSession).not.toHaveBeenCalled()
  for (const method of Object.values(dialogueApi)) expect(method).not.toHaveBeenCalled()
  expect(reviewHttp.get).not.toHaveBeenCalled()
  await button('完成').trigger('click')
  expect(wrapper.find('dialog').exists()).toBe(false)
  await button('打开对话预览').trigger('click')
  expect(wrapper.get('select').element.value).toBe('recap')
  wrapper.unmount()
  vi.unstubAllGlobals()
})

it('hides Chinese by default, toggles translations independently, and resets them on a stage change', async () => {
  const wrapper = mount(DialoguePreviewView, { attachTo: document.body })
  expect(wrapper.find('[lang="zh-CN"]').exists()).toBe(false)
  const translate = () => wrapper.findAll('button').filter(item => item.text() === '中文')
  await translate()[0]!.trigger('click')
  expect(wrapper.get('[lang="zh-CN"]').text()).toContain('你刚练习了')
  await wrapper.findAll('button').find(item => item.text() === '收起中文')!.trigger('click')
  expect(wrapper.find('[lang="zh-CN"]').exists()).toBe(false)
  await wrapper.get('select').setValue('task')
  expect(wrapper.find('[lang="zh-CN"]').exists()).toBe(false)
  await translate().at(-1)!.trigger('click')
  expect(wrapper.findAll('[lang="zh-CN"]')).toHaveLength(1)
  expect(wrapper.get('[lang="zh-CN"]').text()).toContain('安静一点的座位')
  await wrapper.get('select').setValue('recap')
  expect(wrapper.find('[lang="zh-CN"]').exists()).toBe(false)
  wrapper.unmount()
})

it('preserves entered answers, allows blank-answer protection, supports narrow layout and reconnects', async () => {
  const wrapper = mount(DialoguePreviewView, { attachTo: document.body })
  await wrapper.get('form').trigger('submit')
  expect(wrapper.get('select').element.value).toBe('recap')
  await wrapper.get('textarea').setValue('He went out one evening.')
  await wrapper.get('form').trigger('submit')
  expect(wrapper.text()).toContain('He went out one evening.')
  expect(wrapper.text()).toContain('Let’s connect the setting')
  await wrapper.get('[aria-label="切换手机宽度"]').trigger('click')
  expect(wrapper.get('dialog').attributes('style')).toContain('390px')
  await wrapper.get('select').setValue('failed')
  const priorMessages = wrapper.get('[aria-label="对话记录"]').text()
  await wrapper.findAll('button').find(item => item.text() === '重新连接')!.trigger('click')
  expect(wrapper.find('[role="alert"]').exists()).toBe(false)
  expect(wrapper.get('select').element.value).toBe('roleplay')
  expect(wrapper.get('[aria-label="对话记录"]').text()).toBe(priorMessages)
  wrapper.unmount()
})

it('opens the development preview without looking up an account', async () => {
  await router.push('/preview/dialogue')
  await flushPromises()
  expect(router.currentRoute.value.name).toBe('DialoguePreview')
})
