<template>
  <div v-if="visible" class="error-notification" role="alert" aria-live="assertive">
    <div class="error-icon" aria-hidden="true">⚠️</div>
    <div class="error-body">
      <p class="error-type">{{ errorType }}</p>
      <p class="error-message">{{ message }}</p>
      <p class="error-suggestion">{{ suggestion }}</p>
    </div>
    <div class="error-actions">
      <button v-if="onRetry" class="btn-retry" type="button" @click="onRetry">Tentar novamente</button>
      <button v-if="onEdit" class="btn-edit" type="button" @click="onEdit">Editar prompt</button>
      <button class="btn-close" type="button" aria-label="Fechar notificação" @click="visible = false">✕</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'

const props = defineProps<{
  errorCode?: string
  message?: string
  onRetry?: () => void
  onEdit?: () => void
}>()

const visible = ref(true)

const ERROR_TYPES: Record<string, string> = {
  GENERATION_FAILED: 'Erro na geração de conteúdo',
  RENDER_ERROR: 'Erro na renderização',
  SSL_PROVISIONING_ERROR: 'Falha na publicação',
  CDN_INTEGRATION_ERROR: 'Falha na publicação',
  PUBLICATION_TIMEOUT: 'Tempo limite excedido',
  PROMPT_TOO_SHORT: 'Prompt muito curto',
  PROMPT_TOO_LONG: 'Prompt muito longo',
  RATE_LIMIT_EXCEEDED: 'Limite de requisições atingido',
}

const SUGGESTIONS: Record<string, string> = {
  GENERATION_FAILED: 'Tente novamente ou reformule seu prompt.',
  RENDER_ERROR: 'Tente novamente. Se o problema persistir, contate o suporte.',
  SSL_PROVISIONING_ERROR: 'Verifique as configurações de domínio e tente novamente.',
  CDN_INTEGRATION_ERROR: 'Tente publicar novamente em alguns minutos.',
  PUBLICATION_TIMEOUT: 'A publicação está demorando mais que o esperado. Tente novamente.',
  PROMPT_TOO_SHORT: 'Descreva sua landing page com mais detalhes (mínimo 10 caracteres).',
  PROMPT_TOO_LONG: 'Reduza o tamanho do prompt (máximo 4000 caracteres).',
  RATE_LIMIT_EXCEEDED: 'Aguarde um momento antes de tentar novamente.',
}

const errorType = computed(() => ERROR_TYPES[props.errorCode || ''] || 'Erro inesperado')
const suggestion = computed(() => SUGGESTIONS[props.errorCode || ''] || 'Tente novamente ou contate o suporte.')
</script>

<style scoped>
.error-notification {
  display: flex; align-items: flex-start; gap: 12px;
  padding: 16px; background: #fff5f5; border: 1px solid #fed7d7;
  border-radius: 8px; margin: 16px 0;
}
.error-icon { font-size: 1.5rem; flex-shrink: 0; }
.error-body { flex: 1; }
.error-type { font-weight: 600; color: #c53030; margin-bottom: 4px; }
.error-message { color: #742a2a; font-size: 0.875rem; margin-bottom: 4px; }
.error-suggestion { color: #9b2c2c; font-size: 0.8rem; }
.error-actions { display: flex; flex-direction: column; gap: 8px; flex-shrink: 0; }
.btn-retry { background: #c53030; color: #fff; padding: 6px 12px; border: none; border-radius: 4px; cursor: pointer; font-size: 0.875rem; }
.btn-edit { background: #e2e8f0; color: #2d3748; padding: 6px 12px; border: none; border-radius: 4px; cursor: pointer; font-size: 0.875rem; }
.btn-close { background: transparent; border: none; cursor: pointer; color: #9b2c2c; font-size: 1rem; padding: 4px; }
</style>
