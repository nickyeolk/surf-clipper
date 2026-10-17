<script lang="ts">
  // Best rides (004 US3): your analysed rides by score, best first, with what the score is made
  // of. Star the rides you love: the score learns from your stars (across sessions) what you
  // consider a good ride. Pick rides and make a captioned compilation of just those.
  import { api, clock, type Job, type RideAnalysis } from '../lib/api'

  let { sessionId }: { sessionId: string } = $props()

  let rides = $state<RideAnalysis[] | null>(null)
  let error = $state('')
  let rider = $state('')
  let selected = $state<Set<string>>(new Set())
  let playing = $state<RideAnalysis | null>(null)
  let video = $state<HTMLVideoElement>()
  let job = $state<Job | null>(null)
  let status = $state('')

  async function load() {
    try {
      const a = await api.analysis(sessionId)
      rides = a.rides
      if (!rider) rider = a.rides[0]?.rider ?? ''
    } catch (e) {
      error = (e as Error).message
    }
  }
  $effect(() => {
    void load()
  })

  const riderNames = $derived([...new Set((rides ?? []).map((r) => r.rider))])
  const list = $derived(
    (rides ?? []).filter((r) => r.rider === rider).sort((a, b) => (b.score?.value ?? 0) - (a.score?.value ?? 0)),
  )
  const stars = $derived(list.filter((r) => r.starred).length)

  async function star(r: RideAnalysis) {
    await api.star(sessionId, r.ride_id, !r.starred)
    await load() // scores may change: they learn from stars
    status = r.starred ? 'unstarred' : 'starred'
  }
  function play(r: RideAnalysis) {
    playing = r
    queueMicrotask(() => {
      if (!video) return
      video.currentTime = Math.max(0, r.span[0] - 1)
      void video.play()
    })
  }
  function ontimeupdate() {
    if (video && playing && video.currentTime > playing.span[1] + 1) video.pause()
  }
  function toggle(id: string) {
    const s = new Set(selected)
    if (s.has(id)) s.delete(id)
    else s.add(id)
    selected = s
  }
  function top(n: number) {
    selected = new Set(list.slice(0, n).map((r) => r.ride_id))
  }
  async function compile() {
    if (!selected.size) return
    try {
      job = await api.exportClips(sessionId, [...selected], true, rider)
      while (job.status === 'queued' || job.status === 'running') {
        await new Promise((r) => setTimeout(r, 1000))
        job = await api.job(job.job_id)
      }
    } catch (e) {
      status = (e as Error).message
    }
  }
</script>

{#if error}
  <p class="error">{error}</p>
  <p class="small">Name yourself in <a href={`#/riders/${sessionId}`}>Riders</a>, then <em>Analyse rides</em> on Sessions.</p>
{:else if !rides}
  <p class="muted">Loading…</p>
{:else}
  <div class="best">
    <section>
      <div class="titlebar">
        <h1>Best rides
          {#if riderNames.length > 1}
            <select bind:value={rider}>
              {#each riderNames as n}<option value={n}>{n}</option>{/each}
            </select>
          {:else}<span class="muted small">{rider}</span>{/if}
        </h1>
        <span class="small muted">{status}</span>
      </div>
      <p class="small muted">
        ★ the rides you love. Until you have starred a few (5+, across sessions) the score uses
        general rules: long, clean, deep and steady rides first. After that it follows your stars.
        {stars} starred here.
      </p>
      <div class="row">
        <button onclick={() => top(5)}>select top 5</button>
        <button onclick={() => (selected = new Set())} disabled={!selected.size}>clear</button>
        <button class="primary" onclick={compile} disabled={!selected.size || job?.status === 'running' || job?.status === 'queued'}>
          Compilation of {selected.size} selected
        </button>
        {#if job}
          <span class="small">
            {#if job.status === 'failed'}<span class="error">{job.error}</span>
            {:else if job.status === 'done'}ready → <a href={`#/viewer/${sessionId}`}>watch in Exports</a>
            {:else}<progress max="1" value={job.progress}></progress> {job.message}{/if}
          </span>
        {/if}
      </div>
      <ol class="rides">
        {#each list as r, i (r.ride_id)}
          <li class:playing={playing?.ride_id === r.ride_id}>
            <input type="checkbox" checked={selected.has(r.ride_id)} onchange={() => toggle(r.ride_id)} aria-label="select" />
            <span class="rank">{i + 1}</span>
            <button class="thumb" onclick={() => play(r)} title="Play">
              <img loading="lazy" alt="" src={api.thumbUrl(sessionId, (r.span[0] + r.span[1]) / 2)} />
            </button>
            <span class="meta">
              <span><strong>{r.score?.value.toFixed(0) ?? '–'}</strong> <span class="bar"><span style:width="{r.score?.value ?? 0}%"></span></span></span>
              <span class="small">{r.score?.explanation ?? ''}</span>
              <span class="small muted">{clock(r.span[0]).replace(/\.\d+$/, '')} · {r.summary.length_s.toFixed(0)} s · {r.ending}{r.tricks.length ? ` · ${r.tricks.map((t) => t.name).join(', ')}` : ''}</span>
            </span>
            <button class="star" class:on={r.starred} onclick={() => star(r)} title={r.starred ? 'Unstar' : 'Star: a ride you love'}>{r.starred ? '★' : '☆'}</button>
            <a class="small" href={`#/compare?a=${sessionId}:${r.ride_id}`}>compare</a>
          </li>
        {/each}
      </ol>
    </section>
    <aside>
      {#if playing}
        <!-- svelte-ignore a11y_media_has_caption -->
        <video bind:this={video} src={api.videoUrl(sessionId)} controls {ontimeupdate}></video>
        <p class="small">{clock(playing.span[0])} · score {playing.score?.value.toFixed(0)}</p>
      {:else}
        <p class="muted small">Click a thumbnail to play the ride here.</p>
      {/if}
    </aside>
  </div>
{/if}

<style>
  .best {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(280px, 40%);
    gap: 16px;
    align-items: start;
  }
  aside {
    position: sticky;
    top: 8px;
  }
  .titlebar {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
  }
  .row {
    display: flex;
    gap: 6px;
    align-items: center;
    flex-wrap: wrap;
    margin: 8px 0;
  }
  .rides {
    list-style: none;
    padding: 0;
    margin: 0;
  }
  .rides li {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 4px;
    border-bottom: 1px solid var(--border);
  }
  .rides li.playing {
    background: var(--panel);
  }
  .rank {
    width: 1.6em;
    text-align: right;
    color: var(--muted);
  }
  .thumb {
    padding: 0;
    border: none;
    background: none;
  }
  .thumb img {
    width: 120px;
    border-radius: 4px;
    display: block;
  }
  .meta {
    display: flex;
    flex-direction: column;
    flex: 1;
    gap: 2px;
  }
  .bar {
    display: inline-block;
    width: 120px;
    height: 6px;
    background: var(--border);
    border-radius: 3px;
    vertical-align: middle;
  }
  .bar span {
    display: block;
    height: 100%;
    background: var(--ok);
    border-radius: 3px;
  }
  .star {
    font-size: 20px;
    background: none;
    border: none;
    color: var(--muted);
    cursor: pointer;
  }
  .star.on {
    color: var(--q);
  }
  select {
    background: var(--bg);
    color: var(--text);
    border: 1px solid var(--border);
    border-radius: 6px;
  }
</style>
