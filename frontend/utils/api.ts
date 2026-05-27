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

export async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
  token?: string,
): Promise<T> {
  const config = useRuntimeConfig()
  const baseUrl = config.public.apiUrl

  // For FormData bodies, let the browser set Content-Type (includes multipart boundary).
  // Callers can pass headers: {} to suppress the default JSON content type.
  const isFormData = options.body instanceof FormData
  const defaultHeaders: Record<string, string> = isFormData
    ? {}
    : { 'Content-Type': 'application/json' }

  const headers: Record<string, string> = {
    ...defaultHeaders,
    ...(options.headers as Record<string, string> || {}),
  }

  // Auto-inject token from localStorage if not provided in headers
  if (!headers['Authorization'] && !headers['authorization']) {
    const storedToken = token || (process.client ? localStorage.getItem('auth_token') : null)
    if (storedToken) {
      headers['Authorization'] = `Bearer ${storedToken}`
    }
  }

  const response = await fetch(`${baseUrl}${path}`, {
    ...options,
    headers,
  })

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
