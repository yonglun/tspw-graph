export const DEFAULT_PROJECT_ID = 'xiaoao'

export type EntitySummary = {
  id: string
  project_id: string
  type: string
  name: string
  aliases: string[]
  description: string
}

export type Evidence = {
  id: string
  chapter_id: string
  chapter_number: number
  chapter_title: string
  start_offset: number
  end_offset: number
  quote: string
}

export type Fact = {
  id: string
  type: string
  source_id: string
  target_id: string
  evidence: Evidence[]
}

export type RelationEvidence = Fact & {
  label?: string
  review_status?: string
  source?: EntitySummary
  target?: EntitySummary
}

export type AttributeDetail = {
  id: string
  property_id: string
  label: string
  value_type: string
  value: string
  confidence: number
  evidence: Evidence[]
}

export type RelationSummary = {
  fact_id: string
  type: string
  label: string
  direction: 'OUTGOING' | 'INCOMING'
  other: { id: string; type: string; name: string }
}

export type EntityDetail = EntitySummary & {
  attributes?: AttributeDetail[]
  relations?: RelationSummary[]
  facts: Fact[]
}

export type GraphEdge = {
  id: string
  source_id: string
  target_id: string
  type: string
  from_chapter?: number
  to_chapter?: number
  confidence: number
}

export type Neighborhood = { nodes: EntitySummary[]; edges: GraphEdge[] }

export type TimelineRelationship = {
  id: string
  type: string
  label: string
  source: EntitySummary
  target: EntitySummary
  from_chapter?: number
  to_chapter?: number
}

export type TimelineEventDetail = {
  event: EntitySummary
  chapter_number?: number
  participants: EntitySummary[]
  evidence: Evidence[]
  relationship_states: {
    started: TimelineRelationship[]
    active: TimelineRelationship[]
    ended: TimelineRelationship[]
  }
}

export type OntologyCatalog = {
  entity_types: Array<{
    id: string
    label: string
    description: string
    color: string
    parent?: string
    property_definitions?: PropertyDefinition[]
    effective_property_definitions?: PropertyDefinition[]
  }>
  relation_types: Array<{ id: string; label: string; description: string; source_types: string[]; target_types: string[]; symmetric: boolean; temporal: boolean }>
  example: { subject: string; predicate: string; object: string }
}

export type PropertyDefinition = {
  id: string
  label: string
  description: string
  value_type: string
  multiple: boolean
  enum_values: string[]
}

export type AskResponse = {
  answer: string
  path: Array<{ source_name: string; relation: string; target_name: string }>
  query_explanation: string
  cypher_template: string
  parameters: Record<string, string>
  evidence: Evidence[]
}

export type ProjectSummary = { id: string; title: string; is_builtin: boolean; source_encoding?: string; source_size?: number; created_at: string; updated_at: string }
export type ModelProfile = { id: string; provider: string; base_url: string; model: string; timeout_seconds: number; available: boolean }
export type JobKind = 'FULL_BUILD' | 'ATTRIBUTE_BACKFILL'
export type JobSnapshot = { id: string; project_id: string; model_profile_id: string; kind?: JobKind; status: string; completed_chunks: number; total_chunks: number; error_code?: string }
export type ProjectCreated = { project: ProjectSummary; job: JobSnapshot }
export type QualityReport = { total_chunks: number; successful_chunks: number; failed_chunks: number; accepted_entities: number; accepted_facts: number; accepted_evidence: number; accepted_attributes?: number; accepted_attribute_evidence?: number; ambiguous_entities: number; rejected_by_code: Record<string, number>; model_calls: number; retry_count: number }

export type ReviewSummary = {
  open_review_items: number
  accepted_facts: number
  rejected_facts: number
  pending_facts: number
  merged_entities: number
  split_aliases: number
  evidence_coverage: number
  review_completion_rate: number
  graph_fact_delta_before_after_review: number
}

export type ReviewItem = {
  id: string
  project_id?: string
  item_type: 'FACT' | 'DUPLICATE_ENTITY' | 'ALIAS_SPLIT'
  status: 'OPEN' | 'RESOLVED' | 'DISMISSED'
  source: 'rule' | 'model' | 'manual'
  reason_code: string
  target: Record<string, string>
  evidence_ids: string[]
  severity: number
}

export type ReviewActionRequest = {
  action_type: 'accept_fact' | 'reject_fact' | 'merge_entities' | 'split_alias' | 'dismiss_item'
  payload: Record<string, string>
  idempotency_key?: string
}

export type ReviewAction = {
  id: string
  reviewer: string
  action_type: string
  payload: Record<string, string>
  created_at: string
}

type ApiAuthHooks = {
  getCsrfToken?: () => string | undefined
  onAuthenticationRequired?: () => void
  onPasswordChangeRequired?: () => void
}

let authHooks: ApiAuthHooks = {}

export function setApiAuthHooks(hooks: ApiAuthHooks) {
  authHooks = hooks
}

export class ApiError extends Error {
  constructor(public status: number, public code: string, public detail: unknown) {
    super(!code || code === `HTTP_${status}` ? `请求失败（${status}）` : code)
    this.name = 'ApiError'
  }
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers)
  if (!(init?.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  const method = (init?.method ?? 'GET').toUpperCase()
  if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)) {
    const csrf = authHooks.getCsrfToken?.()
    if (csrf) headers.set('X-CSRF-Token', csrf)
  }
  const response = await fetch(path, {
    ...init,
    headers,
    credentials: 'same-origin',
  })
  if (!response.ok) {
    let detail: unknown
    try { detail = await response.json() } catch { detail = undefined }
    const payload = detail as { detail?: { code?: string } } | undefined
    const code = payload?.detail?.code ?? `HTTP_${response.status}`
    if (response.status === 401) authHooks.onAuthenticationRequired?.()
    if (response.status === 403 && code === 'PASSWORD_CHANGE_REQUIRED') authHooks.onPasswordChangeRequired?.()
    throw new ApiError(response.status, code, detail)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export function getTimelineDetail(projectId: string, eventId: string, signal?: AbortSignal) {
  return apiFetch<TimelineEventDetail>(
    `/api/graph/timeline/${encodeURIComponent(eventId)}?project_id=${encodeURIComponent(projectId)}`,
    { signal },
  )
}
