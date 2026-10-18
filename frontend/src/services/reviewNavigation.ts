import { reviewHttp } from './review'

export async function legacyReviewLocation(lessonId: string) {
  const { data } = await reviewHttp.get<{ deck_id: string }>(`/review/legacy-lessons/${encodeURIComponent(lessonId)}`)
  return { name: 'DeckReview', params: { deckId: data.deck_id } }
}
