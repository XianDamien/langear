<script setup lang="ts">
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { Play } from 'lucide-vue-next'
import RetroButton from '@/components/ui/RetroButton.vue'
import { useUserCoursesStore } from '@/stores/userCourses'

const router = useRouter()
const userCoursesStore = useUserCoursesStore()
const { userDecks, loading } = storeToRefs(userCoursesStore)

onMounted(() => {
  void userCoursesStore.load()
})

function handlePlayDeck(userDeckId: number) {
  router.push(`/study/decks/${userDeckId}`)
}
</script>

<template>
  <div class="animate-fadeIn">
    <h2 class="mb-6 text-3xl font-bold uppercase text-brand-accent">
      我的课程
    </h2>

    <div
      v-if="loading"
      class="py-20 text-center text-slate-500"
    >
      加载中...
    </div>

    <div
      v-else-if="!userDecks.length"
      class="border-2 border-dashed border-slate-200 p-8 text-center"
    >
      <p class="mb-4 text-slate-500">
        还没有课程
      </p>
      <RetroButton
        variant="primary"
        size="sm"
        @click="router.push('/library')"
      >
        去题库添加
      </RetroButton>
    </div>

    <div
      v-else
      class="space-y-3"
    >
      <div
        v-for="userDeck in userDecks"
        :key="userDeck.id"
        class="flex items-center justify-between border border-slate-200 bg-white p-4 transition-colors hover:border-brand-accent"
      >
        <div class="min-w-0">
          <div class="truncate text-lg font-bold text-slate-900">
            {{ userDeck.title }}
          </div>
          <div class="mt-1 text-sm text-slate-500">
            <span class="font-pixel text-brand-accent">{{ userDeck.new_count }}</span> 新卡 •
            <span class="font-pixel text-brand-accent">{{ userDeck.review_count }}</span> 复习 •
            <span class="font-pixel text-sky-600">{{ userDeck.learning_count }}</span> 学习中 •
            <span class="text-green-600">{{ userDeck.total_count }}</span> 总句数
          </div>
          <div class="mt-1 text-xs uppercase text-slate-400">
            {{ userDeck.scope_type }}
          </div>
        </div>

        <RetroButton
          variant="primary"
          size="sm"
          :icon="Play"
          @click="handlePlayDeck(userDeck.id)"
        >
          开始
        </RetroButton>
      </div>
    </div>
  </div>
</template>
