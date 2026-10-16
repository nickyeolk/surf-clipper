<script lang="ts">
  // Riders (feature 002): the session's rides grouped by who rode them. Name the riders you
  // care about (e.g. just yourself), merge groups that are the same person, split mixed ones,
  // ignore staff. Every action is an edit the server keeps; regrouping never loses it.
  import { api, clock, type Ride, type RiderEditRequest, type RiderGroup, type RidersInfo, type UserEdit } from '../lib/api'

  let { sessionId }: { sessionId: string } = $props()

  let info = $state<RidersInfo | null>(null)
  let rides = $state<Ride[]>([])
  let edits = $state<UserEdit[]>([])
  let error = $state<string | null>(null)
  let status = $state('')
  let busy = $state(false)
  let video = $state<HTMLVideoElement>()
  let playingRide = $state<string | null>(null)
  let nameDraft = $state<Record<string, string>>({})
  let stopAt: number | null = null

  async function load() {
    try {
      const [r, rs, e] = await Promise.all([api.riders(sessionId), api.rides(sessionId), api.edits(sessionId)])
      info = r
      rides = rs.rides
      edits = e.edits
    } catch (e) {
      error = (e as Error).message
    }
  }
  $effect(() => {
    void load()
  })

  const byId = $derived(new Map(rides.map((r) => [r.ride_id, r])))
  const active = $derived(info ? info.riders.filter((g) => !g.ignored) : [])
  const ignored = $derived(info ? info.riders.filter((g) => g.ignored) : [])
  const riderOps = new Set(['rider_name', 'rider_same_as', 'rider_mixed', 'rider_ignore', 'ride_rider'])
  const undoable = $derived.by(() => {
    const undone = new Set<number>()
    for (const e of [...edits].reverse())
      if (e.op === 'undo' && !undone.has(e.edit_id) && typeof e.payload.edit_id === 'number') undone.add(e.payload.edit_id)
    return [...edits].reverse().find((e) => riderOps.has(e.op) && !undone.has(e.edit_id)) ?? null
  })

  async function act(req: RiderEditRequest, done: string) {
    busy = true
    status = 'regrouping…'
    try {
      await api.riderEdit(sessionId, req)
      await load()
      status = done
    } catch (e) {
      status = (e as Error).message
    } finally {
      busy = false
    }
  }
  function name(g: RiderGroup) {
    const n = (nameDraft[g.rider_id] ?? '').trim()
    if (n) void act({ op: 'rider_name', rider_id: g.rider_id, name: n }, `named ${n}`)
  }
  function sameAs(g: RiderGroup, other: string) {
    if (other) void act({ op: 'rider_same_as', rider_id: g.rider_id, other_rider_id: other }, `${g.label} merged`)
  }
  function mixed(g: RiderGroup) {
    if (confirm(`Split ${g.label} into two riders?`)) void act({ op: 'rider_mixed', rider_id: g.rider_id }, `${g.label} split in two`)
  }
  function ignore(g: RiderGroup, value: boolean) {
    void act({ op: 'rider_ignore', rider_id: g.rider_id, ignore: value }, value ? `${g.label} ignored` : `${g.label} back`)
  }
  async function undo() {
    if (!undoable) return
    busy = true
    try {
      await api.edit(sessionId, 'undo', {}, { edit_id: undoable.edit_id })
      await load()
      status = 'undone'
    } catch (e) {
      status = (e as Error).message
    } finally {
      busy = false
    }
  }
  function play(rideId: string) {
    const r = byId.get(rideId)
    if (!r || !video) return
    playingRide = rideId
    video.currentTime = r.clip_start_s
    stopAt = r.clip_end_s
    void video.play()
  }
  function ontimeupdate() {
    if (video && stopAt !== null && video.currentTime >= stopAt) {
      video.pause()
      stopAt = null
    }
  }
  const still = (rideId: string, t?: number) => api.riderStillUrl(sessionId, rideId, t)
  const reviewHref = (g: RiderGroup) => `#/review/${sessionId}/rider/${encodeURIComponent(g.label)}`
</script>

{#if error}
  <p class="error">{error}</p>
{:else if !info}
  <p class="muted">Loading…</p>
{:else}
  <div class="riders-view">
    <section class="side">
      <h1>Riders <span class="muted small">{active.length} riders · {rides.length} rides</span></h1>
      <!-- svelte-ignore a11y_media_has_caption -->
      <video bind:this={video} src={api.videoUrl(sessionId)} preload="metadata" {ontimeupdate} controls></video>
      <p class="small">{busy ? 'regrouping…' : status}</p>
      <div class="row">
        <button onclick={undo} disabled={!undoable || busy}>undo</button>
        <a class="button secondary" href={`#/review/${sessionId}`}>Review all rides</a>
      </div>
      <details class="help small" open>
        <summary>How it works</summary>
        <p>
          Each card is one person, as far as the tool can tell from clothes, board and build.
          Name the riders you care about — just yourself is fine. If one person appears in two
          cards, use <em>same as</em>; if a card mixes two people, press <em>mixed</em> to split
          it; <em>ignore</em> hides staff or people not riding. Then <em>play &amp; export</em>
          opens that rider's rides in Review, where you can play them back to back or export one
          video.
        </p>
      </details>
    </section>

    <section class="cards">
      {#each active as g (g.rider_id)}
        <div class="card">
          <div class="head">
            <strong>{g.label}</strong>
            <span class="muted small">{g.ride_ids.length} ride{g.ride_ids.length === 1 ? '' : 's'}</span>
          </div>
          <div class="stills">
            {#each g.stills.slice(0, 6) as s (s.ride_id)}
              <button class="still" class:playing={playingRide === s.ride_id} onclick={() => play(s.ride_id)}
                title={`Play ${byId.get(s.ride_id) ? clock(byId.get(s.ride_id)!.start_s) : ''}`}>
                <img loading="lazy" alt="" src={still(s.ride_id)} />
              </button>
            {/each}
          </div>
          <div class="row">
            <input class="text" placeholder={g.name ? `rename ${g.name}` : 'who is this?'}
              bind:value={nameDraft[g.rider_id]} onkeydown={(e) => e.key === 'Enter' && name(g)} disabled={busy} />
            <button onclick={() => name(g)} disabled={busy}>name</button>
          </div>
          <div class="row small">
            <select disabled={busy} onchange={(e) => sameAs(g, (e.currentTarget as HTMLSelectElement).value)}>
              <option value="">same as…</option>
              {#each active.filter((o) => o.rider_id !== g.rider_id) as o (o.rider_id)}
                <option value={o.rider_id}>{o.label}</option>
              {/each}
            </select>
            <button onclick={() => mixed(g)} disabled={busy || g.ride_ids.length < 2}
              title="This card shows two different people">mixed</button>
            <button onclick={() => ignore(g, true)} disabled={busy} title="Staff, or not riding">ignore</button>
            <a class="button" href={reviewHref(g)}>play &amp; export</a>
          </div>
        </div>
      {/each}
      {#if ignored.length}
        <h2 class="small muted">Ignored</h2>
        {#each ignored as g (g.rider_id)}
          <div class="card dim">
            <div class="head">
              <strong>{g.label}</strong> <span class="muted small">{g.ride_ids.length} rides</span>
              <button onclick={() => ignore(g, false)} disabled={busy}>bring back</button>
            </div>
          </div>
        {/each}
      {/if}
    </section>
  </div>
{/if}

<style>
  .riders-view {
    display: grid;
    grid-template-columns: 380px minmax(0, 1fr);
    gap: 16px;
    align-items: start;
  }
  .side {
    position: sticky;
    top: 8px;
  }
  .side video {
    max-height: 240px;
  }
  .cards {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
    gap: 10px;
  }
  .cards h2 {
    grid-column: 1 / -1;
    margin: 6px 0 0;
  }
  .card {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 8px;
  }
  .card.dim {
    opacity: 0.6;
  }
  .head {
    display: flex;
    gap: 8px;
    align-items: baseline;
  }
  .stills {
    display: flex;
    gap: 4px;
    margin: 6px 0;
    overflow: hidden;
  }
  .still {
    padding: 0;
    height: 110px;
    background: #000;
    border: 2px solid transparent;
    flex: none;
  }
  .still.playing {
    border-color: var(--accent);
  }
  .still img {
    height: 106px;
    display: block;
  }
  .text {
    flex: 1;
    background: var(--bg);
    color: var(--text);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 4px 6px;
    font: inherit;
  }
  select {
    background: var(--bg);
    color: var(--text);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 4px;
    font: inherit;
  }
</style>
