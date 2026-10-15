<script lang="ts">
  import { api, clock, type SessionSummary } from '../lib/api'

  let sessions = $state<SessionSummary[] | null>(null)
  let error = $state<string | null>(null)

  api.sessions().then((s) => (sessions = s)).catch((e) => (error = e.message))
</script>

<h1>Sessions</h1>

{#if error}
  <p class="error">Could not load sessions: {error}</p>
{:else if sessions === null}
  <p class="muted">Loading…</p>
{:else if sessions.length === 0}
  <p class="muted">
    No sessions yet. Run <code>surfclip zone</code> and <code>surfclip run</code> on a video first.
  </p>
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
          <td>
            <a class="button secondary" href={`#/zone/${s.session_id}`}>Zone</a>
            {#if s.has_review_copy && s.rides !== null}
              <a class="button" href={`#/review/${s.session_id}`}>Review</a>
            <a class="button secondary" href={`#/label/${s.session_id}`}>Label</a>
            {:else}
              <span class="muted" title="Run `surfclip run` to make the review copy">not ready</span>
            {/if}
          </td>
        </tr>
      {/each}
    </tbody>
  </table>
{/if}
