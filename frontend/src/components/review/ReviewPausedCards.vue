<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { reviewHttp, reviewError } from '@/services/review'
import { templateLabels } from '@/services/content'
import RetroButton from '@/components/ui/RetroButton.vue'
const props = defineProps<{ deckId: string }>()
const emit = defineEmits<{ close: []; changed: [] }>()
const rows = ref<{ id: string; front: Record<string, string>; card_template_key: string; queue: string; card_schedule_revision: number }[]>([])
const busy = ref(false)
const error = ref('')
async function load() {
  busy.value = true
  error.value = ''
  try { rows.value = (await reviewHttp.get('/review/paused-cards', { params: { deck_id: props.deckId } })).data.cards }
  catch (cause) { error.value = reviewError(cause) }
  finally { busy.value = false }
}
async function restore(row: typeof rows.value[number]) {
  busy.value = true
  error.value = ''
  try {
    await reviewHttp.post(`/cards/${row.id}/schedule`, { action: row.queue === 'suspended' ? 'unsuspend' : 'unbury', card_schedule_revision: row.card_schedule_revision })
    emit('changed')
    await load()
  } catch (cause) { error.value = reviewError(cause) }
  finally { busy.value = false }
}
onMounted(load)
</script>
<template>
  <div
    class="fixed inset-0 z-30 flex items-center justify-center bg-black/30 p-4"
    @click.self="!busy && emit('close')"
  >
    <section
      role="dialog"
      aria-modal="true"
      aria-labelledby="paused-cards-title"
      class="max-h-[80dvh] w-full max-w-xl space-y-4 overflow-auto rounded border border-slate-200 bg-brand-panel p-5 shadow-mech"
    >
      <div class="flex items-center justify-between gap-3">
        <h2
          id="paused-cards-title"
          class="font-bold"
        >
          暂停和今日跳过
        </h2><RetroButton
          size="sm"
          variant="ghost"
          :disabled="busy"
          @click="emit('close')"
        >
          关闭
        </RetroButton>
      </div>
      <p class="text-xs text-slate-500">
        今日跳过的卡片会在下一个学习日自动恢复。暂停的卡片需手动恢复。
      </p>
      <p
        v-if="error"
        role="alert"
      >
        {{ error }} <button
          :disabled="busy"
          type="button"
          class="underline"
          @click="load"
        >
          重新加载
        </button>
      </p>
      <p
        v-if="busy"
        role="status"
      >
        处理中…
      </p>
      <p
        v-else-if="!rows.length && !error"
        class="text-sm text-slate-500"
      >
        没有暂停或跳过的卡片。
      </p>
      <div
        v-for="row in rows"
        :key="row.id"
        class="flex items-center justify-between gap-3 border-t border-slate-200 py-3 text-sm"
      >
        <div class="min-w-0">
          <p class="truncate">
            {{ row.front.word || row.front.meaning || row.front.chinese || templateLabels[row.card_template_key] }}
          </p><p class="text-xs text-slate-500">
            {{ row.queue === 'suspended' ? '已暂停' : row.queue === 'buried_sibling' ? '兄弟卡今日隐藏' : '今日已跳过' }}
          </p>
        </div>
        <RetroButton
          size="sm"
          :disabled="busy"
          @click="restore(row)"
        >
          恢复
        </RetroButton>
      </div>
    </section>
  </div>
</template>
