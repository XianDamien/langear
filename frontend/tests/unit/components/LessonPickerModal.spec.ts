import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import LessonPickerModal from '@/components/library/LessonPickerModal.vue'

describe('course and sentence selection', () => {
  it('retains other draft choices when a sentence selection joins a lesson', async () => {
    const wrapper = mount(LessonPickerModal, { props: {
      open: true, title: '课程', allowCardSelection: true, selectedLessonIds: [],
      lessons: [1, 2].map(lessonId => ({ lessonId, lessonTitle: `Lesson ${lessonId}`, sourceTitle: '课程', unitTitle: '单元' })),
    } })
    await wrapper.findAll('input').at(1)!.setValue(true)
    await wrapper.findAll('button').find(button => button.text() === '选择句子')!.trigger('click')
    expect(wrapper.emitted('selectCards')).toEqual([['1']])
    await wrapper.setProps({ selectedLessonIds: [1] })
    expect(wrapper.findAll('input').map(input => (input.element as HTMLInputElement).checked)).toEqual([true, true])
    await wrapper.findAll('button').find(button => button.text() === '保存选择')!.trigger('click')
    expect(wrapper.emitted('save')).toEqual([[[1, 2]]])
    wrapper.unmount()
  })
})
