import { defineStore } from 'pinia'
import type { JobStatus } from '~/types'

export const useGenerationStore = defineStore('generation', {
  state: () => ({
    jobId: null as string | null,
    status: null as JobStatus['status'] | null,
    currentStep: '' as string,
    progress: 0 as number,
    html: null as string | null,
    error: null as string | null,
    projectId: null as string | null,
  }),
  actions: {
    reset() {
      this.jobId = null
      this.status = null
      this.currentStep = ''
      this.progress = 0
      this.html = null
      this.error = null
      this.projectId = null
    },
    setJob(jobId: string, projectId: string) {
      this.jobId = jobId
      this.projectId = projectId
      this.status = 'pending'
    },
    updateStatus(job: JobStatus) {
      this.status = job.status
      this.currentStep = job.current_step || ''
      this.progress = job.progress
      this.error = job.error
    },
    setHtml(html: string) {
      this.html = html
    },
  },
})
