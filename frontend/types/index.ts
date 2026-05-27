// Shared TypeScript types for the WTech Landing Page frontend

export interface GenerateRequest {
  prompt: string
  project_name?: string
  template_id?: string
  brand_color?: string
}

export interface GenerateResponse {
  job_id: string
  status: 'pending'
  project_id: string
  estimated_seconds: number
}

export interface JobStatus {
  job_id: string
  status: 'pending' | 'processing' | 'completed' | 'failed'
  progress: number
  current_step: string
  error: string | null
  result: Record<string, unknown> | null
}

export interface Project {
  id: string
  name: string
  slug: string
  status: 'draft' | 'generating' | 'ready' | 'published' | 'failed'
  created_at: string
  published_url: string | null
}

export interface Template {
  id: string
  name: string
  visual_style: 'minimalista' | 'corporativo' | 'moderno' | 'agressivo'
  description: string
  preview_url: string
}

export interface ErrorResponse {
  error_code: string
  message: string
  timestamp: string
}

