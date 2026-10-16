import type { Deck } from '@/types/domain'
import type { DeckTreeResponse, LessonCardsResponse } from '@/types/api'
import { formatBusinessIso } from '@/utils/businessTime'

function mockIso(value: string): string {
  return formatBusinessIso(new Date(value))
}

const mockTree: Deck[] = [
  {
    id: '1',
    name: '新概念英语 2',
    description: '经典教材',
    totalCards: 96,
    newCards: 5,
    reviewCards: 12,
    completedCards: 79,
    type: 'source',
    children: [
      {
        id: '101',
        name: 'Unit 1 - 基础篇',
        description: '',
        totalCards: 48,
        newCards: 3,
        reviewCards: 8,
        completedCards: 37,
        type: 'unit',
        parentId: '1',
        children: [
          {
            id: '1001',
            name: 'Lesson 1 - 句子复述演示',
            description: '',
            totalCards: 6,
            newCards: 2,
            reviewCards: 3,
            completedCards: 1,
            type: 'lesson',
            parentId: '101',
          },
          {
            id: '1002',
            name: 'Lesson 2 - Breakfast or lunch?',
            description: '',
            totalCards: 5,
            newCards: 1,
            reviewCards: 2,
            completedCards: 2,
            type: 'lesson',
            parentId: '101',
          },
        ],
      },
      {
        id: '102',
        name: 'Unit 2 - 进阶篇',
        description: '',
        totalCards: 48,
        newCards: 2,
        reviewCards: 4,
        completedCards: 42,
        type: 'unit',
        parentId: '1',
        children: [
          {
            id: '1003',
            name: 'Lesson 3 - Please send me a card',
            description: '',
            totalCards: 4,
            newCards: 0,
            reviewCards: 2,
            completedCards: 2,
            type: 'lesson',
            parentId: '102',
          },
        ],
      },
    ],
  },
  {
    id: '2',
    name: '雅思听力 第1章',
    description: '剑桥雅思',
    totalCards: 40,
    newCards: 10,
    reviewCards: 0,
    completedCards: 30,
    type: 'source',
    children: [
      {
        id: '201',
        name: 'Section 1',
        description: '',
        totalCards: 20,
        newCards: 5,
        reviewCards: 0,
        completedCards: 15,
        type: 'unit',
        parentId: '2',
        children: [
          {
            id: '2001',
            name: 'Test 1 - Part 1',
            description: '',
            totalCards: 10,
            newCards: 3,
            reviewCards: 0,
            completedCards: 7,
            type: 'lesson',
            parentId: '201',
          },
        ],
      },
    ],
  },
]

export const mockDeckTree: DeckTreeResponse = { tree: mockTree }

export const mockLessonCards: Record<string, LessonCardsResponse> = {
  '1001': {
    lessonId: '1001',
    lessonName: 'Lesson 1 - 句子复述演示',
    cards: [
      {
        id: '2001',
        frontAudio: '/mock/audio/2001-reference.wav',
        backText: 'The quick brown fox jumps over the lazy dog.',
        backTranslation: '这只敏捷的棕色狐狸跳过了懒惰的狗。',
        difficulty: 1,
        cardState: 'learning',
        isNewCard: true,
        lastReviewAt: null,
        dueAt: null,
        grammarInfo: { nouns: ['fox', 'dog'], verbs: ['jumps'] },
      },
      {
        id: '2002',
        frontAudio: '/mock/audio/2002-reference.wav',
        backText: 'Learning a language requires patience and practice.',
        backTranslation: '学习语言需要耐心和练习。',
        difficulty: 2,
        cardState: 'review',
        isNewCard: false,
        lastReviewAt: mockIso('2026-03-21T02:00:00Z'),
        dueAt: mockIso('2026-03-23T01:00:00Z'),
        grammarInfo: {
          nouns: ['language', 'patience', 'practice'],
          verbs: ['requires', 'learning'],
        },
      },
    ],
  },
  '1002': {
    lessonId: '1002',
    lessonName: 'Lesson 2 - Breakfast or lunch?',
    cards: [
      {
        id: '2003',
        frontAudio: '/mock/audio/2003-reference.wav',
        backText: 'It was Sunday and I never get up early on Sundays.',
        backTranslation: '那是星期天，我星期天从不早起。',
        difficulty: 1,
        cardState: 'learning',
        isNewCard: false,
        lastReviewAt: mockIso('2026-03-21T23:30:00Z'),
        dueAt: mockIso('2026-03-22T04:30:00Z'),
        grammarInfo: { nouns: ['sunday', 'sundays'], verbs: ['get'] },
      },
      {
        id: '2004',
        frontAudio: '/mock/audio/2004-reference.wav',
        backText: 'I sometimes stay in bed until lunchtime.',
        backTranslation: '有时候我会在床上待到午饭时间。',
        difficulty: 1,
        cardState: 'relearning',
        isNewCard: false,
        lastReviewAt: mockIso('2026-03-22T00:15:00Z'),
        dueAt: mockIso('2026-03-22T02:15:00Z'),
        grammarInfo: { nouns: ['bed', 'lunchtime'], verbs: ['stay'] },
      },
    ],
  },
  '1003': {
    lessonId: '1003',
    lessonName: 'Lesson 3 - Please send me a card',
    cards: [
      {
        id: '2005',
        frontAudio: '/mock/audio/2005-reference.wav',
        backText: 'Postcards always spoil my holidays.',
        backTranslation: '明信片总是破坏我的假期。',
        difficulty: 2,
        cardState: 'review',
        isNewCard: false,
        lastReviewAt: mockIso('2026-03-20T08:00:00Z'),
        dueAt: mockIso('2026-03-24T01:00:00Z'),
        grammarInfo: { nouns: ['postcards', 'holidays'], verbs: ['spoil'] },
      },
    ],
  },
  '2001': {
    lessonId: '2001',
    lessonName: 'Test 1 - Part 1',
    cards: [
      {
        id: '3001',
        frontAudio: '/mock/audio/3001-reference.wav',
        backText: 'Good morning, I would like to book a room please.',
        backTranslation: '早上好，我想预订一个房间。',
        difficulty: 1,
        cardState: 'learning',
        isNewCard: true,
        lastReviewAt: null,
        dueAt: null,
        grammarInfo: { nouns: ['morning', 'room'], verbs: ['book'] },
      },
    ],
  },
}
