<script setup lang="ts">
import { ref } from 'vue'
import { ChevronDown, Info } from 'lucide-vue-next'

const open = ref(false)
</script>

<template>
  <div class="w-full text-right lg:fixed lg:right-6 lg:top-24 lg:z-20 lg:max-h-[calc(100vh-8rem)] lg:w-64 lg:overflow-y-auto lg:text-left">
    <button
      type="button"
      class="inline-flex items-center gap-1.5 rounded-md border-2 border-slate-200 bg-white px-2.5 py-1.5 text-xs font-semibold text-slate-600 shadow-mech-sm transition-colors hover:border-brand-accent hover:text-brand-accent"
      :aria-expanded="open"
      aria-controls="retelling-method-steps"
      data-testid="retelling-method-toggle"
      @click="open = !open"
    >
      <Info :size="14" />
      句子复述有问题？
      <ChevronDown
        :size="14"
        class="transition-transform"
        :class="open ? 'rotate-180' : ''"
      />
    </button>

    <div
      v-if="open"
      id="retelling-method-steps"
      class="fixed inset-x-4 bottom-4 z-30 mt-2 max-h-[60vh] overflow-y-auto rounded-md border-2 border-slate-200 bg-white p-3 text-left text-xs leading-5 text-slate-600 shadow-mech-sm lg:static lg:inset-auto lg:z-auto lg:mt-2 lg:max-h-none lg:overflow-visible"
      data-testid="retelling-method-tips"
    >
      <p class="mb-2 font-bold text-slate-800">
        不熟悉的话，可以先用史嘉琳教授的 Echo（回音）法热身：
      </p>
      <ol class="list-decimal space-y-2 pl-4">
        <li>
          <strong class="text-slate-700">第一次 · 回音法：</strong>
          播放原句并专心听；停一下，仔细听脑海里的“回音”；再模仿这个“回音”说出来。
        </li>
        <li>
          <strong class="text-slate-700">第二次 · 独立复述：</strong>
          完整听完一遍后，不用回音法，立刻尝试复述整句。
        </li>
        <li>
          <strong class="text-slate-700">第三次 · 影子跟读：</strong>
          跟着原音频同步朗读，尽量贴近原句的速度。
        </li>
      </ol>
      <p class="mt-2 border-t border-slate-200 pt-2 text-slate-500">
        但最终提交的那一次，仍然要先完整听完一遍原音频，再独立完整地说出整句。
      </p>
    </div>
  </div>
</template>
