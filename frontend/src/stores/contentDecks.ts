import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { contentResources, libraryContent } from '@/services/libraryContent'
import type { ResourceCard, ResourceDeck } from '@/services/contentCore'
import type { Deck } from '@/types/domain'

export const useContentDecksStore = defineStore('contentDecks', () => {
  const decks = ref<ResourceDeck[]>([])
  const cards = ref<ResourceCard[]>([])
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
      newCards: 0, reviewCards: 0, completedCards: 0 })))
  const myDecks = computed(() => personalDecks.value.filter(d => joinedIds.value.has(d.id)))
  async function load() {
    loading.value = true
    decks.value = []
    cards.value = []
    try {
      const [rows, cardRows] = await Promise.all([
        contentResources<ResourceDeck>('/decks', 'decks'),
        contentResources<ResourceCard>('/cards', 'cards', { exclude_imported: true }),
      ])
      decks.value = rows
      cards.value = cardRows
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
  return { decks, cards, joinedIds, personalDecks, myDecks, loading, saving, deckPath, load, toggleMembership }
})
