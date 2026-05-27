<template>
  <div v-if="store.status && store.status !== 'completed'" class="generation-progress" role="status" aria-live="polite">
    <div class="progress-header">
      <span class="progress-label">{{ stepLabel }}</span>
      <span class="progress-percent">{{ Math.round(store.progress * 100) }}%</span>
    </div>
    <div class="progress-bar-track" aria-label="Progresso da geracao">
      <div
        class="progress-bar-fill"
        :style="{ width: `${store.progress * 100}%` }"
        role="progressbar"
        :aria-valuenow="Math.round(store.progress * 100)"
        aria-valuemin="0"
        aria-valuemax="100"
      />
    </div>
    <p v-if="store.status === 'failed'" class="progress-error">
      {{ store.error || 'Erro na geracao. Tente novamente.' }}
    </p>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useGenerationStore } from '~/stores/generation'

const store = useGenerationStore()

const STEP_LABELS: Record<string, string> = {
  interpretando: 'Interpretando seu prompt...',
  'gerando conteudo': 'Gerando conteudo com IA...',
  'montando layout': 'Montando o layout...',
  renderizando: 'Renderizando a pagina...',
  finalizando: 'Finalizando...',
  pending: 'Aguardando processamento...',
  processing: 'Processando...',
}

const stepLabel = computed(() =>
  STEP_LABELS[store.currentStep] || STEP_LABELS[store.status || ''] || 'Processando...'
)
</script>

<style scoped>
.generation-progress { padding: 16px; background: #f0f9fa; border-radius: 8px; margin: 16px 0; }
.progress-header { display: flex; justify-content: space-between; margin-bottom: 8px; font-size: 0.875rem; color: #4a5568; }
.progress-bar-track { height: 8px; background: #e2e8f0; border-radius: 4px; overflow: hidden; }
.progress-bar-fill { height: 100%; background: linear-gradient(90deg, #084753, #0a5f6e); border-radius: 4px; transition: width 0.5s ease; }
.progress-error { margin-top: 8px; color: #c53030; font-size: 0.875rem; }
</style>
