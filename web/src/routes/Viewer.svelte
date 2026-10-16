<script lang="ts">
  // Exports (003 US3): the session's compilations, exported clips per rider and saved stills,
  // played at full quality from the exported files themselves. Stills saved here are taken from
  // the source at the matching time.
  import { api, clock, type ClipInfo, type CompilationInfo, type ExportsInfo, type StillInfo } from '../lib/api'
  import Player, { type Chapter } from '../lib/Player.svelte'

  let { sessionId }: { sessionId: string } = $props()

  type Pick = { kind: 'comp'; comp: CompilationInfo } | { kind: 'clip'; clip: ClipInfo; rider: string }
  let info = $state<ExportsInfo | null>(null)
  let error = $state<string | null>(null)
  let pick = $state<Pick | null>(null)
  let status = $state('')

  async function load() {
    try {
      info = await api.exports(sessionId)
      if (!pick) {
        const c = info.compilations[0]
        const r = info.riders[0]?.clips[0] ?? info.unassigned[0]
        pick = c ? { kind: 'comp', comp: c } : r ? { kind: 'clip', clip: r, rider: info.riders[0]?.rider ?? '' } : null
      }
    } catch (e) {
      error = (e as Error).message
    }
  }
  $effect(() => {
    void load()
  })

  const src = $derived(pick?.kind === 'comp' ? pick.comp.url : pick?.kind === 'clip' ? pick.clip.url : '')
  const chapters = $derived<Chapter[]>(
    pick?.kind === 'comp'
      ? pick.comp.rides.map((r) => ({ start: r.offset_s, end: r.offset_s + r.duration_s, label: r.caption }))
      : [],
  )

  /** Source time of a time in the playing file. */
  function sourceTime(t: number): number | null {
    if (pick?.kind === 'clip') return pick.clip.clip_start_s + t
    if (pick?.kind === 'comp') {
      const r = pick.comp.rides.find((x) => t >= x.offset_s && t < x.offset_s + x.duration_s)
      return r ? r.clip_start_s + (t - r.offset_s) : null
    }
    return null
  }
  async function saveStill(t: number) {
    const s = sourceTime(t)
    if (s === null) return
    try {
      const still = await api.saveStill(sessionId, s)
      status = `saved frame ${still.frame}`
      await load()
    } catch (e) {
      status = `still not saved: ${(e as Error).message}`
    }
  }
  async function removeStill(s: StillInfo) {
    if (!confirm(`Delete the still ${s.name}?`)) return
    await api.deleteStill(sessionId, s.name)
    await load()
  }
  const isPicked = (c: ClipInfo) => pick?.kind === 'clip' && pick.clip.ride_id === c.ride_id
</script>

{#if error}
  <p class="error">{error}</p>
{:else if !info}
  <p class="muted">Loading…</p>
{:else}
  <div class="viewer">
    <section>
      <div class="titlebar">
        <h1>
          Exports
          <span class="muted small">
            {#if pick?.kind === 'comp'}{pick.comp.rider} · compilation of {pick.comp.rides.length} rides
            {:else if pick?.kind === 'clip'}{pick.rider ? `${pick.rider} · ` : ''}{pick.clip.ride_id} · {clock(pick.clip.clip_start_s)}{/if}
          </span>
        </h1>
        <span class="small muted">{status}</span>
      </div>
      {#if pick}
        <Player {src} fps={info.fps} {chapters} onstill={saveStill} />
      {:else}
        <p class="muted">
          Nothing exported yet. Export clips in <a href={`#/review/${sessionId}`}>Review</a> or a
          compilation in <a href={`#/riders/${sessionId}`}>Riders</a>.
        </p>
      {/if}

      {#if info.stills.length}
        <h2>Stills <span class="muted small">{info.stills.length} · full resolution, in clips/stills</span></h2>
        <div class="stills">
          {#each info.stills as s (s.name)}
            <figure>
              <a href={s.url} target="_blank" rel="noreferrer" title="Open full size">
                <img loading="lazy" src={s.url} alt={s.name} />
              </a>
              <figcaption class="small">
                {s.rider ?? s.ride_id ?? ''} · {clock(s.t_s)} · {s.width}×{s.height}
                <a href={`${s.url}?download=1`}>download</a>
                <button class="link" onclick={() => removeStill(s)}>delete</button>
              </figcaption>
            </figure>
          {/each}
        </div>
      {/if}
    </section>

    <aside class="panel">
      <div class="row small">
        <a href={`#/riders/${sessionId}`}>Riders</a> · <a href={`#/review/${sessionId}`}>Review</a>
      </div>
      <h2>Compilations</h2>
      {#if info.compilations.length === 0}
        <p class="small muted">None yet: <em>compilation</em> on a rider's card in Riders.</p>
      {/if}
      {#each info.compilations as c (c.rider)}
        <button class="item" class:active={pick?.kind === 'comp' && pick.comp.rider === c.rider}
          onclick={() => (pick = { kind: 'comp', comp: c })}>
          <strong>{c.rider}</strong> <span class="muted small">{c.rides.length} rides</span>
          {#if !c.current}<span class="tag" title="The rider's rides or name changed since: make it again in Riders">out of date</span>{/if}
        </button>
      {/each}
      {#each info.riders as g (g.rider)}
        <h2>{g.rider} <span class="muted small">{g.clips.length} clips</span></h2>
        {#each g.clips as c (c.ride_id)}
          <button class="item" class:active={isPicked(c)} onclick={() => (pick = { kind: 'clip', clip: c, rider: g.rider })}>
            {clock(c.clip_start_s)} <span class="muted small">{c.duration_s.toFixed(0)} s</span>
          </button>
        {/each}
      {/each}
      {#if info.unassigned.length}
        <h2>Other clips <span class="muted small">{info.unassigned.length}</span></h2>
        {#each info.unassigned as c (c.ride_id)}
          <button class="item" class:active={isPicked(c)} onclick={() => (pick = { kind: 'clip', clip: c, rider: '' })}>
            {clock(c.clip_start_s)} <span class="muted small">{c.duration_s.toFixed(0)} s</span>
          </button>
        {/each}
      {/if}
      <p class="small muted keys">
        Space play · , . frame · Shift+←/→ 1 s · [ ] previous/next ride · c save still · − + speed
      </p>
    </aside>
  </div>
{/if}

<style>
  .viewer {
    display: grid;
    grid-template-columns: minmax(0, 1fr) 280px;
    gap: 16px;
    align-items: start;
  }
  .titlebar {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    gap: 12px;
  }
  .panel {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 10px 12px;
    max-height: calc(100vh - 90px);
    overflow-y: auto;
  }
  h2 {
    font-size: 14px;
    margin: 14px 0 4px;
  }
  .item {
    display: block;
    width: 100%;
    text-align: left;
    margin: 2px 0;
    background: var(--bg);
  }
  .item.active {
    border-color: var(--accent);
  }
  .stills {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
    gap: 10px;
  }
  figure {
    margin: 0;
  }
  figure img {
    width: 100%;
    border-radius: 4px;
    display: block;
  }
  .link {
    background: none;
    border: none;
    color: var(--accent);
    padding: 0;
    cursor: pointer;
  }
  .keys {
    margin-top: 16px;
  }
  @media (max-width: 800px) {
    .viewer {
      grid-template-columns: 1fr;
    }
  }
</style>
