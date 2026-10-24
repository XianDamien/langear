<script setup lang="ts">
import { computed, watch } from 'vue'
import { useRoute } from 'vue-router'
import { storeToRefs } from 'pinia'
import { useSettingsStore } from '@/stores/settings'
import RetroCard from '@/components/ui/RetroCard.vue'
import RetroButton from '@/components/ui/RetroButton.vue'

const settingsStore = useSettingsStore()
const route = useRoute()
const { desiredRetention, learningSteps, relearningSteps, maximumInterval, defaultDeckScope, saving, loading, loadError, saveError } =
  storeToRefs(settingsStore)
const { deckId, deckTitle, dailyNewLimit, dailyReviewLimit, schedulingEnabled } = storeToRefs(settingsStore)
const coreDeck = computed(() => deckId.value !== undefined)
const { newCardGatherOrder, newCardSortOrder, effectiveNewCardGatherOrder, effectiveNewCardSortOrder } = storeToRefs(settingsStore)
function orderPreset(gather: string | null | undefined, sort: string | null | undefined) {
  if (gather == null && sort == null) return 'inherit'
  if (gather === 'lowest_position' && sort === 'order_gathered') return 'source'
  if (gather === 'random_cards' && sort === 'order_gathered') return 'random'
  return 'custom'
}
const newCardOrder = computed({
  get: () => orderPreset(newCardGatherOrder.value, newCardSortOrder.value),
  set: (value: string) => {
    if (value === 'custom') return
    newCardGatherOrder.value = value === 'inherit' ? null : value === 'source' ? 'lowest_position' : 'random_cards'
    newCardSortOrder.value = value === 'inherit' ? null : 'order_gathered'
  },
})
const effectiveOrderLabel = computed(() => {
  const preset = orderPreset(effectiveNewCardGatherOrder.value, effectiveNewCardSortOrder.value)
  return preset === 'source' ? '按课文／添加顺序' : preset === 'random' ? '随机' : preset === 'custom' ? '自定义排序' : '上级设置'
})
const retentionPercent = computed({
  get: () => Number((desiredRetention.value * 100).toFixed(4)),
  set: (value: number) => { desiredRetention.value = value / 100 },
})

function loadSettings() {
  const raw = route.query.deck_id
  const value = Array.isArray(raw) ? raw[0] : raw
  return settingsStore.load(value || undefined)
}
watch(() => route.query.deck_id, loadSettings, { immediate: true })

async function handleSave() {
  await settingsStore.save()
}
</script>

<template>
  <div class="animate-fadeIn max-w-xl mx-auto">
    <h2 class="text-3xl font-bold mb-6 text-brand-accent uppercase">
      {{ deckId ? deckTitle + ' · 设置' : '设置' }}
    </h2>

    <RouterLink v-if="route.query.deck_id" to="/my-courses" class="mb-4 inline-block text-sm text-brand-accent underline">
      返回我的课程
    </RouterLink>
    <p class="mb-6 text-sm text-slate-500">
      {{ route.query.deck_id ? '仅调整你在此牌组中的学习设置，不影响其他用户。子牌组未单独设置时继承此配置。' : '当前账号的默认设置。单个牌组的设置请从「我的课程」进入。' }}
    </p>

    <div
      v-if="loading"
      class="text-center text-slate-500 py-20"
    >
      加载中...
    </div>

    <div v-else-if="loadError" role="alert" class="border border-amber-400 p-4">
      <p>{{ loadError }}</p>
      <button type="button" class="mt-3 underline" @click="loadSettings">重试</button>
    </div>

    <template v-else>
      <p
        v-if="schedulingEnabled === false"
        class="mb-4 text-sm text-slate-500"
        role="status"
      >
        设置可保存；此牌组的评分与复习调度尚未启用，启用后将按此配置安排学习。
      </p>
      <RetroCard class="space-y-6">
        <form class="space-y-6" @submit.prevent="handleSave">
          <div>
            <label for="daily-new-limit" class="block text-sm font-bold text-slate-500 mb-2">
              {{ deckId ? '每日新学数量' : '每日新学数量（账号默认）' }}
            </label>
            <input id="daily-new-limit" v-model.number="dailyNewLimit" type="number" min="0" max="10000" step="1" required class="w-full border border-slate-200 p-2 text-slate-900 outline-none focus:border-brand-accent">
            <p class="mt-2 text-xs text-slate-500">
              {{ deckId
                ? '此牌组每日新卡额度；实际可用数量仍受上级课程与账号总额度限制。'
                : '整个账号的每日新卡总额度，默认 9999（相当于不限制）。单个牌组可另外下调。' }}
            </p>
          </div>
          <div>
            <label for="daily-review-limit" class="block text-sm font-bold text-slate-500 mb-2">
              {{ deckId ? '每日复习数量' : '每日复习数量（账号默认）' }}
            </label>
            <input id="daily-review-limit" v-model.number="dailyReviewLimit" type="number" min="0" max="10000" step="1" required class="w-full border border-slate-200 p-2 text-slate-900 outline-none focus:border-brand-accent">
            <p v-if="!deckId" class="mt-2 text-xs text-slate-500">每天最多安排的复习卡数量。</p>
          </div>
          <template v-if="deckId">
            <div>
              <label
                for="new-card-order"
                class="block text-sm font-bold text-slate-500 mb-2"
              >新卡出现顺序</label>
              <select
                id="new-card-order"
                v-model="newCardOrder"
                class="w-full border border-slate-200 p-2 text-slate-900 bg-white outline-none focus:border-brand-accent"
              >
                <option value="source">
                  按课文／添加顺序
                </option>
                <option value="random">
                  随机
                </option>
                <option value="inherit">
                  继承上级设置
                </option>
                <option
                  v-if="newCardOrder === 'custom'"
                  value="custom"
                >
                  保留当前自定义排序
                </option>
              </select>
              <p
                v-if="newCardOrder === 'inherit'"
                class="mt-2 text-xs text-slate-500"
              >
                当前生效：{{ effectiveOrderLabel }}
              </p>
              <p class="mt-2 text-xs text-slate-500">
                仅影响尚未学习的新卡，复习卡仍按复习计划出现。保存后重新进入练习生效。
              </p>
            </div>
          </template>
          <div>
            <label for="desired-retention" class="block text-sm font-bold uppercase text-slate-500 mb-2">
              目标保留率（%）
            </label>
            <input
              id="desired-retention"
              v-model.number="retentionPercent"
              type="number"
              :min="70"
              :max="99"
              step="0.1"
              required
              class="w-full border border-slate-200 p-2 text-slate-900 font-sans focus:border-brand-accent outline-none"
            >
          </div>

          <div v-if="!coreDeck">
            <label for="maximum-interval" class="block text-sm font-bold uppercase text-slate-500 mb-2">
              最大复习间隔（天）
            </label>
            <input
              id="maximum-interval"
              v-model.number="maximumInterval"
              :max="deckId ? 36500 : undefined"
              type="number"
              min="1"
              step="1"
              required
              class="w-full border border-slate-200 p-2 text-slate-900 font-sans focus:border-brand-accent outline-none"
            >
          </div>

          <div v-if="!coreDeck">
            <label for="learning-steps" class="block text-sm font-bold text-slate-500 mb-2">学习步长（分钟）</label>
            <input id="learning-steps" v-model.trim="learningSteps" type="text" placeholder="例如 1,15；留空表示无步长" class="w-full border border-slate-200 p-2 text-slate-900 outline-none focus:border-brand-accent">
          </div>
          <div v-if="!coreDeck">
            <label for="relearning-steps" class="block text-sm font-bold text-slate-500 mb-2">重学步长（分钟）</label>
            <input id="relearning-steps" v-model.trim="relearningSteps" type="text" placeholder="例如 15；留空表示无步长" class="w-full border border-slate-200 p-2 text-slate-900 outline-none focus:border-brand-accent">
          </div>

          <div v-if="!deckId">
            <label for="default-deck-scope" class="block text-sm font-bold uppercase text-slate-500 mb-2">
              默认牌组范围
            </label>
            <input
              id="default-deck-scope"
              v-model.trim="defaultDeckScope"
              type="text"
              placeholder="留空表示全部，或填写牌组 UUID，逗号分隔"
              class="w-full border border-slate-200 p-2 text-slate-900 font-sans focus:border-brand-accent outline-none bg-white"
            >
          </div>

          <p v-if="saveError" role="alert" class="text-sm text-red-600">{{ saveError }}</p>
          <RetroButton
            type="submit"
            variant="primary"
            class="w-full"
            :disabled="saving"
          >
            {{ saving ? '保存中...' : '保存设置' }}
          </RetroButton>
        </form>
      </RetroCard>
    </template>
  </div>
</template>
