<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { ElMessage } from 'element-plus'
import DeckTreeItem from '@/components/library/DeckTreeItem.vue'
import LibraryContentEditor from '@/components/library/LibraryContentEditor.vue'
import RetroButton from '@/components/ui/RetroButton.vue'
import { useDecksStore } from '@/stores/decks'
import type { DeckView } from '@/stores/decks'
import { deleteDeck, fetchDeletePreview, resourceError, type DeletePreview } from '@/services/content'
import { extractApiError } from '@/services/coreApi'

const route = useRoute()
const router = useRouter()
const decksStore = useDecksStore()
const { myCoursesTree, loading } = storeToRefs(decksStore)
const error = ref('')
const editor = ref<InstanceType<typeof LibraryContentEditor>>()
const removal = ref<{ deckId: string; deckName: string; preview: DeletePreview } | null>(null)
const removing = ref(false)
const removalError = ref('')

const notice = computed(() => {
  switch (route.query.notice) {
    case 'legacy-link-invalid':
      return '旧链接已失效，已返回我的课程。'
    case 'invalid-deck':
      return '该课程链接无效。'
    case 'invalid-card':
      return '该卡片链接无效。'
    default:
      return ''
  }
})

async function load() {
  error.value = ''
  try {
    await decksStore.load()
  } catch (cause) {
    error.value = resourceError(cause)
  }
}

onMounted(load)

function findDeck(nodes: DeckView[], deckId: string): DeckView | null {
  for (const node of nodes) {
    if (node.id === deckId) return node
    const found = findDeck(node.children, deckId)
    if (found) return found
  }
  return null
}

function firstJoinedLesson(deck: DeckView): string | null {
  if (!deck.children.length) return deck.inMyCourses ? deck.id : null
  for (const child of deck.children) {
    const found = firstJoinedLesson(child)
    if (found) return found
  }
  return null
}

function handlePlayDeck(deckId: string) {
  const deck = findDeck(myCoursesTree.value, deckId)
  const target = deck && !deck.inMyCourses ? firstJoinedLesson(deck) : deckId
  void router.push({ name: 'DeckReview', params: { deckId: target ?? deckId } })
}

function handleEditDeckSettings(deckId: string) {
  void router.push({ name: 'Settings', query: { deck_id: deckId } })
}

async function handleRemoveDeck(deckId: string) {
  removalError.value = ''
  error.value = ''
  try {
    const { data } = await fetchDeletePreview(deckId)
    const deck = findDeck(myCoursesTree.value, deckId)
    removal.value = { deckId, deckName: deck?.name ?? '这门课程', preview: data }
  } catch (cause) {
    error.value = resourceError(cause)
  }
}

function cancelRemoval() {
  removal.value = null
  removalError.value = ''
}

async function confirmRemoval() {
  const pending = removal.value
  if (!pending || removing.value) return
  removing.value = true
  removalError.value = ''
  try {
    await deleteDeck(pending.deckId, pending.preview.confirmation_token)
    removal.value = null
    await decksStore.load()
    ElMessage.success('个人副本已删除，共享题库内容未受影响')
  } catch (cause) {
    // A changed impact invalidates the signed token; fetch a fresh preview so
    // the learner sees the new scope instead of retrying a stale confirmation.
    if (extractApiError(cause).code === 'DELETION_IMPACT_CHANGED') {
      removalError.value = '课程内容已变化，已刷新影响范围，请重新确认。'
      try {
        const { data } = await fetchDeletePreview(pending.deckId)
        removal.value = { deckId: pending.deckId, deckName: pending.deckName, preview: data }
      } catch (refreshCause) {
        error.value = resourceError(refreshCause)
        removal.value = null
      }
    } else {
      removalError.value = resourceError(cause)
    }
  } finally {
    removing.value = false
  }
}

async function handleContentChanged() {
  await decksStore.load()
}
</script>

<template>
  <div class="animate-fadeIn">
    <header class="mb-6 flex flex-wrap items-center justify-between gap-4">
      <h2 class="text-3xl font-bold uppercase text-brand-accent">
        我的课程
      </h2>
      <div class="flex gap-2">
        <RetroButton
          variant="secondary"
          size="sm"
          @click="editor?.openDeck()"
        >
          添加牌组
        </RetroButton>
        <RetroButton
          size="sm"
          @click="editor?.openCard()"
        >
          添加卡片
        </RetroButton>
      </div>
    </header>
    <LibraryContentEditor
      ref="editor"
      @created="handleContentChanged"
    />

    <p
      v-if="notice"
      role="status"
      class="mb-4 border border-slate-200 bg-white p-3 text-sm text-slate-600"
    >
      {{ notice }}
    </p>
    <div
      v-if="error"
      role="alert"
      class="mb-4 text-amber-700"
    >
      {{ error }}
      <button
        type="button"
        class="underline"
        @click="load"
      >
        重试
      </button>
    </div>
    <div
      v-if="loading"
      class="py-20 text-center text-slate-500"
    >
      加载中...
    </div>

    <div
      v-else-if="!myCoursesTree.length && !error"
      class="border-2 border-dashed border-slate-200 p-8 text-center"
    >
      <p class="mb-4 text-slate-500">
        你还没有加入任何课程。去题库资源挑选一些牌组吧。
      </p>
      <RetroButton
        variant="primary"
        size="sm"
        @click="router.push('/library')"
      >
        去题库资源添加课程
      </RetroButton>
    </div>

    <div
      v-else
      class="space-y-2"
    >
      <DeckTreeItem
        v-for="deck in myCoursesTree"
        :key="deck.id"
        :deck="deck"
        mode="my-courses"
        :depth="0"
        :selection-disabled="removing"
        @play-deck="handlePlayDeck"
        @edit-deck-settings="handleEditDeckSettings"
        @remove-deck="handleRemoveDeck"
      />
    </div>

    <div
      v-if="removal"
      class="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="remove-copy-title"
    >
      <div class="w-full max-w-lg border-2 border-slate-900 bg-white p-6 shadow-mech">
        <h3
          id="remove-copy-title"
          class="mb-3 text-lg font-bold text-slate-900"
        >
          删除「{{ removal.deckName }}」的个人副本？
        </h3>
        <p class="mb-3 text-sm leading-6 text-slate-600">
          将删除 {{ removal.preview.impact.decks_deleted }} 个牌组、{{
            removal.preview.impact.notes_deleted
          }} 条内容、{{ removal.preview.impact.cards_deleted }} 张卡片和 {{
            removal.preview.impact.attempts_deleted
          }} 条复习记录。共享题库不受影响，之后仍可重新加入。
        </p>
        <p
          v-if="removalError"
          role="alert"
          class="mb-3 text-sm text-amber-700"
        >
          {{ removalError }}
        </p>
        <div class="flex justify-end gap-3">
          <RetroButton
            variant="secondary"
            size="sm"
            :disabled="removing"
            @click="cancelRemoval"
          >
            取消
          </RetroButton>
          <RetroButton
            variant="primary"
            size="sm"
            :disabled="removing"
            @click="confirmRemoval"
          >
            {{ removing ? '删除中…' : '删除副本' }}
          </RetroButton>
        </div>
      </div>
    </div>
  </div>
</template>
