<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ChevronDown, ChevronRight } from 'lucide-vue-next'
import { ElMessage } from 'element-plus'
import { cardEditorFields } from '@/services/cardEditorFields'
import RetroButton from '@/components/ui/RetroButton.vue'
import { fieldLabels, resourceError, templateLabels, type ResourceDeck, type ResourceCard, type ResourceNoteType, type ResourceMedia } from '@/services/contentCore'

import { contentResources, libraryContent } from '@/services/libraryContent'

const expandedDecks = ref(new Set<string>())
const cardLoading = ref(false)
const decks = ref<ResourceDeck[]>([])
const cards = ref<ResourceCard[]>([])
const noteTypes = ref<ResourceNoteType[]>([])
const media = ref<ResourceMedia[]>([])
const loading = ref(true)
const loadError = ref('')
const selectedDeck = ref('')
const deckDialog = ref(false)
const cardDialog = ref(false)
const saving = ref(false)
const formError = ref('')
const deckName = ref('')
const targetDeck = ref('')
const typeKey = ref('vocabulary_english_to_chinese')
const drafts = reactive<Record<string, Record<string,string>>>(Object.fromEntries(Object.keys(templateLabels).map(key => [key, {}])))
const tagDrafts = reactive<Record<string,string>>(Object.fromEntries(Object.keys(templateLabels).map(key => [key, ''])))
const cardTypes = computed(() => noteTypes.value.flatMap(type => type.card_templates.map(template => ({ ...template, noteTypeKey: type.key }))))
const activeTemplate = computed(() => cardTypes.value.find(t => t.key === typeKey.value))
const activeType = computed(() => noteTypes.value.find(t => t.key === activeTemplate.value?.noteTypeKey))
const editorFields = computed(() => cardEditorFields(activeType.value?.fields || [], activeTemplate.value))
const fields = computed(() => drafts[typeKey.value]!)
const standardDecks = computed(() => decks.value.filter(d => d.kind === 'standard'))
const personalDecks = computed(() => standardDecks.value.filter(d => !d.deck_guid?.startsWith('legacy:') || cards.value.some(c => c.deck_id === d.id)))
const generated = computed(() => activeTemplate.value && activeTemplate.value.required_fields.every(f => fields.value[f]?.trim()) ? [activeTemplate.value] : [])
const skipped = computed(() => activeTemplate.value && !generated.value.length ? [activeTemplate.value] : [])
const canSaveCard = computed(() => !!targetDeck.value && !!activeType.value && activeType.value.fields.every(f => !f.required || fields.value[f.key]?.trim()) && generated.value.length > 0)
watch(typeKey, () => { formError.value = '' })

function deckPath(deck: ResourceDeck): string {
  const names = [deck.name]; const visited = new Set([deck.id]); let parent = deck.parent_id
  while (parent && !visited.has(parent)) {
    visited.add(parent)
    const row = decks.value.find(d => d.id === parent)
    if (!row) break
    names.unshift(row.name); parent = row.parent_id
  }
  return names.join(' / ')
}
async function load() {
  loading.value = true; loadError.value = ''
  try {
    const [newDecks, newCards] = await Promise.all([
      contentResources<ResourceDeck>('/decks', 'decks'),
      contentResources<ResourceCard>('/cards', 'cards', { exclude_imported: true }),
    ])
    decks.value = newDecks; cards.value = newCards
  } catch (error) { loadError.value = resourceError(error) }
  finally { loading.value = false }
}
async function openDeck() {
  deckName.value = ''; formError.value = ''; deckDialog.value = true
}
async function openCard() {
  formError.value = ''; cardDialog.value = true; cardLoading.value = true
  try {
    const [newDecks, types, assets] = await Promise.all([
      contentResources<ResourceDeck>('/decks', 'decks'),
      libraryContent.get<{note_types: ResourceNoteType[]}>('/note-types'),
      contentResources<ResourceMedia>('/media-assets', 'media_assets'),
    ])
    decks.value = newDecks; noteTypes.value = types.data.note_types; media.value = assets
    targetDeck.value = standardDecks.value.find(d => d.id === selectedDeck.value)?.id || standardDecks.value[0]?.id || ''
  } catch (error) { formError.value = resourceError(error) }
  finally { cardLoading.value = false }
}
function toggleDeck(id: string) {
  if (expandedDecks.value.has(id)) expandedDecks.value.delete(id)
  else expandedDecks.value.add(id)
}
async function saveDeck() {
  if (!deckName.value.trim() || saving.value) return
  saving.value = true; formError.value = ''
  try {
    const { data } = await libraryContent.post<ResourceDeck>('/decks', { name: deckName.value.trim() })
    decks.value.push(data); selectedDeck.value = data.id; deckDialog.value = false; expandedDecks.value.add(data.id); loadError.value = ''
    ElMessage.success('牌组已添加')
  } catch (error) { formError.value = resourceError(error) }
  finally { saving.value = false }
}
async function saveCard() {
  if (!canSaveCard.value || saving.value) return
  saving.value = true; formError.value = ''
  try {
    const { data } = await libraryContent.post<{cards: ResourceCard[]}>('/notes', {
      deck_id: targetDeck.value, note_type_key: activeType.value!.key, card_template_key: typeKey.value,
      fields: Object.fromEntries(Object.entries(fields.value).filter(([, value]) => value.trim())),
      tags: (tagDrafts[typeKey.value] || '').split(/[,，\s]+/).filter(Boolean),
    })
    cards.value.push(...data.cards); selectedDeck.value = targetDeck.value; expandedDecks.value.add(targetDeck.value); loadError.value = ''
    drafts[typeKey.value] = {}; tagDrafts[typeKey.value] = ''; cardDialog.value = false
    ElMessage.success(`已添加 ${data.cards.length} 张卡片`)
  } catch (error) { formError.value = resourceError(error) }
  finally { saving.value = false }
}
function closeDialog(done: () => void) { if (!saving.value) done() }
defineExpose({ openDeck, openCard })
onMounted(load)
</script>

<template>
  <section aria-label="自建内容">
    <div
      v-if="loadError"
      class="mb-4 border border-amber-200 p-3 text-sm text-slate-600"
      role="alert"
    >
      自建内容加载失败：{{ loadError }}
      <button
        type="button"
        class="ml-3 text-brand-accent underline"
        @click="load"
      >
        重试
      </button>
    </div>
    <div
      v-if="personalDecks.length"
      class="mb-6 space-y-2"
    >
      <h3 class="mb-3 text-sm font-bold text-slate-500">
        自建内容
      </h3>
      <div
        v-for="deck in personalDecks"
        :key="deck.id"
        class="personal-deck"
      >
        <button
          type="button"
          class="mb-2 flex w-full items-center justify-between border border-slate-200 bg-slate-50 p-3 text-left hover:bg-slate-100"
          :aria-expanded="expandedDecks.has(deck.id)"
          @click="toggleDeck(deck.id)"
        >
          <span class="flex min-w-0 items-center gap-2">
            <component
              :is="expandedDecks.has(deck.id) ? ChevronDown : ChevronRight"
              :size="16"
              class="shrink-0 text-slate-400"
            />
            <span class="break-words font-bold text-lg">{{ deckPath(deck) }}</span>
          </span>
          <span class="ml-3 shrink-0 text-sm text-slate-500">{{ cards.filter(c => c.deck_id === deck.id).length }} 张卡片</span>
        </button>
        <div
          v-if="expandedDecks.has(deck.id)"
          class="ml-4 border-l border-slate-200 pl-4"
        >
          <p
            v-if="!cards.some(c => c.deck_id === deck.id)"
            class="py-4 text-sm text-slate-500"
          >
            暂无卡片，点击「添加卡片」开始。
          </p>
          <article
            v-for="card in cards.filter(c => c.deck_id === deck.id)"
            :key="card.id"
            class="personal-card mb-2 border border-slate-200 bg-white p-3"
          >
            <span class="text-xs font-bold text-brand-accent">{{ templateLabels[card.card_template_key] }}</span>
            <p class="mt-1 whitespace-pre-wrap break-words">
              {{ card.back.english || card.back.word }}
            </p>
            <p class="mt-1 whitespace-pre-wrap break-words text-sm text-slate-500">
              {{ card.back.chinese || card.back.meaning }}
            </p>
          </article>
        </div>
      </div>
    </div>
    <el-dialog
      v-model="deckDialog"
      title="添加牌组"
      width="440px"
      class="resource-dialog"
      append-to-body
      top="6vh"
      :close-on-click-modal="false"
      :close-on-press-escape="!saving"
      :show-close="!saving"
      :before-close="closeDialog"
      destroy-on-close
    >
      <form @submit.prevent="saveDeck">
        <label
          class="editor-label"
          for="deck-name"
        >新牌组名称</label><input
          id="deck-name"
          v-model="deckName"
          class="editor-input"
          autofocus
          required
          maxlength="200"
          placeholder="例如：日常英语"
          :disabled="saving"
        ><p
          v-if="formError"
          class="form-error"
          role="alert"
        >
          {{ formError }}
        </p><footer class="editor-footer">
          <RetroButton
            variant="secondary"
            :disabled="saving"
            @click="deckDialog = false"
          >
            取消
          </RetroButton><RetroButton
            type="submit"
            :disabled="saving || !deckName.trim()"
          >
            {{ saving ? '添加中…' : '添加' }}
          </RetroButton>
        </footer>
      </form>
    </el-dialog>

    <el-dialog
      v-model="cardDialog"
      title="添加卡片"
      width="720px"
      class="resource-dialog"
      append-to-body
      top="6vh"
      :close-on-click-modal="false"
      :close-on-press-escape="!saving"
      :show-close="!saving"
      :before-close="closeDialog"
      destroy-on-close
    >
      <p
        v-if="cardLoading"
        role="status"
        class="py-4 text-slate-500"
      >
        正在加载牌组和卡片类型…
      </p>
      <form @submit.prevent="saveCard">
        <div class="editor-selectors">
          <label><span class="editor-label">归属牌组</span><select
            v-model="targetDeck"
            class="editor-input"
            required
            :disabled="saving"
          ><option
            disabled
            value=""
          >请选择牌组</option><option
            v-for="deck in standardDecks"
            :key="deck.id"
            :value="deck.id"
          >{{ deckPath(deck) }}</option></select></label>
          <label><span class="editor-label">卡片类型</span><select
            v-model="typeKey"
            class="editor-input"
            :disabled="saving"
          ><option
            v-for="type in cardTypes"
            :key="type.key"
            :value="type.key"
          >{{ templateLabels[type.key] }}</option></select></label>
        </div>
        <p
          v-if="!cardLoading && !standardDecks.length && !formError"
          class="form-error"
        >
          请先关闭此窗口，添加一个牌组。
        </p>
        <div class="editor-fields">
          <label
            v-for="field in editorFields"
            :key="`${typeKey}-${field.key}`"
            class="field-row"
          ><span class="editor-label">{{ field.label }} <span
             v-if="field.required"
             class="required-mark"
           >*</span><span
             v-else
             class="optional-mark"
           >选填</span></span>
            <textarea
              v-if="field.kind === 'text'"
              v-model="fields[field.key]"
              :aria-label="field.label"
              class="editor-input"
              :rows="field.key === 'phonetic' ? 1 : 2"
              :required="field.required"
              :disabled="saving"
              :maxlength="100000"
            />
            <template v-else><select
              v-model="fields[field.key]"
              :aria-label="field.label"
              class="editor-input"
              :required="field.required"
              :disabled="saving || !media.some(m => m.kind === field.kind)"
            ><option :value="undefined">暂不选择</option><option
              v-for="asset in media.filter(m => m.kind === field.kind)"
              :key="asset.id"
              :value="asset.id"
            >{{ asset.name }}</option></select><span
              v-if="!media.some(m => m.kind === field.kind)"
              class="field-help"
            >暂无可选{{ fieldLabels[field.key] }}。{{ field.kind === 'audio' ? (field.required ? '此类型需要音频；音频上传功能尚未开放。' : '可暂不选择；音频上传功能尚未开放。') : '图片上传功能尚未开放。' }}</span></template>
            <span
              v-if="field.help"
              class="field-help"
            >{{ field.help }}</span>
          </label>
          <label class="field-row"><span class="editor-label">标签 <span class="optional-mark">选填</span></span><input
            v-model="tagDrafts[typeKey]"
            class="editor-input"
            placeholder="用空格或逗号分隔"
            :disabled="saving"
          ></label>
        </div>
        <div
          class="generation-preview"
          aria-live="polite"
        >
          <span class="editor-label">本次生成</span><div class="template-chips">
            <span
              v-for="template in generated"
              :key="template.key"
              class="template-chip"
            >{{ templateLabels[template.key] }}</span><span
              v-if="!generated.length"
              class="field-help"
            >填写内容后显示可生成的卡片。</span>
          </div><p
            v-for="template in skipped"
            :key="template.key"
            class="field-help"
          >
            {{ templateLabels[template.key] }}：还需{{ template.required_fields.filter(f => !fields[f]?.trim()).map(f => editorFields.find(field => field.key === f)?.label || fieldLabels[f]).join('、') }}
          </p>
        </div>
        <p
          v-if="formError"
          class="form-error"
          role="alert"
        >
          {{ formError }}
        </p>
        <footer class="editor-footer">
          <span class="save-hint">添加后保留所选牌组和类型</span><RetroButton
            variant="secondary"
            :disabled="saving"
            @click="cardDialog = false"
          >
            取消
          </RetroButton><RetroButton
            type="submit"
            :disabled="saving || cardLoading || !canSaveCard"
          >
            {{ saving ? '添加中…' : '添加' }}
          </RetroButton>
        </footer>
      </form>
    </el-dialog>
  </section>
</template>
<style scoped>
.editor-selectors{display:grid;grid-template-columns:1fr 1fr;gap:18px;padding-bottom:20px;border-bottom:1px solid #e2e8f0}.editor-label{display:block;font-size:13px;font-weight:700;color:#334155;margin-bottom:8px}.editor-input{width:100%;border:1px solid #cbd5e1;background:#fff;padding:10px 12px;color:#0f172a;border-radius:3px;font-size:14px;outline:none;resize:vertical}.editor-input:focus{border-color:#ff4d2d;box-shadow:0 0 0 2px #ffe3dc}.editor-input:disabled{background:#f8fafc;color:#94a3b8}.editor-fields{display:grid;gap:16px;padding:20px 0}.required-mark{color:#b91c1c}.optional-mark{font-size:11px;font-weight:400;color:#94a3b8;margin-left:6px}.field-help{display:block;color:#64748b;font-size:12px;line-height:1.7;margin-top:6px}.generation-preview{background:#f8fafc;border:1px solid #e2e8f0;padding:14px 16px}.template-chips{display:flex;gap:8px;flex-wrap:wrap}.template-chip{background:#fff0eb;border:1px solid #ffd0c1;color:#9a3412;padding:3px 10px;font-size:12px}.editor-footer{display:flex;justify-content:flex-end;align-items:center;gap:12px;padding-top:24px}.save-hint{margin-right:auto;font-size:12px;color:#64748b}.form-error{color:#b91c1c;font-size:13px;margin-top:14px}button:focus-visible{outline:2px solid #ff4d2d;outline-offset:3px}@media(max-width:760px){.editor-selectors{grid-template-columns:1fr}.save-hint{display:none}}
</style>
<style>.resource-dialog{max-width:calc(100vw - 32px);max-height:88dvh;overflow-y:auto;border-radius:4px!important;background:#fff!important}.resource-dialog .editor-footer{position:sticky;bottom:-16px;background:#fff;padding-bottom:16px;border-top:1px solid #e2e8f0}.resource-dialog .el-dialog__title{font-weight:750;color:#0f172a}.resource-dialog .el-dialog__body{padding-top:12px}.resource-dialog .el-dialog__header{border-bottom:1px solid #e2e8f0;padding-bottom:16px;margin-bottom:8px}</style>
