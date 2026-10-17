<script lang="ts">
  // Pick the surfer in a reference clip (004 US2): scrub to a moment where they're visible,
  // click them; the tool follows that person through the clip and analyses them.
  import { api, clock, type Job, type People, type ReferenceClip } from '../lib/api'

  let { sessionId }: { sessionId: string } = $props()

  let ref = $state<ReferenceClip | null>(null)
  let t = $state(0)
  let people = $state<People | null>(null)
  let job = $state<Job | null>(null)
  let error = $state('')
  let img = $state<HTMLImageElement>()

  async function loadRef() {
    const all = await api.references()
    ref = all.find((r) => r.session_id === sessionId) ?? null
    if (ref?.duration_s && t === 0) t = Math.floor(ref.duration_s / 3)
  }
  $effect(() => {
    void loadRef()
  })
  $effect(() => {
    const at = t
    if (!ref || ref.status === 'working') return
    api.people(sessionId, at).then((p) => (people = p)).catch((e) => (error = e.message))
  })

  async function pick(e: MouseEvent) {
    if (!people || !img) return
    const r = img.getBoundingClientRect()
    const x = ((e.clientX - r.left) / r.width) * people.width
    const y = ((e.clientY - r.top) / r.height) * people.height
    try {
      job = await api.pickSurfer(sessionId, t, x, y)
      while (job.status === 'queued' || job.status === 'running') {
        await new Promise((res) => setTimeout(res, 1000))
        job = await api.job(job.job_id)
      }
      await loadRef()
    } catch (err) {
      error = (err as Error).message
    }
  }
  const pct = (v: number, of: number) => `${(v / of) * 100}%`
</script>

{#if !ref}
  <p class="muted">Loading…</p>
{:else}
  <h1>{ref.video} <span class="muted small">reference clip</span></h1>
  {#if ref.status === 'working'}
    <p>Importing: {ref.job?.message ?? ''} <progress max="1" value={ref.job?.progress ?? 0}></progress></p>
    <button onclick={loadRef}>refresh</button>
  {:else}
    <p class="small">
      Scrub to a moment where the surfer is clearly visible and <strong>click them</strong>. The
      tool follows that person through the clip.
      {#if ref.status === 'ready'}Already chosen; click again to pick someone else.{/if}
    </p>
    <div class="row">
      <input type="range" min="0" max={Math.floor(ref.duration_s ?? 0)} step="1" bind:value={t} />
      <span class="time">{clock(t)}</span>
    </div>
    <div class="frame">
      <!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_noninteractive_element_interactions -->
      <img bind:this={img} src={api.keyframeUrl(sessionId, t)} alt="frame at {clock(t)}" onclick={pick} />
      {#if people}
        {#each people.people as p (p.track_id)}
          <span class="box" style:left={pct(p.box[0], people.width)} style:top={pct(p.box[1], people.height)}
            style:width={pct(p.box[2] - p.box[0], people.width)} style:height={pct(p.box[3] - p.box[1], people.height)}></span>
        {/each}
      {/if}
    </div>
    {#if job && (job.status === 'queued' || job.status === 'running')}
      <p>Analysing the surfer… <progress max="1" value={job.progress}></progress> {job.message}</p>
    {:else if job?.status === 'failed'}
      <p class="error">{job.error}</p>
    {/if}
    {#if ref.status === 'ready'}
      <p><a class="button primary" href={`#/compare?b=${sessionId}:ref`}>Compare with this surfer →</a></p>
    {/if}
    {#if error}<p class="error small">{error}</p>{/if}
  {/if}
{/if}

<style>
  .frame {
    position: relative;
    display: inline-block;
    max-width: 100%;
  }
  .frame img {
    max-width: 100%;
    max-height: 70vh;
    display: block;
    cursor: crosshair;
    border-radius: 6px;
  }
  .box {
    position: absolute;
    border: 2px solid var(--q);
    border-radius: 3px;
    pointer-events: none;
  }
  .row {
    display: flex;
    gap: 8px;
    align-items: center;
  }
  input[type='range'] {
    width: min(600px, 80vw);
  }
  .time {
    font-variant-numeric: tabular-nums;
  }
</style>
