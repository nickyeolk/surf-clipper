<script lang="ts">
  // Riders (feature 002): the session's rides grouped by who rode them. Name the riders you
  // care about (e.g. just yourself), open a card to see all its rides and move single rides,
  // merge cards that are one person, split mixed ones, ignore staff. Every action is an edit the
  // server keeps; regrouping never loses it.
  import { api, clock, type Job, type Ride, type RiderEditRequest, type RiderGroup, type RidersInfo, type UserEdit } from '../lib/api'

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
  let open = $state<Record<string, boolean>>({})
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

  async function act(req: RiderEditRequest, done: (before: number, after: number) => string) {
    busy = true
    status = 'regrouping…'
    const before = active.length
    try {
      await api.riderEdit(sessionId, req)
      await load()
      status = done(before, active.length)
    } catch (e) {
      status = (e as Error).message
    } finally {
      busy = false
    }
  }
  function name(g: RiderGroup) {
    const n = (nameDraft[g.rider_id] ?? '').trim()
    if (!n) return
    nameDraft[g.rider_id] = ''
    void act({ op: 'rider_name', rider_id: g.rider_id, name: n }, () => `named ${n}`)
  }
  function sameAs(g: RiderGroup, select: HTMLSelectElement) {
    const other = active.find((o) => o.rider_id === select.value)
    select.value = ''
    if (!other) return
    if (!confirm(`Merge ${g.label} (${g.ride_ids.length} rides) and ${other.label} (${other.ride_ids.length} rides) into one rider?`)) return
    void act({ op: 'rider_same_as', rider_id: g.rider_id, other_rider_id: other.rider_id }, () => `${g.label} and ${other.label} merged`)
  }
  function mixed(g: RiderGroup) {
    if (!confirm(`${g.label} shows two different people? It will be split into two cards by appearance.`)) return
    void act({ op: 'rider_mixed', rider_id: g.rider_id }, (b, a) =>
      a > b ? `${g.label} split into two cards` : `split ${g.label}; the halves regrouped with other cards — open them to check`)
  }
  function ignore(g: RiderGroup, value: boolean) {
    void act({ op: 'rider_ignore', rider_id: g.rider_id, ignore: value }, () => (value ? `${g.label} ignored` : `${g.label} back`))
  }
  function move(rideId: string, select: HTMLSelectElement) {
    const to = select.value
    select.value = ''
    if (!to) return
    if (to === '__new') {
      const n = prompt('Name of the rider of this ride')?.trim()
      if (n) void act({ op: 'ride_rider', ride_id: rideId, name: n }, () => `ride moved to ${n}`)
      return
    }
    const target = active.find((g) => g.rider_id === to)
    void act({ op: 'ride_rider', ride_id: rideId, to_rider_id: to }, () => `ride moved to ${target?.label ?? 'another rider'}`)
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
  async function joinPair(first: string, second: string) {
    busy = true
    try {
      await api.joinRides(sessionId, first, second)
      await load()
      status = 'rides joined'
    } catch (e) {
      status = (e as Error).message
    } finally {
      busy = false
    }
  }
  async function unjoin(rideId: string) {
    if (!confirm('Split this ride back into the two parts it was joined from?')) return
    busy = true
    try {
      await api.unjoinRide(sessionId, rideId)
      await load()
      status = 'ride split back in two'
    } catch (e) {
      status = (e as Error).message
    } finally {
      busy = false
    }
  }
  let exportJob = $state<Job | null>(null)
  async function exportAll() {
    try {
      exportJob = await api.exportRiderFolders(sessionId)
      while (exportJob && (exportJob.status === 'queued' || exportJob.status === 'running')) {
        await new Promise((r) => setTimeout(r, 1000))
        exportJob = await api.job(exportJob.job_id)
      }
    } catch (e) {
      status = (e as Error).message
    }
  }
  async function startOver() {
    if (!confirm('Undo every rider change in this session (names, merges, splits, moves)?')) return
    busy = true
    try {
      const r = await api.resetRiders(sessionId)
      await load()
      status = `started over (${r.undone} changes undone)`
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
  const still = (rideId: string) => api.riderStillUrl(sessionId, rideId)
  const reviewHref = (g: RiderGroup) => `#/review/${sessionId}/rider/${encodeURIComponent(g.label)}`
  const ridesOf = (g: RiderGroup) =>
    g.ride_ids.map((id) => byId.get(id)).filter((r): r is Ride => !!r).sort((a, b) => a.start_s - b.start_s)
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
      <p class="small status">{busy ? 'regrouping…' : status}</p>
      <div class="row">
        <button onclick={undo} disabled={!undoable || busy}>undo</button>
        <button onclick={startOver} disabled={!undoable || busy}>start over</button>
        <a class="button secondary" href={`#/review/${sessionId}`}>Review all rides</a>
      </div>
      <div class="row">
        <button onclick={exportAll} disabled={busy || exportJob?.status === 'running' || exportJob?.status === 'queued'}
          title="A folder of full-quality clips per rider (ignored riders left out), plus a list of every ride">
          Export all riders
        </button>
      </div>
      {#if exportJob}
        <p class="small">
          {#if exportJob.status === 'failed'}
            <span class="error">Export failed: {exportJob.error}</span>
          {:else if exportJob.status === 'done'}
            Folders: {Object.entries(exportJob.result.folders ?? {}).map(([n, k]) => `${n} (${k})`).join(', ')}
            → <code>{exportJob.result.folder}</code>; list: <code>{exportJob.result.manifest}</code>
          {:else}
            <progress max="1" value={exportJob.progress}></progress> {exportJob.message || exportJob.status}
          {/if}
        </p>
      {/if}
      <details class="help small" open>
        <summary>How it works</summary>
        <p>
          Each card is one person, as far as the tool can tell from clothes, board and build. Click
          a still to play that ride; <em>all rides</em> opens every ride of the card, where
          <em>move to…</em> sends a single ride to the right person.
        </p>
        <p>
          Name the riders you care about — just yourself is fine. <em>same as</em> merges two cards
          of one person; <em>mixed</em> splits a card of two people; <em>ignore</em> hides staff.
          <em>play &amp; export</em> opens that rider's rides in Review (play all, one video).
        </p>
      </details>
    </section>

    <section class="cards">
      {#if info.join_suggestions.length}
        <div class="card wide joins">
          <strong>Possibly one ride split in two</strong>
          <span class="muted small">the rider left the frame and came back; play both, then join</span>
          {#each info.join_suggestions as s (s.first + s.second)}
            <div class="row">
              <button class="still" onclick={() => play(s.first)}><img alt="" src={still(s.first)} /></button>
              <button class="still" onclick={() => play(s.second)}><img alt="" src={still(s.second)} /></button>
              <span class="small time">{byId.get(s.first) ? clock(byId.get(s.first)!.start_s) : ''} · gap {s.gap_s.toFixed(1)} s</span>
              <button onclick={() => joinPair(s.first, s.second)} disabled={busy}>join</button>
            </div>
          {/each}
        </div>
      {/if}
      {#each active as g (g.rider_id)}
        <div class="card" class:wide={open[g.rider_id]}>
          <div class="head">
            <strong>{g.label}</strong>
            <span class="muted small">{g.ride_ids.length} ride{g.ride_ids.length === 1 ? '' : 's'}</span>
            <button class="link" onclick={() => (open[g.rider_id] = !open[g.rider_id])}>
              {open[g.rider_id] ? 'close' : `all rides (${g.ride_ids.length})`}
            </button>
          </div>
          {#if !open[g.rider_id]}
            <div class="stills">
              {#each g.stills.slice(0, 5) as s (s.ride_id)}
                <button class="still" class:playing={playingRide === s.ride_id} onclick={() => play(s.ride_id)}
                  title={`Play ride at ${byId.get(s.ride_id) ? clock(byId.get(s.ride_id)!.start_s) : ''}`}>
                  <img alt="" src={still(s.ride_id)} />
                </button>
              {/each}
            </div>
          {:else}
            <div class="all">
              {#each ridesOf(g) as r (r.ride_id)}
                <div class="ride" class:playing={playingRide === r.ride_id}>
                  <button class="still" onclick={() => play(r.ride_id)} title="Play this ride">
                    <img loading="lazy" alt="" src={still(r.ride_id)} />
                  </button>
                  <span class="small time">{clock(r.start_s)}
                    {#if r.flags.joined}<span class="tag" title="Two parts joined: the rider left the frame and came back">joined</span>{/if}
                  </span>
                  {#if r.flags.joined}
                    <button class="small" onclick={() => unjoin(r.ride_id)} disabled={busy}>unjoin</button>
                  {/if}
                  <select disabled={busy} onchange={(e) => move(r.ride_id, e.currentTarget)}>
                    <option value="">move to…</option>
                    {#each active.filter((o) => o.rider_id !== g.rider_id) as o (o.rider_id)}
                      <option value={o.rider_id}>{o.label}</option>
                    {/each}
                    <option value="__new">a new rider…</option>
                  </select>
                </div>
              {/each}
            </div>
          {/if}
          <div class="row">
            <input class="text" placeholder={g.name ? `rename ${g.name}` : 'who is this? (name)'}
              bind:value={nameDraft[g.rider_id]} onkeydown={(e) => e.key === 'Enter' && name(g)} disabled={busy} />
            <button onclick={() => name(g)} disabled={busy}>name</button>
          </div>
          <div class="row small">
            <select disabled={busy} onchange={(e) => sameAs(g, e.currentTarget)}>
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
    grid-template-columns: 360px minmax(0, 1fr);
    gap: 16px;
    align-items: start;
  }
  .side {
    position: sticky;
    top: 8px;
  }
  .side video {
    max-height: 220px;
  }
  .status {
    min-height: 1.2em;
  }
  .cards {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(420px, 1fr));
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
  .card.wide {
    grid-column: 1 / -1;
  }
  .card.dim {
    opacity: 0.6;
  }
  .head {
    display: flex;
    gap: 8px;
    align-items: baseline;
  }
  .head .link {
    margin-left: auto;
  }
  .stills {
    display: flex;
    gap: 4px;
    margin: 6px 0;
    overflow-x: auto;
  }
  .still {
    padding: 0;
    height: 144px;
    min-width: 72px;
    background: #000;
    border: 2px solid transparent;
    flex: none;
  }
  .still img {
    height: 140px;
    display: block;
  }
  .stills .still.playing,
  .ride.playing .still {
    border-color: var(--accent);
  }
  .all {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin: 6px 0;
  }
  .ride {
    display: flex;
    flex-direction: column;
    gap: 2px;
    width: 120px;
  }
  .ride .still {
    height: 124px;
    width: 120px;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .ride .still img {
    max-height: 120px;
    max-width: 116px;
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
    padding: 3px;
    font: inherit;
    font-size: 12px;
  }
</style>
