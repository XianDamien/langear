import type { AxiosRequestConfig, AxiosResponse } from 'axios'
import OSS from 'ali-oss'
import http from '../http'
import { normalizeOssRegion } from '@/services/ossRegion'
import type {
  SubmitReviewRequest,
  SubmitReviewResponseAsync,
  PollingResponse,
  STSToken,
  SubmitRatingRequest,
  SubmitRatingResponse,
  StudySessionResponse,
  StudySubmissionListItem,
} from '@/types/api'

const silentErrorRequestConfig = {
  skipErrorMessage: true,
} as AxiosRequestConfig

export function getSTSToken() {
  return http.get<STSToken>('/oss/sts-token')
}

/**
 * Generate a signed URL for an OSS audio path via STS credentials.
 * Used for user recordings playback when blob URL is unavailable.
 */
export async function getOSSSignedUrl(ossPath: string): Promise<string> {
  const { data: sts } = await getSTSToken()
  const client = new OSS({
    region: normalizeOssRegion(sts.region),
    accessKeyId: sts.access_key_id,
    accessKeySecret: sts.access_key_secret,
    stsToken: sts.security_token,
    bucket: sts.bucket,
    secure: true,
  })
  return client.signatureUrl(ossPath, { expires: 3600 })
}

export function submitReviewAsync(
  payload: SubmitReviewRequest,
): Promise<AxiosResponse<SubmitReviewResponseAsync>> {
  return http.post<SubmitReviewResponseAsync>(
    '/study/submissions',
    payload,
    silentErrorRequestConfig,
  )
}

export function fetchStudySession(params?: { sourceScope?: number[]; lessonId?: number }) {
  return fetchStudySessionWithScope(params)
}

export function fetchStudySessionWithScope(params?: {
  sourceScope?: number[]
  lessonId?: number
  userDeckId?: number
}) {
  return http.get<StudySessionResponse>('/study/session', {
    params: {
      ...(params?.sourceScope?.length ? { source_scope: params.sourceScope.join(',') } : {}),
      ...(params?.lessonId ? { lesson_id: params.lessonId } : {}),
      ...(params?.userDeckId ? { user_deck_id: params.userDeckId } : {}),
    },
  })
}

export function submitRating(submissionId: number, payload: SubmitRatingRequest) {
  return http.post<SubmitRatingResponse>(`/study/submissions/${submissionId}/rating`, payload)
}

export function pollSubmissionResult(submissionId: number) {
  return http.get<PollingResponse>(`/study/submissions/${submissionId}`)
}

export function listStudySubmissions(params: { lesson_id?: number; user_deck_id?: number; card_id?: number }) {
  return http.get<StudySubmissionListItem[]>('/study/submissions', { params })
}
