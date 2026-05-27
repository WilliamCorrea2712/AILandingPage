import { defineStore } from 'pinia'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: null as string | null,
    userId: null as string | null,
  }),
  getters: {
    isAuthenticated: (state) => !!state.token,
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
        this.token = localStorage.getItem('auth_token')
        this.userId = localStorage.getItem('user_id')
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
