<template>
  <div class="preview-container">
    <div class="preview-header">
      <h2 class="preview-title">Pré-visualização</h2>
      <div class="preview-actions">
        <button class="btn-secondary" type="button" @click="$emit('edit')">Editar</button>
        <button class="btn-primary" type="button" @click="$emit('publish')">Publicar</button>
      </div>
    </div>
    <div class="preview-frame-wrapper">
      <iframe
        ref="iframeRef"
        class="preview-iframe"
        sandbox="allow-same-origin"
        title="Pré-visualização da landing page"
        aria-label="Pré-visualização da landing page gerada"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'

const props = defineProps<{ html: string }>()
defineEmits<{ edit: []; publish: [] }>()

const iframeRef = ref<HTMLIFrameElement | null>(null)

function renderHtml(html: string) {
  const iframe = iframeRef.value
  if (!iframe) return
  const doc = iframe.contentDocument || iframe.contentWindow?.document
  if (!doc) return
  doc.open()
  doc.write(html)
  doc.close()
}

onMounted(() => { if (props.html) renderHtml(props.html) })
watch(() => props.html, (html) => { if (html) renderHtml(html) })
</script>

<style scoped>
.preview-container { display: flex; flex-direction: column; gap: 16px; }
.preview-header { display: flex; justify-content: space-between; align-items: center; }
.preview-title { font-size: 1.25rem; font-weight: 600; color: #2d3748; }
.preview-actions { display: flex; gap: 8px; }
.btn-primary { background: #084753; color: #fff; padding: 8px 16px; border: none; border-radius: 4px; cursor: pointer; }
.btn-secondary { background: #e2e8f0; color: #2d3748; padding: 8px 16px; border: none; border-radius: 4px; cursor: pointer; }
.preview-frame-wrapper { border: 1px solid #e2e8f0; border-radius: 8px; overflow: hidden; }
.preview-iframe { width: 100%; height: 600px; border: none; display: block; }
</style>
