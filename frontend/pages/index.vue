<template>
  <div class="page-container">
    <header class="page-header">
      <NuxtLink to="/" class="logo-link">
        <img src="/logo-wstack.png" alt="WStack" class="header-logo" />
      </NuxtLink>
      <div class="header-actions">
        <template v-if="auth.isAuthenticated">
          <span class="user-badge">Conectado</span>
          <button class="btn-logout" type="button" @click="logout">Sair</button>
        </template>
        <template v-else>
          <NuxtLink to="/login" class="btn-nav">Entrar</NuxtLink>
          <NuxtLink to="/register" class="btn-nav btn-primary-nav">Criar conta</NuxtLink>
        </template>
      </div>
    </header>

    <main class="page-main">

      <div v-if="!auth.isAuthenticated" class="auth-prompt">
        <div class="auth-card">
          <h2>Bem-vindo ao WTech Landing Page</h2>
          <p>Crie landing pages profissionais com IA em segundos.</p>
          <div class="auth-buttons">
            <NuxtLink to="/register" class="btn-cta">Criar conta gratis</NuxtLink>
            <NuxtLink to="/login" class="btn-secondary-link">Ja tenho conta</NuxtLink>
          </div>
        </div>
      </div>

      <template v-else>
        <section v-if="!generationDone" class="prompt-section">
          <h2 class="section-title">Descreva sua landing page</h2>

          <form class="prompt-form" @submit.prevent="handleGenerate">
            <div class="form-group">
              <label for="prompt" class="form-label">O que voce quer criar?</label>
              <textarea
                id="prompt"
                v-model="prompt"
                class="form-textarea"
                rows="5"
                placeholder="Ex: Landing page para clinica odontologica Sorriso Perfeito, especializada em implantes e clareamento, em Sao Paulo, estilo moderno, cores azul e branco, quero formulario com nome e WhatsApp, 3 depoimentos e FAQ"
                minlength="10"
                maxlength="4000"
                required
                :disabled="isGenerating"
              />
              <p class="form-hint">{{ prompt.length }}/4000 caracteres (minimo 10)</p>
            </div>

            <!-- ── Upload de Logo ──────────────────────────────────────────── -->
            <div class="form-group">
              <label class="form-label">
                Logo da marca
                <span class="optional-tag">opcional</span>
              </label>

              <div
                class="logo-upload-area"
                :class="{
                  'logo-upload-area--active': isDragging,
                  'logo-upload-area--has-logo': !!logoPreviewUrl,
                }"
                @dragover.prevent="isDragging = true"
                @dragleave.prevent="isDragging = false"
                @drop.prevent="onLogoDrop"
                @click="!logoPreviewUrl && triggerFileInput()"
              >
                <template v-if="logoPreviewUrl">
                  <img :src="logoPreviewUrl" alt="Preview do logo" class="logo-preview-img" />
                  <div class="logo-preview-overlay">
                    <button
                      type="button"
                      class="logo-remove-btn"
                      :disabled="isGenerating"
                      @click.stop="removeLogo"
                    >
                      Remover logo
                    </button>
                  </div>
                </template>
                <template v-else>
                  <div class="logo-upload-icon">🖼️</div>
                  <p class="logo-upload-text"><strong>Clique ou arraste</strong> seu logo aqui</p>
                  <p class="logo-upload-hint">PNG, JPG, WEBP ou SVG — max. 5 MB</p>
                </template>
              </div>

              <input
                ref="fileInputRef"
                type="file"
                accept="image/png,image/jpeg,image/jpg,image/webp,image/svg+xml"
                class="file-input-hidden"
                :disabled="isGenerating"
                @change="onLogoFileChange"
              />

              <div v-if="isUploadingLogo" class="logo-uploading">
                <span class="logo-uploading-spinner" />
                Analisando logo e extraindo cores...
              </div>

              <div v-if="extractedColors.length && !isUploadingLogo" class="extracted-colors">
                <p class="extracted-colors-label">🎨 Cores detectadas — clique para aplicar:</p>
                <div class="extracted-colors-swatches">
                  <button
                    v-for="(color, i) in extractedColors"
                    :key="color"
                    type="button"
                    class="color-swatch"
                    :style="{ background: color }"
                    :title="color"
                    :aria-label="`Aplicar cor ${color}`"
                    @click="applyExtractedColor(color, i)"
                  />
                </div>
                <p class="extracted-colors-hint">
                  Cores primaria e de destaque ja foram aplicadas automaticamente.
                </p>
              </div>
            </div>

            <!-- ── Cores ──────────────────────────────────────────────────── -->
            <div class="form-group form-row">
              <div>
                <label for="brand-color" class="form-label">Cor primaria</label>
                <div class="color-picker-row">
                  <input id="brand-color" v-model="brandColor" type="color" class="form-color" :disabled="isGenerating" />
                  <span class="color-value">{{ brandColor }}</span>
                </div>
                <p class="form-hint">Header, hero, botoes principais</p>
              </div>
              <div>
                <label for="accent-color" class="form-label">Cor de destaque</label>
                <div class="color-picker-row">
                  <input id="accent-color" v-model="accentColor" type="color" class="form-color" :disabled="isGenerating" />
                  <span class="color-value">{{ accentColor }}</span>
                </div>
                <p class="form-hint">CTAs, icones, destaques</p>
              </div>
            </div>

            <div v-if="errorMsg" class="error-box" role="alert">
              <strong>{{ errorMsg }}</strong>
              <button type="button" class="error-dismiss" @click="errorMsg = ''">X</button>
            </div>

            <div v-if="isGenerating" class="progress-box">
              <div class="progress-step">{{ currentStep }}</div>
              <div class="progress-bar-track">
                <div class="progress-bar-fill" :style="{ width: `${progress * 100}%` }" />
              </div>
              <p class="progress-pct">{{ Math.round(progress * 100) }}%</p>
            </div>

            <button
              class="btn-generate"
              type="submit"
              :disabled="isGenerating || prompt.length < 10"
            >
              <span v-if="isGenerating">Gerando...</span>
              <span v-else>Gerar Landing Page</span>
            </button>
          </form>
        </section>

        <section v-if="generationDone && generatedHtml" class="result-section">
          <div class="result-header">
            <h2 class="section-title">Landing page gerada!</h2>
            <div class="result-actions">
              <button class="btn-secondary" type="button" @click="resetForm">Nova geracao</button>
              <button class="btn-primary-btn" type="button" @click="copyHtml">Copiar HTML</button>
              <a :href="downloadUrl" download="landing-page.html" class="btn-download">Baixar HTML</a>
            </div>
          </div>

          <!-- ── Feedback ──────────────────────────────────────────────── -->
          <div class="feedback-bar">
            <span class="feedback-label">Como ficou esta landing page?</span>
            <div class="feedback-buttons">
              <button
                type="button"
                class="feedback-btn feedback-btn--positive"
                :class="{ 'feedback-btn--active': feedbackGiven === 1 }"
                :disabled="feedbackGiven !== null"
                @click="submitFeedback(1)"
                aria-label="Gostei"
              >
                👍 Gostei
              </button>
              <button
                type="button"
                class="feedback-btn feedback-btn--negative"
                :class="{ 'feedback-btn--active': feedbackGiven === -1 }"
                :disabled="feedbackGiven !== null"
                @click="submitFeedback(-1)"
                aria-label="Nao gostei"
              >
                👎 Nao gostei
              </button>
            </div>
            <p v-if="feedbackGiven === 1" class="feedback-thanks feedback-thanks--positive">
              ✅ Obrigado! Esse resultado foi salvo para melhorar as proximas geracoes.
            </p>
            <p v-if="feedbackGiven === -1" class="feedback-thanks feedback-thanks--negative">
              📝 Feedback registrado. Vamos melhorar!
            </p>
          </div>

          <div class="preview-wrapper">
            <iframe
              ref="previewFrame"
              class="preview-iframe"
              sandbox="allow-same-origin allow-scripts"
              title="Preview da landing page"
            />
          </div>
          <p v-if="copied" class="copy-success">HTML copiado para a area de transferencia!</p>
        </section>
      </template>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, onMounted } from 'vue'
import { useAuthStore } from '~/stores/auth'
import { apiFetch } from '~/utils/api'
import type { GenerateResponse, JobStatus } from '~/types'

const auth = useAuthStore()
const prompt = ref('')
const brandColor = ref('#084753')
const accentColor = ref('#D8AC4D')
const errorMsg = ref('')
const isGenerating = ref(false)
const currentStep = ref('Aguardando...')
const progress = ref(0)
const generationDone = ref(false)
const generatedHtml = ref('')
const copied = ref(false)
const previewFrame = ref<HTMLIFrameElement | null>(null)

// ── Feedback state ──────────────────────────────────────────────────────────
const feedbackGiven = ref<number | null>(null)  // 1, -1, or null
const currentJobId = ref<string>('')

// ── Logo upload state ──────────────────────────────────────────────────────
const fileInputRef = ref<HTMLInputElement | null>(null)
const logoPreviewUrl = ref<string>('')   // URL local (blob) para preview
const logoServerUrl = ref<string>('')    // URL retornada pelo backend
const extractedColors = ref<string[]>([])
const isUploadingLogo = ref(false)
const isDragging = ref(false)

const downloadUrl = computed(() => {
  if (!generatedHtml.value) return '#'
  const blob = new Blob([generatedHtml.value], { type: 'text/html' })
  return URL.createObjectURL(blob)
})

onMounted(() => {
  auth.loadFromStorage()
})

// ── Logo handlers ──────────────────────────────────────────────────────────

function triggerFileInput() {
  fileInputRef.value?.click()
}

function onLogoFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (file) uploadLogo(file)
  // Reset input so the same file can be re-selected after removal
  input.value = ''
}

function onLogoDrop(event: DragEvent) {
  isDragging.value = false
  const file = event.dataTransfer?.files?.[0]
  if (file) uploadLogo(file)
}

async function uploadLogo(file: File) {
  const ALLOWED = ['image/png', 'image/jpeg', 'image/jpg', 'image/webp', 'image/svg+xml']
  if (!ALLOWED.includes(file.type)) {
    errorMsg.value = 'Formato invalido. Use PNG, JPG, WEBP ou SVG.'
    return
  }
  if (file.size > 5 * 1024 * 1024) {
    errorMsg.value = 'Logo muito grande. Maximo: 5 MB.'
    return
  }

  // Mostra preview local imediatamente
  logoPreviewUrl.value = URL.createObjectURL(file)
  isUploadingLogo.value = true
  extractedColors.value = []
  errorMsg.value = ''

  try {
    const formData = new FormData()
    formData.append('file', file)

    // Read token from Pinia store (most reliable — already loaded on mount)
    const token = auth.token || (process.client ? localStorage.getItem('auth_token') : null) || ''
    if (!token) {
      errorMsg.value = 'Sessao expirada. Faca login novamente.'
      removeLogo()
      isUploadingLogo.value = false
      return
    }

    // Check token expiry before uploading
    if (auth.isTokenExpired) {
      auth.logout()
      errorMsg.value = 'Sua sessao expirou. Faca login novamente.'
      removeLogo()
      isUploadingLogo.value = false
      setTimeout(() => navigateTo('/login?reason=session_expired'), 1500)
      return
    }

    // Use raw fetch for multipart — avoids any header merging issues
    const config = useRuntimeConfig()
    const apiBase = config.public.apiUrl as string
    const uploadRes = await fetch(`${apiBase}/upload-logo`, {
      method: 'POST',
      body: formData,
      headers: { 'Authorization': `Bearer ${token}` },
    })

    if (!uploadRes.ok) {
      // Token expired — redirect to login
      if (uploadRes.status === 401) {
        auth.logout()
        errorMsg.value = 'Sua sessao expirou. Faca login novamente.'
        removeLogo()
        isUploadingLogo.value = false
        setTimeout(() => navigateTo('/login?reason=session_expired'), 1500)
        return
      }
      const errData = await uploadRes.json().catch(() => ({}))
      throw new Error(errData.detail || `Erro ${uploadRes.status}`)
    }

    const res = await uploadRes.json() as {
      logo_url: string
      brand_color: string
      accent_color: string
      all_colors: string[]
    }

    // logo_url is already a base64 data URI — use directly
    logoServerUrl.value = res.logo_url
    extractedColors.value = res.all_colors

    // Aplica automaticamente as cores extraídas
    brandColor.value = res.brand_color
    accentColor.value = res.accent_color
  } catch (err: any) {
    errorMsg.value = err.message || 'Erro ao enviar logo. Tente novamente.'
    removeLogo()
  } finally {
    isUploadingLogo.value = false
  }
}

function removeLogo() {
  if (logoPreviewUrl.value.startsWith('blob:')) {
    URL.revokeObjectURL(logoPreviewUrl.value)
  }
  logoPreviewUrl.value = ''
  logoServerUrl.value = ''
  extractedColors.value = []
}

function applyExtractedColor(color: string, index: number) {
  if (index === 0) {
    brandColor.value = color
  } else {
    accentColor.value = color
  }
}

// ── Generation ─────────────────────────────────────────────────────────────

async function handleGenerate() {
  if (prompt.value.length < 10) return
  errorMsg.value = ''
  isGenerating.value = true
  currentStep.value = 'Enviando prompt...'
  progress.value = 0.05

  try {
    const res = await apiFetch<GenerateResponse>('/generate', {
      method: 'POST',
      body: JSON.stringify({
        prompt: prompt.value,
        brand_color: brandColor.value,
        accent_color: accentColor.value,
        logo_url: logoServerUrl.value || null,
      }),
    })
    currentStep.value = 'Job enfileirado - processando...'
    progress.value = 0.1
    currentJobId.value = res.job_id.toString()
    await pollJob(res.job_id.toString())
  } catch (err: any) {
    errorMsg.value = err.message || 'Erro ao gerar. Tente novamente.'
    isGenerating.value = false
    progress.value = 0
  }
}

async function pollJob(jobId: string) {
  const STEP_LABELS: Record<string, string> = {
    interpretando: 'Interpretando seu prompt...',
    'analisando prompt com ia': 'Analisando prompt com IA local...',
    'analisando prompt com IA': 'Analisando prompt com IA local...',
    'consultando base de conhecimento': 'Consultando base de conhecimento...',
    'gerando conteudo': 'Gerando conteudo com IA...',
    'montando layout': 'Montando o layout...',
    renderizando: 'Renderizando a pagina...',
    finalizando: 'Finalizando...',
    pending: 'Aguardando processamento...',
    processing: 'Processando...',
  }

  let attempts = 0
  const maxAttempts = 120

  const interval = setInterval(async () => {
    attempts++
    if (attempts > maxAttempts) {
      clearInterval(interval)
      errorMsg.value = 'Tempo limite excedido. Tente novamente.'
      isGenerating.value = false
      return
    }

    try {
      const job = await apiFetch<JobStatus>(`/jobs/${jobId}`)
      currentStep.value = STEP_LABELS[job.current_step || ''] || STEP_LABELS[job.status] || 'Processando...'
      progress.value = job.progress || progress.value

      if (job.status === 'completed') {
        clearInterval(interval)
        progress.value = 1
        currentStep.value = 'Concluido!'
        if (job.result?.html_output) {
          generatedHtml.value = job.result.html_output as string
        }
        isGenerating.value = false
        generationDone.value = true
        await nextTick()
        renderPreview()
      } else if (job.status === 'failed') {
        clearInterval(interval)
        errorMsg.value = job.error || 'Geracao falhou. Tente novamente.'
        isGenerating.value = false
        progress.value = 0
      }
    } catch {
      // Keep polling on network errors
    }
  }, 2000)
}

function renderPreview() {
  const iframe = previewFrame.value
  if (!iframe || !generatedHtml.value) return
  const doc = iframe.contentDocument || iframe.contentWindow?.document
  if (!doc) return
  doc.open()
  doc.write(generatedHtml.value)
  doc.close()
}

async function copyHtml() {
  await navigator.clipboard.writeText(generatedHtml.value)
  copied.value = true
  setTimeout(() => { copied.value = false }, 3000)
}

function resetForm() {
  generationDone.value = false
  generatedHtml.value = ''
  progress.value = 0
  currentStep.value = ''
  errorMsg.value = ''
  feedbackGiven.value = null
  currentJobId.value = ''
  removeLogo()
}

async function submitFeedback(rating: number) {
  if (!currentJobId.value || feedbackGiven.value !== null) return
  try {
    await apiFetch(`/feedback/${currentJobId.value}`, {
      method: 'POST',
      body: JSON.stringify({ rating }),
    })
    feedbackGiven.value = rating
  } catch {
    // Silently ignore — feedback is non-critical
    feedbackGiven.value = rating
  }
}

function logout() {
  auth.logout()
  navigateTo('/login')
}
</script>

<style scoped>
.page-container { min-height: 100vh; background: #f0f9fa; }

/* Header */
.page-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 16px 32px; background: #084753;
  box-shadow: 0 2px 8px rgba(0,0,0,0.2);
}
.logo-link { display: flex; align-items: center; text-decoration: none; }
.header-logo { height: 58px; width: auto; object-fit: contain; }
.header-actions { display: flex; gap: 8px; align-items: center; }
.user-badge { color: #b8e0e6; font-size: 0.875rem; }
.btn-logout {
  background: rgba(255,255,255,0.15); color: #fff;
  padding: 6px 14px; border: 1px solid rgba(255,255,255,0.3);
  border-radius: 4px; cursor: pointer; font-size: 0.875rem;
}
.btn-nav { color: #b8e0e6; text-decoration: none; padding: 6px 14px; border-radius: 4px; font-size: 0.875rem; }
.btn-primary-nav { background: #D8AC4D; color: #1a202c; font-weight: 600; }

/* Main */
.page-main { max-width: 860px; margin: 0 auto; padding: 40px 16px; }

/* Auth prompt */
.auth-prompt { display: flex; justify-content: center; }
.auth-card {
  background: #fff; padding: 48px; border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.1); text-align: center; max-width: 480px;
}
.auth-card h2 { font-size: 1.5rem; color: #084753; margin-bottom: 12px; }
.auth-card p { color: #718096; margin-bottom: 32px; }
.auth-buttons { display: flex; flex-direction: column; gap: 12px; }
.btn-cta {
  background: #084753; color: #fff; padding: 14px 24px;
  border-radius: 6px; text-decoration: none; font-weight: 600; font-size: 1rem;
}
.btn-secondary-link { color: #084753; text-decoration: none; font-size: 0.875rem; }

/* Prompt form */
.prompt-section {
  background: #fff; border-radius: 12px; padding: 40px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.08);
}
.section-title { font-size: 1.5rem; font-weight: 700; color: #084753; margin-bottom: 24px; }
.prompt-form { display: flex; flex-direction: column; gap: 20px; }
.form-group { display: flex; flex-direction: column; gap: 6px; }
.form-row { flex-direction: row; align-items: flex-start; gap: 24px; }
.form-label { font-size: 0.875rem; font-weight: 600; color: #4a5568; display: flex; align-items: center; gap: 6px; }
.optional-tag {
  font-size: 0.7rem; font-weight: 400; color: #a0aec0;
  background: #f7fafc; border: 1px solid #e2e8f0;
  padding: 1px 6px; border-radius: 10px;
}
.form-textarea {
  padding: 14px; border: 2px solid #e2e8f0; border-radius: 8px;
  font-size: 1rem; resize: vertical; font-family: inherit;
  transition: border-color 0.2s;
}
.form-textarea:focus { outline: none; border-color: #084753; }
.form-hint { font-size: 0.75rem; color: #a0aec0; }
.color-picker-row { display: flex; align-items: center; gap: 8px; }
.form-color {
  width: 48px; height: 40px; padding: 2px;
  border: 2px solid #e2e8f0; border-radius: 6px; cursor: pointer;
}
.color-value { font-size: 0.875rem; color: #718096; font-family: monospace; }

/* Logo upload */
.file-input-hidden { display: none; }

.logo-upload-area {
  border: 2px dashed #cbd5e0; border-radius: 10px;
  padding: 28px 20px; text-align: center; cursor: pointer;
  transition: border-color 0.2s, background 0.2s;
  background: #f7fafc; position: relative; overflow: hidden;
  min-height: 120px; display: flex; flex-direction: column;
  align-items: center; justify-content: center; gap: 6px;
}
.logo-upload-area:hover { border-color: #084753; background: #f0f9fa; }
.logo-upload-area--active { border-color: #084753; background: #e6f4f6; }
.logo-upload-area--has-logo { cursor: default; padding: 12px; border-style: solid; border-color: #084753; }

.logo-upload-icon { font-size: 2rem; }
.logo-upload-text { font-size: 0.9rem; color: #4a5568; margin: 0; }
.logo-upload-hint { font-size: 0.75rem; color: #a0aec0; margin: 0; }

.logo-preview-img {
  max-height: 80px; max-width: 100%; object-fit: contain;
  border-radius: 6px;
}
.logo-preview-overlay {
  position: absolute; inset: 0; background: rgba(0,0,0,0.45);
  display: flex; align-items: center; justify-content: center;
  opacity: 0; transition: opacity 0.2s;
}
.logo-upload-area--has-logo:hover .logo-preview-overlay { opacity: 1; }
.logo-remove-btn {
  background: #fff; color: #c53030; border: none; border-radius: 6px;
  padding: 8px 16px; font-size: 0.875rem; font-weight: 600; cursor: pointer;
}

/* Uploading state */
.logo-uploading {
  display: flex; align-items: center; gap: 8px;
  font-size: 0.8rem; color: #718096; margin-top: 6px;
}
.logo-uploading-spinner {
  width: 14px; height: 14px; border: 2px solid #e2e8f0;
  border-top-color: #084753; border-radius: 50%;
  animation: spin 0.7s linear infinite; flex-shrink: 0;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* Extracted colors */
.extracted-colors {
  background: #f0f9fa; border: 1px solid #b2e0e8; border-radius: 8px;
  padding: 12px 14px; margin-top: 4px;
}
.extracted-colors-label { font-size: 0.8rem; font-weight: 600; color: #2d3748; margin-bottom: 8px; }
.extracted-colors-swatches { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 6px; }
.color-swatch {
  width: 32px; height: 32px; border-radius: 50%; border: 2px solid rgba(0,0,0,0.12);
  cursor: pointer; transition: transform 0.15s, box-shadow 0.15s;
  flex-shrink: 0;
}
.color-swatch:hover { transform: scale(1.2); box-shadow: 0 2px 8px rgba(0,0,0,0.2); }
.extracted-colors-hint { font-size: 0.72rem; color: #718096; margin: 0; }

/* Error */
.error-box {
  background: #fff5f5; border: 1px solid #fed7d7; border-radius: 8px;
  padding: 12px 16px; color: #c53030;
  display: flex; justify-content: space-between; align-items: center;
}
.error-dismiss { background: none; border: none; cursor: pointer; color: #c53030; font-size: 1rem; }

/* Progress */
.progress-box { background: #f0f9fa; border-radius: 8px; padding: 16px; }
.progress-step { font-size: 0.875rem; color: #4a5568; margin-bottom: 8px; font-weight: 500; }
.progress-bar-track { height: 8px; background: #e2e8f0; border-radius: 4px; overflow: hidden; }
.progress-bar-fill {
  height: 100%; background: linear-gradient(90deg, #084753, #0a5f6e);
  border-radius: 4px; transition: width 0.5s ease;
}
.progress-pct { font-size: 0.75rem; color: #a0aec0; margin-top: 4px; text-align: right; }

/* Generate button */
.btn-generate {
  background: linear-gradient(135deg, #084753, #0a5f6e);
  color: #fff; padding: 16px 32px; border: none; border-radius: 8px;
  font-size: 1.1rem; cursor: pointer; font-weight: 700; transition: opacity 0.2s;
}
.btn-generate:disabled { opacity: 0.6; cursor: not-allowed; }
.btn-generate:not(:disabled):hover { opacity: 0.9; }

/* Result */
.result-section {
  background: #fff; border-radius: 12px; padding: 32px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.08);
}
.result-header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 24px; flex-wrap: wrap; gap: 12px;
}
.result-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.btn-secondary {
  background: #e2e8f0; color: #2d3748; padding: 8px 16px;
  border: none; border-radius: 6px; cursor: pointer; font-size: 0.875rem;
}
.btn-primary-btn {
  background: #084753; color: #fff; padding: 8px 16px;
  border: none; border-radius: 6px; cursor: pointer; font-size: 0.875rem;
}
.btn-download {
  background: #D8AC4D; color: #1a202c; padding: 8px 16px;
  border-radius: 6px; text-decoration: none; font-size: 0.875rem; font-weight: 600;
}
.preview-wrapper { border: 2px solid #e2e8f0; border-radius: 8px; overflow: hidden; }
.preview-iframe { width: 100%; height: 600px; border: none; display: block; }
.copy-success { color: #38a169; font-size: 0.875rem; margin-top: 8px; text-align: center; }

/* Feedback bar */
.feedback-bar {
  background: #f0f9fa; border: 1px solid #b2e0e8; border-radius: 10px;
  padding: 16px 20px; margin-bottom: 20px;
  display: flex; align-items: center; flex-wrap: wrap; gap: 12px;
}
.feedback-label { font-size: 0.9rem; font-weight: 600; color: #2d3748; }
.feedback-buttons { display: flex; gap: 8px; }
.feedback-btn {
  padding: 8px 18px; border-radius: 8px; border: 2px solid transparent;
  font-size: 0.875rem; font-weight: 600; cursor: pointer;
  transition: all 0.15s;
}
.feedback-btn--positive { background: #f0fff4; color: #276749; border-color: #9ae6b4; }
.feedback-btn--positive:hover:not(:disabled) { background: #c6f6d5; }
.feedback-btn--negative { background: #fff5f5; color: #c53030; border-color: #feb2b2; }
.feedback-btn--negative:hover:not(:disabled) { background: #fed7d7; }
.feedback-btn--active { transform: scale(1.05); box-shadow: 0 2px 8px rgba(0,0,0,0.15); }
.feedback-btn:disabled { cursor: default; opacity: 0.7; }
.feedback-thanks { font-size: 0.8rem; font-weight: 500; margin: 0; width: 100%; }
.feedback-thanks--positive { color: #276749; }
.feedback-thanks--negative { color: #744210; }

@media (max-width: 600px) {
  .page-header { padding: 12px 16px; }
  .page-main { padding: 20px 12px; }
  .prompt-section, .result-section { padding: 24px 16px; }
  .result-header { flex-direction: column; }
  .form-row { flex-direction: column; }
}
</style>
