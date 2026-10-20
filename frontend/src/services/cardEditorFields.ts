import type { ResourceField, ResourceTemplate } from './content'
import { fieldLabels } from './content'

interface FieldPresentation { key: string; label: string; help?: string }

// Prompt and answer roles belong to the selected exercise, not the shared NoteType.
const layouts: Record<string, FieldPresentation[]> = {
  vocabulary_english_to_chinese: [
    { key: 'word', label: '英文单词', help: '作为题目展示。' },
    { key: 'meaning', label: '中文释义', help: '翻面后展示的参考答案。' },
    { key: 'phonetic', label: '音标' },
    { key: 'mnemonic', label: '助记', help: '联想、词根或记忆提示，翻面后显示。' },
    { key: 'reference_audio', label: '单词发音' },
    { key: 'image', label: '辅助图片' },
    { key: 'note', label: '笔记' },
  ],
  vocabulary_chinese_to_english: [
    { key: 'meaning', label: '中文释义', help: '作为题目展示。' },
    { key: 'word', label: '英文单词', help: '翻面后展示的参考答案。' },
    { key: 'phonetic', label: '音标' },
    { key: 'mnemonic', label: '助记', help: '联想、词根或记忆提示，翻面后显示。' },
    { key: 'reference_audio', label: '单词发音' },
    { key: 'image', label: '辅助图片' },
    { key: 'note', label: '笔记' },
  ],
  sentence_retelling: [
    { key: 'reference_audio', label: '参考音频', help: '学习时先听音频，再录音复述。' },
    { key: 'english', label: '英文参考原文', help: '用于对照复述内容。' },
    { key: 'chinese', label: '中文翻译', help: '帮助理解原文，选填。' },
    { key: 'note', label: '笔记' },
  ],
  sentence_translation: [
    { key: 'chinese', label: '中文原文', help: '作为翻译题目展示。' },
    { key: 'english', label: '英文参考译文', help: '用于对照学习者输入的英文译文。' },
    { key: 'reference_audio', label: '参考音频', help: '翻面后可听参考发音，选填。' },
    { key: 'note', label: '笔记' },
  ],
  sentence_dictation: [
    { key: 'reference_audio', label: '题目音频', help: '学习时听音频，输入听到的英文。' },
    { key: 'english', label: '英文标准答案', help: '用于核对听写结果。' },
    { key: 'chinese', label: '中文释义', help: '翻面后辅助理解，选填。' },
    { key: 'note', label: '笔记' },
  ],
}

export function cardEditorFields(fields: ResourceField[], template?: ResourceTemplate) {
  if (!template) return []
  const layout: FieldPresentation[] = layouts[template.key] || fields.map(field => ({ key: field.key, label: fieldLabels[field.key] || field.key }))
  return layout.flatMap(presentation => {
    const field = fields.find(value => value.key === presentation.key)
    return field ? [{ ...field, ...presentation, required: field.required || template.required_fields.includes(field.key) }] : []
  })
}
