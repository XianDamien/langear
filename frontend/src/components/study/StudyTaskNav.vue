<script setup lang="ts">
import { ref } from 'vue'
import type { Card } from '@/types/domain'

defineProps<{
  cards: Card[]
  currentIndex: number
}>()

const emit = defineEmits<{
  select: [index: number]
}>()

// Read actual media metadata; unknown or failed audio never gets an invented duration.
const durations = ref<Record<string, number>>({})

function readDuration(source: string, event: Event) {
  const duration = (event.target as HTMLAudioElement).duration
  if (Number.isFinite(duration) && duration > 0) durations.value[source] = duration
}

function formatDuration(source?: string) {
  const duration = source ? durations.value[source] : undefined
  return duration ? `${duration.toFixed(2)}s` : '—'
}
</script>

<template>
  <nav class="sentence-nav" aria-label="句子列表" data-testid="study-task-nav">
    <ol class="sentence-timeline">
      <li v-for="(card, index) in cards" :key="card.id" class="sentence-item">
        <audio
          v-if="card.frontAudio"
          :key="card.frontAudio"
          :src="card.frontAudio"
          preload="metadata"
          hidden
          aria-hidden="true"
          @loadedmetadata="readDuration(card.frontAudio, $event)"
          @durationchange="readDuration(card.frontAudio, $event)"
        />
        <button
          type="button"
          class="sentence-button"
          :class="{ 'is-current': index === currentIndex }"
          :aria-current="index === currentIndex ? 'step' : undefined"
          :data-testid="`task-nav-item-${index + 1}`"
          @click="emit('select', index)"
        >
          <span class="sentence-marker" aria-hidden="true">
            <span v-if="index === currentIndex" class="sentence-wave">
              <i /><i /><i />
            </span>
            <span v-else class="sentence-dot" />
          </span>
          <span>第{{ index + 1 }}句 <span class="sentence-duration">— {{ formatDuration(card.frontAudio) }}</span></span>
        </button>
      </li>
    </ol>
  </nav>
</template>

<style scoped>
.sentence-nav {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding: 14px 12px;
}

.sentence-timeline {
  margin: 0;
  padding: 0;
  list-style: none;
}

.sentence-item {
  position: relative;
}

.sentence-item:not(:last-child)::after {
  content: '';
  position: absolute;
  left: 18px;
  top: 30px;
  bottom: -30px;
  width: 1px;
  background: #dedfe2;
  pointer-events: none;
}

.sentence-button {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  min-height: 60px;
  padding: 10px 4px;
  border-radius: 4px;
  color: #475569;
  text-align: left;
  font-size: 14px;
  white-space: nowrap;
  transition: color 150ms;
}

.sentence-button:hover,
.sentence-button.is-current {
  color: #ff4d2d;
}

.sentence-button.is-current {
  font-weight: 600;
}

.sentence-button:focus-visible {
  outline: 2px solid #ff4d2d;
  outline-offset: -2px;
}

.sentence-duration {
  font-variant-numeric: tabular-nums;
}

.sentence-marker {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  width: 28px;
  height: 28px;
}

.sentence-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #dedfe2;
  box-shadow: 0 0 0 4px white;
}

.sentence-wave {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 3px;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: #ff4d2d;
  box-shadow: 0 0 0 3px white;
}

.sentence-wave i {
  width: 3px;
  height: 13px;
  border-radius: 2px;
  background: white;
  animation: sentence-wave 950ms ease-in-out infinite alternate;
}

.sentence-wave i:nth-child(2) {
  animation-delay: -350ms;
}

.sentence-wave i:nth-child(3) {
  animation-delay: -650ms;
}

@keyframes sentence-wave {
  from { transform: scaleY(0.35); }
  to { transform: scaleY(1); }
}

@media (prefers-reduced-motion: reduce) {
  .sentence-wave i { animation: none; }
  .sentence-wave i:nth-child(2) { transform: scaleY(0.5); }
}
</style>
