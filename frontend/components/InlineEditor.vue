<template>
  <div class="editor-container">
    <h2 class="editor-title">Editar Conteúdo</h2>
    <div v-for="(field, key) in editableFields" :key="key" class="editor-field">
      <label :for="`field-${key}`" class="editor-label">{{ field.label }}</label>
      <textarea
        :id="`field-${key}`"
        v-model="localValues[key]"
        class="editor-textarea"
        :rows="field.rows || 2"
        :aria-label="field.label"
      />
    </div>
    <div class="editor-actions">
      <button class="btn-primary" type="button" @click="save">Salvar alterações</button>
      <button class="btn-secondary" type="button" @click="$emit('cancel')">Cancelar</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive } from 'vue'

interface EditableField { label: string; rows?: number }

const props = defineProps<{
  fields: Record<string, EditableField>
  values: Record<string, string>
}>()

const emit = defineEmits<{
  save: [values: Record<string, string>]
  cancel: []
}>()

const localValues = reactive<Record<string, string>>({ ...props.values })

function save() {
  emit('save', { ...localValues })
}
</script>

<style scoped>
.editor-container { padding: 24px; background: #fff; border-radius: 8px; }
.editor-title { font-size: 1.25rem; font-weight: 600; color: #2d3748; margin-bottom: 16px; }
.editor-field { margin-bottom: 16px; }
.editor-label { display: block; font-size: 0.875rem; color: #4a5568; margin-bottom: 4px; }
.editor-textarea { width: 100%; padding: 8px 12px; border: 1px solid #e2e8f0; border-radius: 4px; font-size: 0.875rem; resize: vertical; }
.editor-actions { display: flex; gap: 8px; margin-top: 16px; }
.btn-primary { background: #084753; color: #fff; padding: 8px 16px; border: none; border-radius: 4px; cursor: pointer; }
.btn-secondary { background: #e2e8f0; color: #2d3748; padding: 8px 16px; border: none; border-radius: 4px; cursor: pointer; }
</style>
