/**
 * API utility for communicating with the FastAPI backend.
 */

import type { ErrorResponse } from '~/types'

export class ApiError extends Error {
  constructor(
    public readonly errorCode: string,
    message: string,
    public readonly timestamp: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

/** Clear auth state and redirect to login on token expiry */
function handleUnauthorized() {
  if (!process.client) return
  localStorage.removeItem('auth_token')
  localStorage.removeItem('user_id')
  try {
    const { useAuthStore } = require('~/stores/auth')
    const auth = useAuthStore()
    auth.logout()
  } catch { /* ignore if store not available */ }
  // Use window.location for hard redirect to avoid stale Nuxt state
  window.location.href = '/login?reason=session_expired'
}

export async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
  token?: string,
): Promise<T> {
  const config = useRuntimeConfig()
  const baseUrl = config.public.apiUrl

  // For FormData bodies, let the browser set Content-Type (includes multipart boundary).
  const isFormData = options.body instanceof FormData
  const defaultHeaders: Record<string, string> = isFormData
    ? {}
    : { 'Content-Type': 'application/json' }

  const headers: Record<string, string> = {
    ...defaultHeaders,
    ...(options.headers as Record<string, string> || {}),
  }

  // Auto-inject token from localStorage
  if (!headers['Authorization'] && !headers['authorization']) {
    const storedToken = token
      || (process.client ? localStorage.getItem('auth_token') : null)
    if (storedToken) {
      headers['Authorization'] = `Bearer ${storedToken}`
    }
  }

  const response = await fetch(`${baseUrl}${path}`, {
    ...options,
    headers,
  })

  // Handle token expiry — clear auth and redirect to login
  if (response.status === 401) {
    handleUnauthorized()
    throw new ApiError(
      'UNAUTHORIZED',
      'Sessao expirada. Faca login novamente.',
      new Date().toISOString(),
    )
  }

  if (!response.ok) {
    let error: ErrorResponse
    try {
      error = await response.json()
    } catch {
      error = {
        error_code: `HTTP_${response.status}`,
        message: `Erro ${response.status}: ${response.statusText}`,
        timestamp: new Date().toISOString(),
      }
    }
    throw new ApiError(error.error_code, error.message, error.timestamp)
  }

  return response.json() as Promise<T>
}
