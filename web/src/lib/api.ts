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
  exported: number
  analysed: boolean
  zone_confirmed: boolean
  zone_checked: boolean
  job: Job | null
}

export interface SourceVideo {
  path: string
  name: string
  size_bytes: number
  session_id: string | null
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

export interface Zone {
  epoch_id: number
  corners: { back_a: [number, number]; back_b: [number, number]; front_a: [number, number]; front_b: [number, number] }
  entry_walls: ('side_a' | 'side_b')[]
  side_areas: [number, number][][]
  image_to_pool: unknown
  undistort: unknown
  origin: string
  proposal_confidence: number | null
  face_v: [number, number] | null
}

export interface FaceBand {
  face_v: [number, number] | null
  origin: string
  frames: number
}

export interface ZoneProposal {
  zone: Zone
  confidence: number
  unreliable: boolean
  points: number
  walls_in_frame: Record<string, boolean>
  notes: string[]
}

export interface ZoneInfo {
  zone: Zone | null
  face: FaceBand | null
  frame: { width: number; height: number; duration_s: number }
  feet: [number, number][]
  proposal: ZoneProposal | null
}

export interface RideFlags {
  lesson: boolean
  truncated: boolean
  user_edited: boolean
  user_added: boolean
  joined?: boolean
}

export interface ExportRecord {
  path: string
  exported_at: string
  span: [number, number]
}

export interface Ride {
  ride_id: string
  start_s: number
  end_s: number
  confidence: number
  clip_start_s: number
  clip_end_s: number
  start_kind: string
  flags: RideFlags
  export: ExportRecord | null
  rider?: string | null
  rider_id?: string | null
  rider_confidence?: number | null
  rider_confirmed?: boolean
}

export interface ShortAttempt {
  ride_id: string
  start_s: number
  end_s: number
  confidence: number
}

export interface Rides {
  session_id: string
  source: { path: string; fps: number; hdr_format: string }
  settings: { min_length_s: number; pad_before_s: number; pad_after_s: number }
  rides: Ride[]
  short_attempts: ShortAttempt[]
}

export type EditOp = 'trim' | 'split' | 'merge' | 'delete' | 'add' | 'undo'
export type RiderOp = RiderEditRequest['op']

export interface UserEdit {
  edit_id: number
  at: string
  op: EditOp | RiderOp | 'confirm_zone' | 'rider_unjoin'
  target: { epoch_id?: number | null; ride_id?: string | null; ride_ids?: string[] | null }
  payload: Record<string, unknown>
}

export interface Job {
  job_id: string
  kind: string
  status: 'queued' | 'running' | 'done' | 'failed'
  progress: number
  message: string
  result: { exported?: string[]; up_to_date?: string[]; folder?: string; reel?: string; next?: string; rides?: number; short_attempts?: number }
  error: string | null
}

export interface RiderLabelItem {
  id: string
  start_s: number
  end_s: number
  rider: string | null
  proposed: string | null
  detected_ride: string | null
}

export interface RiderLabelWork {
  schema_version: string
  source: string
  items: RiderLabelItem[]
  named: string[]
  finalized: boolean
}

export interface RiderStill {
  ride_id: string
  t_s: number
}

export interface RiderGroup {
  rider_id: string
  label: string
  name: string | null
  ignored: boolean
  kind: string
  ride_ids: string[]
  example_ride_id: string | null
  stills: RiderStill[]
}

export interface RideAssignment {
  ride_id: string
  rider_id: string | null
  confidence: number
  confirmed: boolean
  queued: boolean
  low_evidence: boolean
}

export interface RidersInfo {
  descriptor: string
  riders: RiderGroup[]
  assignments: RideAssignment[]
  join_suggestions: { first: string; second: string; gap_s: number; confidence: number }[]
}

export interface RiderEditRequest {
  op: 'rider_name' | 'rider_same_as' | 'rider_mixed' | 'rider_ignore' | 'ride_rider'
  rider_id?: string
  other_rider_id?: string
  ride_id?: string
  same_as_ride_id?: string
  to_rider_id?: string
  name?: string
  not_name?: string
  ignore?: boolean
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
  session: (id: string) => call<{ probe: SourceInfo; zone_origin: string | null }>(`/sessions/${id}`),
  activity: (id: string) => call<Activity>(`/sessions/${id}/activity`),
  labels: (id: string) => call<LabelWork>(`/sessions/${id}/labels`),
  saveLabels: (id: string, work: LabelWork) =>
    call<LabelWork>(`/sessions/${id}/labels`, { method: 'PUT', body: JSON.stringify(work) }),
  finalize: (id: string) =>
    call<{ rides: number; path: string }>(`/sessions/${id}/labels/finalize`, { method: 'POST' }),
  videoUrl: (id: string) => `/api/sessions/${id}/media/review.mp4`,
  zone: (id: string) => call<ZoneInfo>(`/sessions/${id}/zone`),
  saveZone: (id: string, zone: Zone) =>
    call<{ rides: number; short_attempts: number; face: FaceBand | null }>(`/sessions/${id}/zone`, {
      method: 'PUT',
      body: JSON.stringify(zone),
    }),
  keyframeUrl: (id: string, t: number) => `/api/sessions/${id}/keyframe.jpg?t=${Math.round(t)}`,
  rides: (id: string, rider?: string) =>
    call<Rides>(`/sessions/${id}/rides${rider ? `?rider=${encodeURIComponent(rider)}` : ''}`),
  riders: (id: string) => call<RidersInfo>(`/sessions/${id}/riders`),
  joinRides: (id: string, first: string, second: string) =>
    call<{ riders: RiderGroup[] }>(`/sessions/${id}/joins`, { method: 'POST', body: JSON.stringify({ first, second }) }),
  unjoinRide: (id: string, rideId: string) =>
    call<{ riders: RiderGroup[] }>(`/sessions/${id}/unjoin`, { method: 'POST', body: JSON.stringify({ ride_id: rideId }) }),
  resetRiders: (id: string) =>
    call<{ undone: number }>(`/sessions/${id}/rider-edits/reset`, { method: 'POST' }),
  riderEdit: (id: string, req: RiderEditRequest) =>
    call<{ edit: UserEdit; riders: RiderGroup[] }>(`/sessions/${id}/rider-edits`, {
      method: 'POST',
      body: JSON.stringify(req),
    }),
  edits: (id: string) => call<{ edits: UserEdit[] }>(`/sessions/${id}/edits`),
  edit: (
    id: string,
    op: EditOp,
    target: { ride_id?: string; ride_ids?: string[] },
    payload: Record<string, number> = {},
  ) =>
    call<{ edit: UserEdit; rides: Rides }>(`/sessions/${id}/edits`, {
      method: 'POST',
      body: JSON.stringify({ op, target, payload }),
    }),
  exportClips: (id: string, rides?: string[], reel = false, rider?: string) =>
    call<Job>(`/sessions/${id}/export`, {
      method: 'POST',
      body: JSON.stringify({ rides: rides ?? null, reel, rider: rider ?? null }),
    }),
  reelUrl: (id: string, rider?: string) =>
    `/api/sessions/${id}/media/reel.mp4${rider ? `?rider=${encodeURIComponent(rider)}` : ''}`,
  sources: () => call<SourceVideo[]>('/sources'),
  addSession: (sourcePath: string, minLength: number | null) =>
    call<{ session_id: string; job: Job }>('/sessions', {
      method: 'POST',
      body: JSON.stringify({ source_path: sourcePath, min_length_s: minLength }),
    }),
  riderLabels: (id: string) => call<RiderLabelWork>(`/sessions/${id}/rider-labels`),
  saveRiderLabels: (id: string, work: RiderLabelWork) =>
    call<RiderLabelWork>(`/sessions/${id}/rider-labels`, { method: 'PUT', body: JSON.stringify(work) }),
  finalizeRiderLabels: (id: string) =>
    call<{ rides: number; riders: number }>(`/sessions/${id}/rider-labels/finalize`, { method: 'POST' }),
  riderStillUrl: (id: string, ride: string, t?: number) =>
    `/api/sessions/${id}/media/rider-still.jpg?ride=${ride}${t !== undefined ? `&t=${t.toFixed(2)}` : ''}`,
  rerun: (id: string, minLength: number) =>
    call<Job>(`/sessions/${id}/rerun`, { method: 'POST', body: JSON.stringify({ min_length_s: minLength }) }),
  job: (jobId: string) => call<Job>(`/jobs/${jobId}`),
  thumbUrl: (id: string, t: number) => `/api/sessions/${id}/media/thumb.jpg?t=${(Math.round(t * 2) / 2).toFixed(1)}`,
  clipUrl: (id: string, rideId: string) => `/api/sessions/${id}/media/clips/${rideId}.mp4`,
}

export function clock(seconds: number): string {
  const s = Math.max(0, seconds)
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = (s % 60).toFixed(2).padStart(5, '0')
  return h ? `${h}:${String(m).padStart(2, '0')}:${sec}` : `${String(m).padStart(2, '0')}:${sec}`
}
