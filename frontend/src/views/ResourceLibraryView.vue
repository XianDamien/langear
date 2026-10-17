<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { Plus, Layers, BookOpen, ChevronRight } from 'lucide-vue-next'
import { ElMessage } from 'element-plus'
import { cardEditorFields } from '@/services/cardEditorFields'
import RetroButton from '@/components/ui/RetroButton.vue'
import { allResources, coreHttp, fieldLabels, resourceError, templateLabels, type ResourceDeck, type ResourceCard, type ResourceNoteType, type ResourceMedia } from '@/services/contentCore'

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
const currentCards = computed(() => cards.value.filter(c => c.deck_id === selectedDeck.value))
const selectedName = computed(() => decks.value.find(d => d.id === selectedDeck.value)?.name)
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
    const [newDecks, newCards, types, assets] = await Promise.all([
      allResources<ResourceDeck>('/decks', 'decks'), allResources<ResourceCard>('/cards', 'cards'),
      coreHttp.get<{note_types: ResourceNoteType[]}>('/note-types'), allResources<ResourceMedia>('/media-assets', 'media_assets'),
    ])
    decks.value = newDecks; cards.value = newCards; noteTypes.value = types.data.note_types; media.value = assets
    if (!newDecks.some(d => d.id === selectedDeck.value)) selectedDeck.value = newDecks[0]?.id || ''
  } catch (error) { loadError.value = resourceError(error) }
  finally { loading.value = false }
}
function openDeck() { deckName.value = ''; formError.value = ''; deckDialog.value = true }
function openCard() {
  targetDeck.value = standardDecks.value.find(d => d.id === selectedDeck.value)?.id || standardDecks.value[0]?.id || ''
  formError.value = ''; cardDialog.value = true
}
async function saveDeck() {
  if (!deckName.value.trim() || saving.value) return
  saving.value = true; formError.value = ''
  try {
    const { data } = await coreHttp.post<ResourceDeck>('/decks', { name: deckName.value.trim() })
    decks.value.push(data); selectedDeck.value = data.id; deckDialog.value = false
    ElMessage.success('牌组已添加')
  } catch (error) { formError.value = resourceError(error) }
  finally { saving.value = false }
}
async function saveCard() {
  if (!canSaveCard.value || saving.value) return
  saving.value = true; formError.value = ''
  try {
    const { data } = await coreHttp.post<{cards: ResourceCard[]}>('/notes', {
      deck_id: targetDeck.value, note_type_key: activeType.value!.key, card_template_key: typeKey.value,
      fields: Object.fromEntries(Object.entries(fields.value).filter(([, value]) => value.trim())),
      tags: (tagDrafts[typeKey.value] || '').split(/[,，\s]+/).filter(Boolean),
    })
    cards.value.push(...data.cards); selectedDeck.value = targetDeck.value
    drafts[typeKey.value] = {}; tagDrafts[typeKey.value] = ''; cardDialog.value = false
    ElMessage.success(`已添加 ${data.cards.length} 张卡片`)
  } catch (error) { formError.value = resourceError(error) }
  finally { saving.value = false }
}
function closeDialog(done: () => void) { if (!saving.value) done() }
onMounted(load)
</script>

<template>
  <section class="resource-page animate-fadeIn">
    <header class="resource-heading">
      <div>
        <p class="eyebrow">
          YOUR COLLECTION
        </p><h2>题库资源</h2><p class="intro">
          按牌组整理内容，让每一张卡片各有所属。
        </p>
      </div>
      <div class="heading-actions">
        <RetroButton
          variant="secondary"
          :icon="Plus"
          :disabled="loading || !!loadError"
          @click="openDeck"
        >
          添加牌组
        </RetroButton>
        <RetroButton
          :icon="Plus"
          :disabled="loading || !!loadError"
          @click="openCard"
        >
          添加卡片
        </RetroButton>
      </div>
    </header>
    <div
      v-if="loading"
      class="state-panel"
      role="status"
    >
      正在加载题库资源…
    </div>
    <div
      v-else-if="loadError"
      class="state-panel"
      role="alert"
    >
      <p>{{ loadError }}</p><RetroButton
        class="mt-4"
        @click="load"
      >
        重新加载
      </RetroButton>
    </div>
    <div
      v-else
      class="resource-workspace"
    >
      <aside
        class="deck-list"
        aria-label="牌组列表"
      >
        <div class="section-caption">
          <span>我的牌组</span><span>{{ decks.length }}</span>
        </div>
        <p
          v-if="!decks.length"
          class="empty-hint"
        >
          还没有牌组，先添加一个吧。
        </p>
        <button
          v-for="deck in decks"
          :key="deck.id"
          type="button"
          class="deck-row"
          :class="{ selected: selectedDeck === deck.id }"
          :aria-pressed="selectedDeck === deck.id"
          @click="selectedDeck = deck.id"
        >
          <Layers :size="18" /><span class="deck-name">{{ deckPath(deck) }}</span><span class="deck-count">{{ cards.filter(c => c.deck_id === deck.id).length }}</span><ChevronRight :size="14" />
        </button>
      </aside>
      <section
        class="card-list"
        aria-label="牌组卡片"
      >
        <header class="card-list-heading">
          <RouterLink v-if="selectedDeck" :to="`/review/${selectedDeck}`" class="text-sm text-brand-accent underline">开始复习</RouterLink>
          <h3>{{ selectedName || '开始整理你的题库' }}</h3><span>{{ currentCards.length }} 张卡片</span>
        </header>
        <div
          v-if="!currentCards.length"
          class="empty-cards"
        >
          <BookOpen
            :size="38"
            :stroke-width="1.2"
          /><h4>把第一条内容放进来</h4><p>词汇和句子卡片可以放在同一个牌组。</p><button
            type="button"
            @click="standardDecks.length ? openCard() : openDeck()"
          >
            {{ standardDecks.length ? '添加卡片' : '添加牌组' }} <span aria-hidden="true">↗</span>
          </button>
        </div>
        <article
          v-for="card in currentCards"
          :key="card.id"
          class="content-card"
        >
          <span class="template-label">{{ templateLabels[card.card_template_key] }}</span><p>{{ card.back.english || card.back.word }}</p><p class="translation">
            {{ card.back.chinese || card.back.meaning }}
          </p>
        </article>
      </section>
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
          v-if="!standardDecks.length"
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
            :disabled="saving || !canSaveCard"
          >
            {{ saving ? '添加中…' : '添加' }}
          </RetroButton>
        </footer>
      </form>
    </el-dialog>
  </section>
</template>

<style scoped>
.resource-page{max-width:1200px;margin:12px auto}.resource-heading{display:flex;align-items:center;justify-content:space-between;gap:24px;margin-bottom:32px}.eyebrow{font-size:11px;letter-spacing:.18em;font-weight:700;color:#64748b;margin-bottom:8px}.resource-heading h2{font-size:30px;font-weight:800;color:#0f172a}.intro{color:#64748b;font-size:14px;margin-top:8px}.heading-actions{display:flex;gap:12px;flex-shrink:0}.resource-workspace{display:grid;grid-template-columns:260px minmax(0,1fr);min-height:460px;border:1px solid #cbd5e1;background:white}.deck-list{border-right:1px solid #e2e8f0;background:#f8fafc;padding:18px 12px}.section-caption{display:flex;justify-content:space-between;padding:0 10px 16px;font-size:12px;font-weight:700;color:#64748b}.deck-row{display:flex;align-items:center;gap:10px;text-align:left;width:100%;padding:13px 10px;margin-bottom:6px;border:1px solid transparent;color:#475569}.deck-row.selected{background:#fff;border-color:#cbd5e1;color:#0f172a;box-shadow:2px 2px 0 #e2e8f0}.deck-row:hover{background:#fff}.deck-name{flex:1;overflow-wrap:anywhere;font-weight:600;font-size:14px}.deck-count{font-size:12px;color:#64748b}.card-list{padding:24px}.card-list-heading{display:flex;justify-content:space-between;gap:12px;align-items:center;border-bottom:1px solid #e2e8f0;padding-bottom:18px;margin-bottom:8px}.card-list-heading h3{font-size:18px;font-weight:700;overflow-wrap:anywhere}.card-list-heading>span{font-size:12px;color:#64748b;white-space:nowrap}.empty-cards{padding:64px 12px;text-align:center;color:#94a3b8}.empty-cards svg{margin:0 auto 20px}.empty-cards h4{font-size:18px;color:#334155;font-weight:600}.empty-cards p{font-size:14px;margin:8px 0 22px}.empty-cards button{color:#b93820;font-weight:700}.content-card{padding:20px 0;border-bottom:1px solid #f1f5f9}.content-card>p{margin-top:8px;overflow-wrap:anywhere;white-space:pre-wrap}.template-label{font-size:11px;font-weight:700;letter-spacing:.04em;color:#b93820}.translation{font-size:14px;color:#64748b}.state-panel{padding:70px 24px;background:white;border:1px solid #e2e8f0}.empty-hint{font-size:13px;padding:16px;color:#64748b}.editor-selectors{display:grid;grid-template-columns:1fr 1fr;gap:18px;padding-bottom:20px;border-bottom:1px solid #e2e8f0}.editor-label{display:block;font-size:13px;font-weight:700;color:#334155;margin-bottom:8px}.editor-input{width:100%;border:1px solid #cbd5e1;background:#fff;padding:10px 12px;color:#0f172a;border-radius:3px;font-size:14px;outline:none;resize:vertical}.editor-input:focus{border-color:#ff4d2d;box-shadow:0 0 0 2px #ffe3dc}.editor-input:disabled{background:#f8fafc;color:#94a3b8}.editor-fields{display:grid;gap:16px;padding:20px 0}.required-mark{color:#b91c1c}.optional-mark{font-size:11px;font-weight:400;color:#94a3b8;margin-left:6px}.field-help{display:block;color:#64748b;font-size:12px;line-height:1.7;margin-top:6px}.generation-preview{background:#f8fafc;border:1px solid #e2e8f0;padding:14px 16px}.template-chips{display:flex;gap:8px;flex-wrap:wrap}.template-chip{background:#fff0eb;border:1px solid #ffd0c1;color:#9a3412;padding:3px 10px;font-size:12px}.editor-footer{display:flex;justify-content:flex-end;align-items:center;gap:12px;padding-top:24px}.save-hint{margin-right:auto;font-size:12px;color:#64748b}.form-error{color:#b91c1c;font-size:13px;margin-top:14px}button:focus-visible{outline:2px solid #ff4d2d;outline-offset:3px}@media(max-width:760px){.resource-heading{align-items:flex-start;flex-direction:column}.heading-actions{width:100%;flex-wrap:wrap}.heading-actions button{flex:1}.resource-workspace{grid-template-columns:1fr}.deck-list{border-right:0;border-bottom:1px solid #e2e8f0}.card-list{padding:18px}.editor-selectors{grid-template-columns:1fr}.save-hint{display:none}.empty-cards{padding:32px 4px}}
</style>
<style>.resource-dialog{max-width:calc(100vw - 32px);max-height:88dvh;overflow-y:auto;border-radius:4px!important;background:#fff!important}.resource-dialog .editor-footer{position:sticky;bottom:-16px;background:#fff;padding-bottom:16px;border-top:1px solid #e2e8f0}.resource-dialog .el-dialog__title{font-weight:750;color:#0f172a}.resource-dialog .el-dialog__body{padding-top:12px}.resource-dialog .el-dialog__header{border-bottom:1px solid #e2e8f0;padding-bottom:16px;margin-bottom:8px}</style>
