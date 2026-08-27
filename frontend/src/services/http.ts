import axios from 'axios'
import { ElMessage } from 'element-plus'
import { getUseMockMode } from '@/config/runtimeFlags'
import { installMockAdapter } from './mockAdapter'
import { getAccessToken } from './authToken'
import type { ApiError } from '@/types/api'

const http = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api/v1',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
})

if (getUseMockMode()) {
  installMockAdapter(http)
} else {
  http.interceptors.request.use((config) => {
    const token = getAccessToken()
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  })

  // Unwrap backend { request_id, data } envelope → return inner data
  http.interceptors.response.use(
    (response) => {
      if (response.data && 'request_id' in response.data && 'data' in response.data) {
        response.data = response.data.data
      }
      return response
    },
    (error) => {
      const apiError = extractApiError(error)
      if (!(error.config as { skipErrorMessage?: boolean } | undefined)?.skipErrorMessage) {
        ElMessage.error(apiError.message)
      }
      return Promise.reject(error)
    },
  )
}

export function extractApiError(error: unknown): ApiError {
  const responseData = (error as { response?: { data?: unknown } })?.response?.data as
    | {
        detail?: { error?: Partial<ApiError> }
        error?: Partial<ApiError>
      }
    | undefined

  const detailError = responseData?.detail?.error
  const directError = responseData?.error

  return {
    code: detailError?.code || directError?.code || 'UNKNOWN_ERROR',
    message:
      detailError?.message ||
      directError?.message ||
      (error as { message?: string })?.message ||
      '网络请求失败',
    request_id: detailError?.request_id || directError?.request_id || 'unknown',
  }
}

export default http
