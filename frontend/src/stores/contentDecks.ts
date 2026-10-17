import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { contentResources, libraryContent } from '@/services/libraryContent'
import type { QueueCounts } from '@/services/review'
import type { ResourceCard, ResourceDeck } from '@/services/contentCore'
import type { Deck } from '@/types/domain'

export const useContentDecksStore = defineStore('contentDecks', () => {
  const decks = ref<ResourceDeck[]>([])
  const cards = ref<ResourceCard[]>([])
  const reviewCounts = ref<Record<string, QueueCounts>>({})
  const loading = ref(false)
  const saving = ref(false)
  const joinedIds = computed(() => new Set(decks.value.filter(deck => deck.in_my_courses).map(deck => deck.id)))
  function deckPath(deck: ResourceDeck) {
    const names = [deck.name]
    const visited = new Set([deck.id])
    let parent = deck.parent_id
    while (parent && !visited.has(parent)) {
      visited.add(parent)
      const row = decks.value.find(d => d.id === parent)
      if (!row) break
      names.unshift(row.name)
      parent = row.parent_id
    }
    return names.join(' / ')
  }
  const personalDecks = computed<Deck[]>(() => decks.value
    .filter(d => d.kind === 'standard' && (!d.deck_guid?.startsWith('legacy:') || cards.value.some(c => c.deck_id === d.id)))
    .map(d => ({ id: d.id, name: deckPath(d), origin: 'core', type: 'source', description: '',
      totalCards: cards.value.filter(c => c.deck_id === d.id).length,
      newCards: reviewCounts.value[d.id]?.new_remaining || 0,
      reviewCards: (reviewCounts.value[d.id]?.review_remaining || 0) + (reviewCounts.value[d.id]?.learning_remaining || 0),
      completedCards: 0, reviewCountsAvailable: !!reviewCounts.value[d.id] })))
  const myDecks = computed(() => personalDecks.value.filter(d => joinedIds.value.has(d.id)))
  async function load() {
    loading.value = true
    decks.value = []
    cards.value = []
    try {
      const [rows, cardRows, counts] = await Promise.all([
        contentResources<ResourceDeck>('/decks', 'decks'),
        contentResources<ResourceCard>('/cards', 'cards', { exclude_imported: true }),
        libraryContent.get<{ decks: Record<string, QueueCounts> }>('/review/deck-counts'),
      ])
      decks.value = rows
      cards.value = cardRows
      reviewCounts.value = counts.data.decks
    } finally { loading.value = false }
  }
  async function toggleMembership(id: string) {
    if (saving.value) return
    saving.value = true
    try {
      const { data } = await libraryContent.put<ResourceDeck>(`/decks/${id}/membership`, { joined: !joinedIds.value.has(id) })
      decks.value = decks.value.map(d => d.id === id ? data : d)
      return data.in_my_courses
    } finally { saving.value = false }
  }
  return { decks, cards, reviewCounts, joinedIds, personalDecks, myDecks, loading, saving, deckPath, load, toggleMembership }
})
