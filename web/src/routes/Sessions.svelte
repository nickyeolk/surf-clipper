<script lang="ts">
  // Sessions: add a video from the footage folder, follow its processing, then go to the next
  // step (zone, then review). Polls while anything is processing.
  import { api, clock, type Health, type Job, type SessionSummary, type SourceVideo } from '../lib/api'

  let sessions = $state<SessionSummary[] | null>(null)
  let sources = $state<SourceVideo[]>([])
  let error = $state<string | null>(null)
  let chosen = $state('')
  let minLength = $state(10)
  let adding = $state(false)
  let addError = $state('')

  // 003: what the start needs to tell the user (GPU, models), and stopping without a terminal
  let health = $state<Health | null>(null)
  let modelJob = $state<Job | null>(null)
  let stopped = $state(false)
  $effect(() => {
    api.health().then((h) => (health = h)).catch(() => {})
  })
  async function downloadModels() {
    try {
      modelJob = await api.downloadModels()
      while (modelJob.status === 'queued' || modelJob.status === 'running') {
        await new Promise((r) => setTimeout(r, 1500))
        modelJob = await api.job(modelJob.job_id)
      }
      health = await api.health()
    } catch (e) {
      addError = (e as Error).message
    }
  }
  async function stop() {
    const busy = sessions?.some((s) => s.job && (s.job.status === 'queued' || s.job.status === 'running'))
    const ask = busy
      ? 'Stop Surf Clipper? Work in progress stops and continues from where it got to next time.'
      : 'Stop Surf Clipper?'
    if (!confirm(ask)) return
    await api.shutdown().catch(() => {})
    stopped = true
  }

  async function load() {
    try {
      ;[sessions, sources] = await Promise.all([api.sessions(), api.sources()])
    } catch (e) {
      error = (e as Error).message
    }
  }
  $effect(() => {
    void load()
    const timer = setInterval(() => {
      if (sessions?.some((s) => s.job)) void load()
    }, 2000)
    return () => clearInterval(timer)
  })

  const newSources = $derived(sources.filter((s) => !s.session_id))
  const gb = (b: number) => `${(b / 1e9).toFixed(1)} GB`

  async function add() {
    if (!chosen) return
    adding = true
    addError = ''
    try {
      await api.addSession(chosen, minLength)
      chosen = ''
      await load()
    } catch (e) {
      addError = (e as Error).message
    } finally {
      adding = false
    }
  }
</script>

<div class="title">
  <h1>Sessions</h1>
  {#if !stopped}<button class="stop" onclick={stop} title="Stop the tool (start it again from the desktop shortcut)">Stop</button>{/if}
</div>

{#if stopped}
  <p class="banner">Surf Clipper is stopped. Start it again with the <strong>Surf Clipper</strong> shortcut on the Desktop; you can close this tab.</p>
{:else if health && (!health.gpu || !health.models.detector || !health.models.embedder)}
  <div class="banner">
    {#if !health.gpu}
      <p>No NVIDIA GPU found: everything works, but analysis and exports will be much slower.</p>
    {/if}
    {#if !health.models.detector || !health.models.embedder}
      <p>
        The {[!health.models.detector && 'person detector', !health.models.embedder && 'rider model'].filter(Boolean).join(' and ')}
        {!health.models.detector && !health.models.embedder ? 'are' : 'is'} not downloaded yet (needed once, about 100 MB).
        {#if modelJob && (modelJob.status === 'queued' || modelJob.status === 'running')}
          <progress max="1" value={modelJob.progress}></progress> {modelJob.message}
        {:else}
          <button class="primary" onclick={downloadModels}>Download models</button>
          {#if modelJob?.status === 'failed'}<span class="error small">failed: {modelJob.error}</span>{/if}
        {/if}
      </p>
    {/if}
  </div>
{/if}

{#if stopped}
  <!-- nothing more to show -->
{:else if error}
  <p class="error">Could not load sessions: {error}</p>
{:else if sessions === null}
  <p class="muted">Loading…</p>
{:else}
  <div class="add">
    <label>
      Add a video
      <select bind:value={chosen} disabled={adding || newSources.length === 0}>
        <option value="">{newSources.length ? 'choose from your footage folder…' : 'no new videos in the footage folder'}</option>
        {#each newSources as s (s.path)}
          <option value={s.path}>{s.name} ({gb(s.size_bytes)})</option>
        {/each}
      </select>
    </label>
    <label title="Rides shorter than this are listed as short attempts">
      min ride <input type="number" min="1" step="1" bind:value={minLength} /> s
    </label>
    <button class="primary" disabled={!chosen || adding} onclick={add}>Add & analyse</button>
    {#if addError}<span class="error small">{addError}</span>{/if}
    <p class="small muted">
      Analysis takes roughly an hour per hour of video (HDR takes longest). You can close the
      browser meanwhile; it keeps going while the server runs. The wave zone is set from the
      riders automatically when possible; a quick check in the zone editor improves the clips.
    </p>
  </div>

  {#if sessions.length === 0}
    <p class="muted">No sessions yet.</p>
  {:else}
    <table class="sessions">
      <thead>
        <tr>
          <th>Video</th>
          <th>Length</th>
          <th>Rides</th>
          <th>Short</th>
          <th>Exported</th>
          <th>Labels</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {#each sessions as s (s.session_id)}
          <tr>
            <td>{s.name}</td>
            <td>{s.duration_s ? clock(s.duration_s).replace(/\.\d+$/, '') : '–'}</td>
            <td>{s.rides ?? '–'}</td>
            <td>{s.short_attempts ?? '–'}</td>
            <td>{s.rides !== null ? s.exported : '–'}</td>
            <td>
              {#if s.labels_final}
                <span class="tag ok">done</span>
              {:else if s.labels_total}
                <progress max={s.labels_total} value={s.labels_done}></progress>
                {s.labels_done}/{s.labels_total}
              {:else}
                –
              {/if}
            </td>
            <td class="actions">
              {#if s.job && (s.job.status === 'queued' || s.job.status === 'running')}
                <progress max="1" value={s.job.progress}></progress>
                <span class="small">{s.job.status === 'queued' ? 'waiting for the GPU…' : s.job.message} ({Math.round(s.job.progress * 100)}%)</span>
              {:else if s.job?.status === 'failed'}
                <span class="error small">failed: {s.job.error}</span>
              {:else if s.analysed && !s.zone_confirmed}
                <a class="button" href={`#/zone/${s.session_id}`}>Set wave zone →</a>
              {:else}
                <a class="button secondary" href={`#/zone/${s.session_id}`}
                  title={s.zone_confirmed && !s.zone_checked ? 'Set automatically from the proposal: worth a quick check' : ''}
                  >Zone{s.zone_confirmed && !s.zone_checked ? ' (not checked)' : ''}</a>
                {#if s.has_review_copy && s.rides !== null}
                  <a class="button" href={`#/review/${s.session_id}`}>Review</a>
                  <a class="button" href={`#/riders/${s.session_id}`}>Riders</a>
                  <a class="button secondary" href={`#/viewer/${s.session_id}`}
                    title="Watch exported clips and compilations at full quality; saved stills">Exports</a>
                  <a class="button secondary" href={`#/label/${s.session_id}`}>Label</a>
                  {#if s.labels_final}
                    <a class="button secondary" href={`#/rider-labels/${s.session_id}`}
                      title="Say who rode each labelled ride (for measuring rider grouping)">Label riders</a>
                  {/if}
                {:else}
                  <span class="muted small">not analysed</span>
                {/if}
              {/if}
            </td>
          </tr>
        {/each}
      </tbody>
    </table>
  {/if}
{/if}

<style>
  .title {
    display: flex;
    align-items: center;
    justify-content: space-between;
    max-width: 1000px;
  }
  .stop {
    background: var(--panel);
    border-color: var(--border);
  }
  .banner {
    background: var(--panel);
    border: 1px solid var(--border);
    border-left: 3px solid var(--q);
    border-radius: 8px;
    padding: 6px 12px;
    margin-bottom: 16px;
    max-width: 1000px;
  }
  .banner p {
    margin: 4px 0;
  }
  .add {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    align-items: center;
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 10px 12px;
    margin-bottom: 16px;
    max-width: 1000px;
  }
  .add p {
    flex-basis: 100%;
    margin: 0;
  }
  select,
  input {
    background: var(--bg);
    color: var(--text);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 4px 6px;
    font: inherit;
  }
  input[type='number'] {
    width: 4em;
  }
  .actions {
    white-space: nowrap;
  }
</style>
