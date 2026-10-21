<script setup lang="ts">
import { provide, ref } from 'vue'
import { RotateCcw, Smartphone, Monitor } from 'lucide-vue-next'
import DialogueModal from '@/components/dialogue/DialogueModal.vue'
import RetroButton from '@/components/ui/RetroButton.vue'
import DialoguePreviewConversation from '@/preview/DialoguePreviewConversation.vue'
import { dialogueControllerKey } from '@/composables/useDialogue'
import { createDialoguePreview, previewEntry, previewStates, type PreviewPage } from '@/preview/dialogue'

const preview = createDialoguePreview()
provide(dialogueControllerKey, () => preview.controller)
const open = ref(true)
const narrow = ref(false)
function select(state: PreviewPage) {
  preview.show(state)
}
function reopen() {
  select('recap')
  open.value = true
}
</script>

<template>
  <div class="flex min-h-dvh items-center justify-center bg-brand-dark p-4 text-slate-900">
    <RetroButton
      v-if="!open"
      class="rounded-md"
      @click="reopen"
    >
      打开对话预览
    </RetroButton>
    <DialogueModal
      v-if="open"
      class="dialogue-preview"
      :entry="previewEntry"
      :confirm-on-close="false"
      close-label="关闭"
      :style="narrow ? { width: '390px', maxWidth: '94vw' } : undefined"
      @close="open = false"
    >
      <template #preview-controls>
        <div class="border-b border-slate-200 bg-brand-dark px-4 py-3">
          <div class="mb-2 flex items-center justify-between gap-3">
            <span class="text-[11px] font-semibold text-slate-500">界面预览 · 脚本回复 · 无实时音频</span>
            <div class="flex gap-1">
              <button
                class="rounded-md border border-slate-200 bg-brand-panel p-1.5 text-slate-600 hover:border-brand-accent hover:text-brand-accent"
                :aria-label="narrow ? '切换桌面宽度' : '切换手机宽度'"
                :aria-pressed="narrow"
                @click="narrow = !narrow"
              >
                <Monitor
                  v-if="narrow"
                  :size="15"
                /><Smartphone
                  v-else
                  :size="15"
                />
              </button>
              <button
                class="rounded-md border border-slate-200 bg-brand-panel p-1.5 text-slate-600 hover:border-brand-accent hover:text-brand-accent"
                aria-label="重置预览"
                @click="select('recap')"
              >
                <RotateCcw :size="15" />
              </button>
            </div>
          </div>
          <label class="flex items-center gap-2 text-xs text-slate-600">
            预览
            <select
              :value="preview.page.value"
              class="min-w-0 flex-1 rounded-md border border-slate-200 bg-brand-panel px-2 py-1.5 text-xs outline-brand-accent outline-offset-2"
              @change="select(($event.target as HTMLSelectElement).value as PreviewPage)"
            >
              <option
                v-for="state in previewStates"
                :key="state.value"
                :value="state.value"
              >{{ state.label }}</option>
            </select>
          </label>
        </div>
      </template>
      <template #heading>
        <h2
          id="dialogue-title"
          class="sr-only"
        >
          情景对话
        </h2>
      </template>
      <template #content>
        <DialoguePreviewConversation
          :preview="preview"
          @close="open = false"
        />
      </template>
    </DialogueModal>
  </div>
</template>

<style scoped>
:deep(.dialogue-preview::backdrop) {
  background: transparent;
}
</style>
