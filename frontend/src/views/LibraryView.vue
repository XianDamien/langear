<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { ElMessage } from 'element-plus'
import { Plus } from 'lucide-vue-next'
import RetroButton from '@/components/ui/RetroButton.vue'
import { libraryEditorEnabled } from '@/services/libraryContent'
import LibraryContentEditor from '@/components/library/LibraryContentEditor.vue'
import DeckTreeItem from '@/components/library/DeckTreeItem.vue'
import LessonPickerModal from '@/components/library/LessonPickerModal.vue'
import CardPickerModal from '@/components/library/CardPickerModal.vue'
import { useLessonPicker } from '@/composables/useLessonPicker'
import { useContentDecksStore } from '@/stores/contentDecks'
import { resourceError } from '@/services/contentCore'
import { useDeckStore } from '@/stores/deck'
import { useUserCoursesStore } from '@/stores/userCourses'
import { collectLessonIds, findDeckById, getNodeSelectionStatus } from '@/utils/deckSelection'

const coreDecks = useContentDecksStore()
const coreError = ref('')
const libraryDeckTree = computed(() => [
  ...(libraryEditorEnabled ? coreDecks.personalDecks : []),
  ...deckTree.value,
])
async function loadCore() {
  if (!libraryEditorEnabled) return
  coreError.value = ''
  try { await coreDecks.load() } catch (error) { coreError.value = resourceError(error) }
}

const editor = ref<InstanceType<typeof LibraryContentEditor>>()
const cardPicker = ref<InstanceType<typeof CardPickerModal>>()
const deckStore = useDeckStore()
const userCoursesStore = useUserCoursesStore()
const { deckTree, loading } = storeToRefs(deckStore)
const {
  selectedLessonIds,
  selectedLessonIdSet,
  loading: coursesLoading,
  saving,
} = storeToRefs(userCoursesStore)

const pageLoading = computed(() => loading.value || coursesLoading.value || (libraryEditorEnabled && coreDecks.loading))
const {
  pickerDeck,
  pickerLessons,
  pickerSelectedLessonIds,
  openPicker,
  closePicker,
  savePickerSelection,
} = useLessonPicker({
  deckTree,
  selectedLessonIds,
  replaceLessons: userCoursesStore.replaceLessons,
})

onMounted(() => {
  if (!deckTree.value.length) {
    deckStore.load()
  }
  userCoursesStore.load()
  loadCore()
})

async function handleToggleDeckSelection(deckId: string) {
  if (libraryEditorEnabled && coreDecks.personalDecks.some(deck => deck.id === deckId)) {
    const deck = coreDecks.personalDecks.find(row => row.id === deckId)
    if (deck) void cardPicker.value?.show(deck)
    return
  }
  const deck = findDeckById(deckTree.value, deckId)
  if (!deck) return

  if (deck.type === 'lesson') {
    const lessonId = Number(deck.id)
    if (libraryEditorEnabled) void cardPicker.value?.show(deck)
    else if (selectedLessonIdSet.value.has(lessonId)) {
      await userCoursesStore.removeLessons([lessonId])
    } else {
      await userCoursesStore.addLessons([lessonId])
    }
    return
  }

  const status = getNodeSelectionStatus(deck, selectedLessonIdSet.value)
  if (status === 'full') {
    await userCoursesStore.removeLessons(collectLessonIds(deck))
    ElMessage.success('已移除该范围下的所有 lessons')
    return
  }

  openPicker(deckId)
}

async function handlePickerSave(lessonIds: number[]) {
  await savePickerSelection(lessonIds)
  ElMessage.success('我的课程已更新')
}

function handleSelectCards(deckId: string) {
  const deck = findDeckById(deckTree.value, deckId)
  if (deck) {
    void cardPicker.value?.show(deck)
  }
}

async function handleCardsSaved() {
  await Promise.all([userCoursesStore.load(), loadCore()])
  ElMessage.success('课程学习范围已更新')
}
</script>

<template>
  <div class="animate-fadeIn">
    <header class="mb-6 flex flex-wrap items-center justify-between gap-4">
      <h2 class="text-3xl font-bold uppercase text-brand-accent">
        题库资源
      </h2>
      <div
        v-if="libraryEditorEnabled"
        class="flex flex-wrap gap-3"
      >
        <RetroButton
          variant="secondary"
          :icon="Plus"
          @click="editor?.openDeck()"
        >
          添加牌组
        </RetroButton>
        <RetroButton
          :icon="Plus"
          @click="editor?.openCard()"
        >
          添加卡片
        </RetroButton>
      </div>
    </header>
    <LibraryContentEditor
      v-if="libraryEditorEnabled"
      ref="editor"
    />

    <div
      v-if="coreError"
      role="alert"
      class="mb-4 text-amber-700"
    >
      自建牌组加载失败：{{ coreError }}
      <button
        type="button"
        class="underline"
        @click="loadCore"
      >
        重试
      </button>
    </div>
    <div
      v-if="pageLoading"
      class="py-20 text-center text-slate-500"
    >
      加载中...
    </div>

    <div
      v-else
      class="space-y-2"
    >
      <DeckTreeItem
        v-for="deck in libraryDeckTree"
        :key="`${deck.origin || 'legacy'}:${deck.id}`"
        :class="{ 'personal-deck': deck.origin === 'core' }"
        :deck="deck"
        mode="library"
        :selected-lesson-id-set="selectedLessonIdSet"
        :selected-core-deck-ids="coreDecks.joinedIds"
        :selection-disabled="deck.origin === 'core' ? coreDecks.saving : saving"
        :depth="0"
        @toggle-deck-selection="handleToggleDeckSelection"
      />
    </div>

    <LessonPickerModal
      :open="!!pickerDeck"
      :title="pickerDeck ? `${pickerDeck.name} · 选择 lessons` : ''"
      :lessons="pickerLessons"
      :selected-lesson-ids="pickerSelectedLessonIds"
      :saving="saving"
      :allow-card-selection="libraryEditorEnabled"
      @close="closePicker"
      @save="handlePickerSave"
      @select-cards="handleSelectCards"
    />
    <CardPickerModal v-if="libraryEditorEnabled" ref="cardPicker" @saved="handleCardsSaved" />
  </div>
</template>
