export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'

export type Opportunity = {
  opportunity_id: string
  source: string
  source_record_id: string
  orgao_nome: string | null
  orgao_cnpj: string | null
  unidade_nome: string | null
  municipio: string | null
  uf: string | null
  objeto_original: string | null
  categories: string[]
  relevance: string
  temporal_status: string
  data_publicacao: string | null
  data_abertura_proposta: string | null
  data_encerramento_proposta: string | null
  valor_total_estimado: number | null
  opportunity_score: number
  confidence_score: number
  rules_version: string
  generated_at: string
}

export type Stats = {
  total_gold: number
  relevant: number
  irrelevant: number
  high: number
  medium: number
  low: number
  active: number
  future: number
  closed: number
  indeterminate: number
  average_opportunity_score: number | null
  average_confidence_score: number | null
  estimated_ticket_total: number
  categories: Record<string, number>
}

export type Evidence = {
  opportunity_id: string
  matched_terms: { term: string; category: string }[]
  negative_matches: { term: string; reason_code: string }[]
  reason_codes: string[]
  score_breakdown: Record<string, { points: number | null; maximum: number; status: string; evidence: string[] }>
  lineage: Record<string, unknown>
}

export type ReviewItemSummary = {
  review_id: string
  source_record_id: string
  orgao_nome: string
  objeto_original: string
  is_reviewed: boolean
  reviewed_at: string | null
}

export type ReviewSummary = {
  total: number
  reviewed: number
  pending: number
  progress_percent: number
  items: ReviewItemSummary[]
}

export type ReviewBaseline = {
  relevance: string | null
  categories: string[]
  opportunity_score: number
  confidence_score: number
  matched_terms: string
  negative_matches: string
}

export type ReviewHumanAnnotation = {
  human_relevant: boolean | null
  human_relevance: string | null
  human_categories: string[]
  human_confidence: number | null
  human_notes: string
  reviewed_at: string | null
  is_reviewed: boolean
}

export type ReviewDetail = {
  review_id: string
  source_record_id: string
  objeto_original: string
  orgao_nome: string
  unidade_nome: string
  municipio: string
  uf: string
  valor_total_estimado: number | null
  data_publicacao: string
  baseline: ReviewBaseline | null
  human: ReviewHumanAnnotation
}

export type HumanAnnotationPayload = {
  human_relevant: boolean
  human_relevance: string
  human_categories: string[]
  human_confidence: number
  human_notes?: string | null
}

async function get<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`)
  if (!response.ok) throw new Error(`API respondeu ${response.status}`)
  return response.json()
}

async function put<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify(body),
  })
  if (!response.ok) {
    const errorData = await response.json().catch(() => null)
    let detail = `API respondeu ${response.status}`
    if (typeof errorData?.detail === 'string') {
      detail = errorData.detail
    } else if (Array.isArray(errorData?.detail)) {
      detail = errorData.detail.map((e: any) => e.msg || JSON.stringify(e)).join('; ')
    } else if (errorData?.detail) {
      detail = JSON.stringify(errorData.detail)
    }
    throw new Error(detail)
  }
  return response.json()
}

export const api = {
  stats: () => get<Stats>('/stats'),
  opportunities: (params: URLSearchParams) =>
    get<{ items: Opportunity[]; total: number; page: number; page_size: number; total_pages: number }>(`/opportunities?${params}`),
  detail: (id: string) => get<Opportunity>(`/opportunities/${id}`),
  evidence: (id: string) => get<Evidence>(`/opportunities/${id}/evidence`),
  reviewSummary: () => get<ReviewSummary>('/review'),
  reviewDetail: (reviewId: string) => get<ReviewDetail>(`/review/${reviewId}`),
  reviewSave: (reviewId: string, payload: HumanAnnotationPayload) => put<ReviewDetail>(`/review/${reviewId}`, payload),
  reviewExportUrl: () => `${API_BASE_URL}/review/export`,
  devReviewSummary: () => get<ReviewSummary>('/review/dev'),
  devReviewDetail: (reviewId: string) => get<ReviewDetail>(`/review/dev/${reviewId}`),
  devReviewSave: (reviewId: string, payload: HumanAnnotationPayload) => put<ReviewDetail>(`/review/dev/${reviewId}`, payload),
  devReviewExportUrl: () => `${API_BASE_URL}/review/dev/export`,
}
