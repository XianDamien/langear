<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import { Mic, Send, Square } from 'lucide-vue-next'
import RetroButton from '@/components/ui/RetroButton.vue'
import EnglishMessage from './EnglishMessage.vue'
import type { createDialoguePreview } from './dialogue'

const props = defineProps<{ preview: ReturnType<typeof createDialoguePreview> }>()
const emit = defineEmits<{ close: [] }>()
const anchor = ref<HTMLElement>()
watch(() => props.preview.messages.value.length, async () => {
  await nextTick()
  anchor.value?.scrollIntoView?.({ block: 'nearest', behavior: 'smooth' })
})
</script>

<template>
  <div
    class="space-y-5"
    lang="en"
  >
    <ol
      class="space-y-5"
      aria-label="Conversation"
    >
      <li
        v-for="message in preview.messages.value"
        :key="message.id"
        class="flex items-start gap-2.5"
        :class="message.speaker === 'user' ? 'ml-8 flex-row-reverse' : 'mr-3'"
      >
        <span
          class="flex h-7 w-7 shrink-0 items-center justify-center rounded-md border text-[10px] font-bold"
          :class="message.speaker === 'user' ? 'border-brand-accent/20 bg-red-50 text-brand-accent' : 'border-slate-200 bg-brand-dark text-slate-500'"
          aria-hidden="true"
        >
          {{ message.speaker === 'user' ? 'Y' : message.speaker === 'staff' ? 'S' : 'T' }}
        </span>
        <div class="min-w-0 flex-1">
          <p class="mb-1.5 text-xs text-slate-400">
            {{ message.speaker === 'user' ? 'You' : message.speaker === 'staff' ? 'Theatre staff' : 'Your teacher' }}
          </p>
          <div
            class="rounded-md border p-3.5"
            :class="message.speaker === 'user' ? 'border-brand-accent/15 bg-red-50/50' : 'border-slate-200 bg-brand-dark'"
          >
            <p
              v-if="message.label"
              class="mb-2 text-xs font-semibold text-brand-accent"
            >
              {{ message.label }}
            </p>
            <EnglishMessage
              :english="message.english"
              :chinese="message.chinese"
            />
            <div
              v-if="message.expressions"
              class="mt-4 space-y-3 border-t border-slate-200 pt-3"
            >
              <p class="text-xs font-semibold text-slate-500">
                Try these expressions
              </p>
              <EnglishMessage
                v-for="expression in message.expressions"
                :key="expression.english"
                :english="expression.english"
                :chinese="expression.chinese"
              />
            </div>
          </div>
        </div>
      </li>
    </ol>
    <div ref="anchor" />
    <div
      v-if="preview.page.value === 'refine'"
      class="ml-9"
    >
      <RetroButton
        size="sm"
        class="rounded-md"
        @click="preview.introduceTask"
      >
        Try a real-life task
      </RetroButton>
    </div>
    <div
      v-if="preview.page.value === 'task'"
      class="ml-9 space-y-2"
    >
      <RetroButton
        size="sm"
        class="rounded-md"
        @click="preview.startRoleplay"
      >
        I’m ready. Let’s try!
      </RetroButton>
      <p class="text-xs text-slate-400">
        Your teacher will now play the staff member.
      </p>
    </div>
    <form
      v-if="preview.canReply.value"
      class="sticky bottom-0 space-y-2 border-t border-slate-200 bg-brand-panel pb-1 pt-4"
      @submit.prevent="preview.submit"
    >
      <div class="flex items-center justify-between text-xs text-slate-500">
        <label for="preview-answer">{{ preview.page.value === 'recap' ? 'Your short recap' : 'Your reply' }}</label>
        <button
          type="button"
          class="text-brand-accent hover:underline"
          @click="preview.useSample"
        >
          Use a sample
        </button>
      </div>
      <textarea
        id="preview-answer"
        :value="preview.input.value"
        rows="2"
        class="w-full resize-none rounded-md border border-slate-200 bg-brand-dark px-3 py-2 text-sm leading-6 outline-brand-accent placeholder:text-slate-400"
        placeholder="Type a short answer in English…"
        :disabled="preview.controller.status.value === 'recording'"
        @input="preview.setInput(($event.target as HTMLTextAreaElement).value)"
      />
      <div class="flex flex-wrap items-center justify-between gap-2">
        <button
          type="button"
          class="flex items-center gap-1.5 rounded-md border border-slate-200 px-3 py-2 text-xs text-slate-600 hover:border-brand-accent hover:text-brand-accent"
          @click="preview.controller.status.value === 'recording' ? preview.sendRecording() : preview.record()"
        >
          <Square
            v-if="preview.controller.status.value === 'recording'"
            :size="13"
          /><Mic
            v-else
            :size="14"
          />
          {{ preview.controller.status.value === 'recording' ? 'Send sample voice' : 'Preview voice' }}
        </button>
        <RetroButton
          type="submit"
          size="sm"
          class="rounded-md"
          :disabled="!preview.input.value.trim() || preview.controller.status.value === 'recording'"
        >
          <Send :size="14" /> Send
        </RetroButton>
      </div>
      <p
        v-if="preview.controller.status.value === 'recording'"
        role="status"
        class="text-xs text-brand-accent"
      >
        Voice preview only. No microphone is recording.
      </p>
      <button
        v-if="preview.page.value === 'roleplay'"
        type="button"
        class="text-xs text-slate-400 underline"
        @click="preview.finish"
      >
        Finish here
      </button>
    </form>
    <div
      v-if="preview.page.value === 'failed'"
      class="space-y-3 rounded-md bg-amber-50 p-4"
    >
      <p
        role="alert"
        class="text-sm text-amber-900"
      >
        {{ preview.controller.error.value }}
      </p>
      <RetroButton
        size="sm"
        class="rounded-md"
        @click="preview.controller.connect"
      >
        Reconnect
      </RetroButton>
    </div>
    <div
      v-if="preview.page.value === 'complete'"
      class="flex gap-2 border-t border-slate-200 pt-4"
    >
      <RetroButton
        variant="secondary"
        size="sm"
        class="rounded-md"
        @click="preview.reset"
      >
        Try again
      </RetroButton>
      <RetroButton
        size="sm"
        class="rounded-md"
        @click="emit('close')"
      >
        Done
      </RetroButton>
    </div>
  </div>
</template>
