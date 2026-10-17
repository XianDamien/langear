export type DiffStatus = 'match' | 'replace' | 'remove' | 'add'

export interface DiffTokenView {
  raw: string
  normalized: string
  index: number
  status: DiffStatus
}

export interface TranscriptDiffRows {
  original: DiffTokenView[]
  transcript: DiffTokenView[]
  counts: {
    changed: number
    removed: number
    added: number
    replaced: number
  }
}

interface Token {
  raw: string
  normalized: string
  index: number
}

interface DiffOperation {
  type: 'match' | 'remove' | 'add'
  original?: Token
  transcript?: Token
}

function normalizeToken(raw: string): string {
  const trimmed = raw.trim().toLowerCase()
  const cleaned = trimmed.replace(/^[^a-z0-9']+|[^a-z0-9']+$/g, '')
  return cleaned || trimmed
}

function tokenize(text: string, strict: boolean): Token[] {
  if (strict) {
    return (text.match(/\s+|[\p{L}\p{N}]+|[^\s\p{L}\p{N}]/gu) || []).map((raw, index) => ({
      raw, normalized: raw, index,
    }))
  }
  return text
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .map((raw, index) => ({
      raw,
      normalized: normalizeToken(raw),
      index,
    }))
}

function diffTokens(original: Token[], transcript: Token[]): DiffOperation[] {
  const rows = original.length + 1
  const cols = transcript.length + 1
  const dp = Array.from({ length: rows }, () => Array<number>(cols).fill(0))

  for (let i = original.length - 1; i >= 0; i -= 1) {
    for (let j = transcript.length - 1; j >= 0; j -= 1) {
      dp[i]![j] =
        original[i]!.normalized === transcript[j]!.normalized
          ? dp[i + 1]![j + 1]! + 1
          : Math.max(dp[i + 1]![j]!, dp[i]![j + 1]!)
    }
  }

  const operations: DiffOperation[] = []
  let i = 0
  let j = 0

  while (i < original.length && j < transcript.length) {
    if (original[i]!.normalized === transcript[j]!.normalized) {
      operations.push({
        type: 'match',
        original: original[i],
        transcript: transcript[j],
      })
      i += 1
      j += 1
      continue
    }

    if (dp[i + 1]![j]! >= dp[i]![j + 1]!) {
      operations.push({
        type: 'remove',
        original: original[i],
      })
      i += 1
      continue
    }

    operations.push({
      type: 'add',
      transcript: transcript[j],
    })
    j += 1
  }

  while (i < original.length) {
    operations.push({
      type: 'remove',
      original: original[i],
    })
    i += 1
  }

  while (j < transcript.length) {
    operations.push({
      type: 'add',
      transcript: transcript[j],
    })
    j += 1
  }

  return operations
}

export function buildTranscriptDiff(
  originalText: string,
  transcriptText: string,
  strict = false,
): TranscriptDiffRows {
  const originalTokens = tokenize(originalText, strict)
  const transcriptTokens = tokenize(transcriptText, strict)
  const operations = diffTokens(originalTokens, transcriptTokens)

  const original: DiffTokenView[] = []
  const transcript: DiffTokenView[] = []
  const counts = {
    changed: 0,
    removed: 0,
    added: 0,
    replaced: 0,
  }

  for (let index = 0; index < operations.length; index += 1) {
    const current = operations[index]!
    const next = operations[index + 1]

    if (
      (current.type === 'remove' && next?.type === 'add') ||
      (current.type === 'add' && next?.type === 'remove')
    ) {
      const removal = current.type === 'remove' ? current : next
      const addition = current.type === 'add' ? current : next

      original.push({
        raw: removal!.original!.raw,
        normalized: removal!.original!.normalized,
        index: removal!.original!.index,
        status: 'replace',
      })
      transcript.push({
        raw: addition!.transcript!.raw,
        normalized: addition!.transcript!.normalized,
        index: addition!.transcript!.index,
        status: 'replace',
      })
      counts.changed += 1
      counts.replaced += 1
      index += 1
      continue
    }

    if (current.type === 'match') {
      original.push({
        raw: current.original!.raw,
        normalized: current.original!.normalized,
        index: current.original!.index,
        status: 'match',
      })
      transcript.push({
        raw: current.transcript!.raw,
        normalized: current.transcript!.normalized,
        index: current.transcript!.index,
        status: 'match',
      })
      continue
    }

    if (current.type === 'remove') {
      original.push({
        raw: current.original!.raw,
        normalized: current.original!.normalized,
        index: current.original!.index,
        status: 'remove',
      })
      counts.changed += 1
      counts.removed += 1
      continue
    }

    transcript.push({
      raw: current.transcript!.raw,
      normalized: current.transcript!.normalized,
      index: current.transcript!.index,
      status: 'add',
    })
    counts.changed += 1
    counts.added += 1
  }

  return {
    original,
    transcript,
    counts,
  }
}
