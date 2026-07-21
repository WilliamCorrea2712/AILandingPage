import { defineStore } from 'pinia'

// Decode JWT payload without verifying signature (client-side only)
function decodeJwtExpiry(token: string): number | null {
  try {
    const payload = JSON.parse(atob(token.split('.')[1]))
    return payload.exp ?? null  // Unix timestamp in seconds
  } catch {
    return null
  }
}

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: null as string | null,
    userId: null as string | null,
  }),
  getters: {
    isAuthenticated: (state) => !!state.token,
    isTokenExpired: (state): boolean => {
      if (!state.token) return true
      const exp = decodeJwtExpiry(state.token)
      if (!exp) return false
      // Consider expired 60s before actual expiry to avoid edge cases
      return Date.now() / 1000 > exp - 60
    },
  },
  actions: {
    setAuth(token: string, userId: string) {
      this.token = token
      this.userId = userId
      if (process.client) {
        localStorage.setItem('auth_token', token)
        localStorage.setItem('user_id', userId)
      }
    },
    loadFromStorage() {
      if (process.client) {
        const token = localStorage.getItem('auth_token')
        const userId = localStorage.getItem('user_id')
        if (token) {
          // Clear expired tokens on load
          const exp = decodeJwtExpiry(token)
          if (exp && Date.now() / 1000 > exp) {
            this.logout()
            return
          }
        }
        this.token = token
        this.userId = userId
      }
    },
    logout() {
      this.token = null
      this.userId = null
      if (process.client) {
        localStorage.removeItem('auth_token')
        localStorage.removeItem('user_id')
      }
    },
  },
})
