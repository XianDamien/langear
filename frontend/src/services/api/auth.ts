import http from '@/services/http'
import type { AxiosRequestConfig } from 'axios'
import type { AuthResponse, CurrentUser } from '@/types/api'

export interface LoginPayload {
  username: string
  password: string
}

export interface RegisterPayload extends LoginPayload {
  email?: string
  invitation_code: string
}

export function login(payload: LoginPayload) {
  return http.post<AuthResponse>('/auth/login', payload)
}

export function register(payload: RegisterPayload) {
  return http.post<AuthResponse>('/auth/register', payload)
}

export function fetchCurrentUser() {
  return http.get<CurrentUser>('/auth/me', { skipErrorMessage: true } as AxiosRequestConfig)
}
