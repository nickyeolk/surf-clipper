// Typed client for the local backend (specs/001-ride-detection-clipping/contracts/http-api.md).

export interface SessionSummary {
  session_id: string
  name: string
  source_path: string
  duration_s: number | null
  fps: number | null
  rides: number | null
  short_attempts: number | null
  has_review_copy: boolean
  labels_done: number
  labels_total: number
  labels_final: boolean
}

export type Verdict = '?' | 'ok' | 'fix' | 'no' | 'add'

export interface LabelItem {
  id: string
  start_s: number
  end_s: number
  verdict: Verdict
  acid_drop: boolean
  detected_as: string | null
  proposed_start_s: number | null
  proposed_end_s: number | null
  confidence: number | null
  notes: string
}

export interface LabelWork {
  schema_version: string
  source: string
  items: LabelItem[]
  scanned_to_s: number
  finalized: boolean
}

export interface Activity {
  bin_s: number
  values: number[]
}

export interface SourceInfo {
  path: string
  width: number
  height: number
  duration_s: number
  avg_fps: number
  hdr_format: string
}

export class ApiError extends Error {
  constructor(public code: string, message: string) {
    super(message)
  }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    ...init,
    headers: { 'content-type': 'application/json', ...(init?.headers ?? {}) },
  })
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    const err = body?.error ?? { code: String(res.status), message: res.statusText }
    throw new ApiError(err.code, err.message)
  }
  return res.json() as Promise<T>
}

export const api = {
  sessions: () => call<SessionSummary[]>('/sessions'),
  session: (id: string) => call<{ probe: SourceInfo }>(`/sessions/${id}`),
  activity: (id: string) => call<Activity>(`/sessions/${id}/activity`),
  labels: (id: string) => call<LabelWork>(`/sessions/${id}/labels`),
  saveLabels: (id: string, work: LabelWork) =>
    call<LabelWork>(`/sessions/${id}/labels`, { method: 'PUT', body: JSON.stringify(work) }),
  finalize: (id: string) =>
    call<{ rides: number; path: string }>(`/sessions/${id}/labels/finalize`, { method: 'POST' }),
  videoUrl: (id: string) => `/api/sessions/${id}/media/review.mp4`,
}

export function clock(seconds: number): string {
  const s = Math.max(0, seconds)
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = (s % 60).toFixed(2).padStart(5, '0')
  return h ? `${h}:${String(m).padStart(2, '0')}:${sec}` : `${String(m).padStart(2, '0')}:${sec}`
}
