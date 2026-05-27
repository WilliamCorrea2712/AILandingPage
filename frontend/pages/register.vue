<template>
  <div class="login-page">
    <div class="login-card">
      <h1 class="login-title">
        <img src="/logo-wstack.png" alt="WStack" style="height:58px;width:auto;margin-bottom:16px;display:block;margin-left:auto;margin-right:auto" />
        Criar conta
      </h1>
      <form class="login-form" @submit.prevent="handleRegister">
        <div class="form-group">
          <label for="name" class="form-label">Nome</label>
          <input id="name" v-model="name" type="text" class="form-input" required placeholder="Seu nome" autocomplete="name" />
        </div>
        <div class="form-group">
          <label for="email" class="form-label">E-mail</label>
          <input id="email" v-model="email" type="email" class="form-input" required placeholder="seu@email.com" autocomplete="email" />
        </div>
        <div class="form-group">
          <label for="password" class="form-label">Senha</label>
          <input id="password" v-model="password" type="password" class="form-input" required placeholder="Minimo 8 caracteres" autocomplete="new-password" minlength="8" />
        </div>
        <p v-if="error" class="login-error" role="alert">{{ error }}</p>
        <button class="btn-login" type="submit" :disabled="loading">
          {{ loading ? 'Criando conta...' : 'Criar conta' }}
        </button>
        <p class="login-register">
          Ja tem conta? <NuxtLink to="/login">Entrar</NuxtLink>
        </p>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useAuthStore } from '~/stores/auth'
import { apiFetch } from '~/utils/api'

const auth = useAuthStore()
const name = ref('')
const email = ref('')
const password = ref('')
const error = ref('')
const loading = ref(false)

async function handleRegister() {
  loading.value = true
  error.value = ''
  try {
    const res = await apiFetch<{ access_token: string; user_id: string }>('/auth/register', {
      method: 'POST',
      body: JSON.stringify({ name: name.value, email: email.value, password: password.value }),
    })
    auth.setAuth(res.access_token, res.user_id)
    navigateTo('/')
  } catch (err: any) {
    error.value = err.message || 'Erro ao criar conta. Tente novamente.'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh; display: flex; align-items: center;
  justify-content: center; background: #f0f9fa; padding: 16px;
}
.login-card {
  background: #fff; padding: 32px; border-radius: 8px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.1); width: 100%; max-width: 400px;
}
.login-title { font-size: 1.5rem; font-weight: 700; color: #084753; margin-bottom: 24px; text-align: center; }
.login-form { display: flex; flex-direction: column; gap: 16px; }
.form-group { display: flex; flex-direction: column; gap: 4px; }
.form-label { font-size: 0.875rem; font-weight: 500; color: #4a5568; }
.form-input { padding: 10px 12px; border: 1px solid #e2e8f0; border-radius: 4px; font-size: 1rem; }
.form-input:focus { outline: none; border-color: #084753; }
.login-error { color: #c53030; font-size: 0.875rem; }
.btn-login {
  background: #084753; color: #fff; padding: 12px; border: none;
  border-radius: 4px; font-size: 1rem; cursor: pointer; font-weight: 600;
}
.btn-login:disabled { opacity: 0.6; cursor: not-allowed; }
.login-register { text-align: center; font-size: 0.875rem; color: #718096; }
.login-register a { color: #084753; }
</style>
