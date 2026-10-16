<script lang="ts">
  // Review mode: check the detected rides, fix them (trim, split, merge, delete, add, keep a
  // short attempt), then export final-quality clips. Every change is an edit in edits.json, so
  // re-running detection later keeps it (FR-022). Undo appends an "undo" edit.
  import {
    api, clock, type Activity, type Job, type Ride, type Rides, type ShortAttempt, type SourceInfo,
    type UserEdit, type EditOp,
  } from '../lib/api'
  import Timeline, { type Bar } from '../lib/Timeline.svelte'

  let { sessionId, rider }: { sessionId: string; rider?: string } = $props()
  // Rider filter (002): only this rider's rides in the list, play-all and export.
  // svelte-ignore state_referenced_locally (initial value; the route re-creates the page)
  let riderFilter = $state(rider ?? '')
  let riderLabels = $state<string[]>([])

  type Item =
    | { kind: 'ride'; id: string; start_s: number; end_s: number; ride: Ride }
    | { kind: 'short'; id: string; start_s: number; end_s: number; short: ShortAttempt }

  let rides = $state<Rides | null>(null)
  let probe = $state<SourceInfo | null>(null)
  let activity = $state<Activity | null>(null)
  let edits = $state<UserEdit[]>([])
  let error = $state<string | null>(null)
  let status = $state('')
  let video = $state<HTMLVideoElement>()
  let current = $state(0)
  let paused = $state(true)
  let rate = $state(1)
  let selectedId = $state<string | null>(null)
  let pendingStart = $state<number | null>(null)
  let byConfidence = $state(true)
  let showShort = $state(false)
  let job = $state<Job | null>(null)
  let busy = $state(false)
  let zoneOrigin = $state<string | null>(null)
  let stopAt: number | null = null
  // Reel: play the rides back to back (only the rides left after deleting others').
  let reel = $state(false)
  let reelIdx = $state(0)
  let minLength = $state(10)
  let rerunJob = $state<Job | null>(null)

  const RATES = [0.25, 0.5, 1, 2, 4]
  const ZOOM_S = 60
  const COLOUR = { ride: '#58a6ff', edited: '#bc8cff', exported: '#3fb950', short: '#6e7681' }

  $effect(() => {
    Promise.all([
      api.rides(sessionId), api.session(sessionId), api.activity(sessionId).catch(() => null),
      api.edits(sessionId),
      api.riders(sessionId).catch(() => null),
    ])
      .then(([r, s, a, e, rd]) => {
        riderLabels = rd ? rd.riders.filter((g) => !g.ignored).map((g) => g.label) : []
        rides = r
        probe = s.probe
        zoneOrigin = s.zone_origin
        activity = a
        edits = e.edits
        minLength = r.settings.min_length_s
        selectedId = sortedRides()[0]?.ride_id ?? null
      })
      .catch((e) => (error = e.message))
  })

  const duration = $derived(probe?.duration_s ?? 1)
  const frame = $derived(1 / (probe?.avg_fps ?? 30))
  const rideList = $derived(
    rides
      ? [...rides.rides]
          .filter((r) => !riderFilter || r.rider === riderFilter)
          .sort((a, b) => a.start_s - b.start_s)
      : [],
  )
  // Short attempts the user already kept as a ride are not shown again.
  const shorts = $derived(
    rides
      ? rides.short_attempts.filter(
          (s) => !rideList.some((r) => r.start_s <= s.start_s + 0.5 && r.end_s >= s.end_s - 0.5),
        )
      : [],
  )
  const items = $derived.by<Item[]>(() => {
    const list: Item[] = (byConfidence
      ? [...rideList].sort((a, b) => a.confidence - b.confidence)
      : rideList
    ).map((r) => ({ kind: 'ride', id: r.ride_id, start_s: r.start_s, end_s: r.end_s, ride: r }))
    if (showShort)
      list.push(
        ...shorts.map((s): Item => ({ kind: 'short', id: s.ride_id, start_s: s.start_s, end_s: s.end_s, short: s })),
      )
    return list
  })
  const selected = $derived.by<Item | null>(() => {
    const r = rideList.find((x) => x.ride_id === selectedId)
    if (r) return { kind: 'ride', id: r.ride_id, start_s: r.start_s, end_s: r.end_s, ride: r }
    const s = shorts.find((x) => x.ride_id === selectedId)
    if (s) return { kind: 'short', id: s.ride_id, start_s: s.start_s, end_s: s.end_s, short: s }
    return null
  })
  const selRide = $derived(selected?.kind === 'ride' ? selected.ride : null)
  const selShort = $derived(selected?.kind === 'short' ? selected.short : null)
  const exported = $derived(rideList.filter((r) => r.export).length)
  const toExport = $derived(rideList.length - exported)
  const undoable = $derived.by(() => {
    const undone = new Set<number>()
    for (const e of [...edits].reverse())
      if (e.op === 'undo' && !undone.has(e.edit_id) && typeof e.payload.edit_id === 'number')
        undone.add(e.payload.edit_id)
    return [...edits].reverse().find((e) => e.op !== 'undo' && e.op !== 'confirm_zone' && !undone.has(e.edit_id)) ?? null
  })
  function colourOf(r: Ride): string {
    if (r.export) return COLOUR.exported
    if (r.flags.user_edited || r.flags.user_added) return COLOUR.edited
    return COLOUR.ride
  }
  const bars = $derived<Bar[]>([
    ...rideList.map((r) => ({ id: r.ride_id, start_s: r.start_s, end_s: r.end_s, colour: colourOf(r) })),
    ...(showShort
      ? shorts.map((s) => ({ id: s.ride_id, start_s: s.start_s, end_s: s.end_s, colour: COLOUR.short, dim: true }))
      : []),
  ])
  const zoomFrom = $derived(Math.max(0, Math.min(current - ZOOM_S / 2, duration - ZOOM_S)))
  const reelOffsets = $derived.by(() => {
    const out: number[] = []
    let acc = 0
    for (const r of rideList) {
      out.push(acc)
      acc += r.clip_end_s - r.clip_start_s
    }
    out.push(acc)
    return out
  })
  const reelTotal = $derived(reelOffsets[reelOffsets.length - 1] ?? 0)
  const reelPos = $derived.by(() => {
    const r = rideList[reelIdx]
    if (!r) return 0
    return reelOffsets[reelIdx] + Math.max(0, Math.min(r.clip_end_s - r.clip_start_s, current - r.clip_start_s))
  })

  function sortedRides(): Ride[] {
    if (!rides) return []
    return [...rides.rides].sort((a, b) => (byConfidence ? a.confidence - b.confidence : a.start_s - b.start_s))
  }

  // ---- player -------------------------------------------------------------------------------
  function seek(t: number) {
    if (!video) return
    video.currentTime = Math.max(0, Math.min(duration, t))
  }
  function step(frames: number) {
    video?.pause()
    seek(current + frames * frame)
  }
  function toggle() {
    if (!video) return
    if (video.paused) void video.play()
    else video.pause()
  }
  function setRate(r: number) {
    rate = r
    if (video) video.playbackRate = r
  }
  function ontimeupdate() {
    if (!video) return
    current = video.currentTime
    if (reel) {
      const r = rideList[reelIdx]
      if (r && current >= r.clip_end_s - 0.05) {
        if (reelIdx + 1 < rideList.length) goReel(reelIdx + 1, true)
        else video.pause()
      }
      return
    }
    if (stopAt !== null && current >= stopAt) {
      video.pause()
      stopAt = null
    }
  }

  // ---- reel -----------------------------------------------------------------------------------
  function goReel(i: number, play: boolean) {
    const r = rideList[i]
    if (!r || !video) return
    reel = true
    reelIdx = i
    selectedId = r.ride_id
    stopAt = null
    seek(r.clip_start_s)
    if (play) void video.play()
  }
  function startReel() {
    if (reel) {
      reel = false
      video?.pause()
      return
    }
    goReel(0, true) // from the first ride; clicking a ride in the list jumps there
  }
  function reelSeek(e: MouseEvent) {
    const box = (e.currentTarget as HTMLElement).getBoundingClientRect()
    const pos = ((e.clientX - box.left) / box.width) * reelTotal
    let i = 0
    while (i + 1 < rideList.length && reelOffsets[i + 1] <= pos) i++
    const r = rideList[i]
    reel = true
    reelIdx = i
    selectedId = r.ride_id
    seek(r.clip_start_s + pos - reelOffsets[i])
  }
  function leaveReel(t: number) {
    reel = false
    seek(t)
  }
  function playSelected() {
    if (!selected || !video) return
    seek(selRide ? selRide.clip_start_s : selected.start_s - 1)
    stopAt = selRide ? selRide.clip_end_s : selected.end_s + 1
    void video.play()
  }

  // ---- selection ----------------------------------------------------------------------------
  function select(id: string, play = false) {
    const ri = rideList.findIndex((x) => x.ride_id === id)
    if (reel && ri >= 0) {
      goReel(ri, !paused || play)
      return
    }
    selectedId = id
    const r = rideList.find((x) => x.ride_id === id)
    const s = shorts.find((x) => x.ride_id === id)
    if (r) seek(r.clip_start_s)
    else if (s) seek(s.start_s - 1)
    if (play) playSelected()
  }
  function move(delta: number) {
    const i = items.findIndex((it) => it.id === selectedId)
    const next = items[Math.max(0, Math.min(items.length - 1, i + delta))]
    if (next) select(next.id)
  }

  // ---- edits --------------------------------------------------------------------------------
  async function edit(
    op: EditOp, target: { ride_id?: string; ride_ids?: string[] }, payload: Record<string, number> = {},
    nextId?: (r: Rides) => string | null,
  ) {
    if (busy) return
    busy = true
    try {
      const before = selected
      const res = await api.edit(sessionId, op, target, payload)
      rides = riderLabels.length ? await api.rides(sessionId) : res.rides // keep rider fields
      edits = [...edits, res.edit]
      if (nextId) selectedId = nextId(res.rides)
      if (before && !res.rides.rides.some((r) => r.ride_id === selectedId)) {
        // e.g. after an undo: select whatever ride now covers the old selection
        const t = (before.start_s + before.end_s) / 2
        selectedId = res.rides.rides.find((r) => r.start_s <= t && t <= r.end_s)?.ride_id ?? selectedId
      }
      status = describe(res.edit)
    } catch (e) {
      status = (e as Error).message
    } finally {
      busy = false
    }
  }
  function describe(e: UserEdit): string {
    const t = e.target.ride_id ?? e.target.ride_ids?.join(' + ') ?? ''
    return e.op === 'undo' ? `undid edit ${e.payload.edit_id}` : `${e.op} ${t}`.trim()
  }
  function setEdge(which: 'start' | 'end') {
    if (!selRide) return
    const payload: Record<string, number> = { [which === 'start' ? 'start_s' : 'end_s']: current }
    void edit('trim', { ride_id: selRide.ride_id }, payload, () => selRide?.ride_id ?? null)
  }
  function split() {
    if (!selRide) return
    if (!(current > selRide.start_s + 0.5 && current < selRide.end_s - 0.5)) {
      status = 'move the playhead inside the ride to split it'
      return
    }
    const id = selRide.ride_id
    void edit('split', { ride_id: id }, { at_s: current }, () => `${id}b`)
  }
  function mergeNext() {
    if (!selRide) return
    const next = rideList.find((r) => r.start_s > selRide!.start_s)
    if (!next) return
    const id = selRide.ride_id
    void edit('merge', { ride_ids: [id, next.ride_id] }, {}, () => id)
  }
  function remove() {
    if (!selRide) return
    const i = items.findIndex((it) => it.id === selRide!.ride_id)
    const after = items[i + 1]?.id ?? items[i - 1]?.id ?? null
    void edit('delete', { ride_id: selRide.ride_id }, {}, () => after)
  }
  function keepShort() {
    if (!selShort) return
    const s = selShort
    void edit('add', {}, { start_s: s.start_s, end_s: s.end_s }, (r) =>
      r.rides.find((x) => x.flags.user_added && Math.abs(x.start_s - s.start_s) < 1e-3)?.ride_id ?? null)
  }
  function addRide() {
    if (pendingStart === null) {
      pendingStart = current
      return
    }
    const [s, e] = pendingStart < current ? [pendingStart, current] : [current, pendingStart]
    pendingStart = null
    if (e - s < 0.5) return
    void edit('add', {}, { start_s: s, end_s: e }, (r) =>
      r.rides.find((x) => x.flags.user_added && Math.abs(x.start_s - s) < 1e-3)?.ride_id ?? null)
  }
  function undo() {
    if (undoable) void edit('undo', {}, { edit_id: undoable.edit_id })
  }

  // ---- export -------------------------------------------------------------------------------
  function reelHref(): string {
    const url = api.reelUrl(sessionId, riderFilter || undefined)
    return `${url}${url.includes('?') ? '&' : '?'}t=${Date.now()}`
  }
  async function exportClips(ids?: string[], asReel = false) {
    const who = riderFilter || undefined
    try {
      job = await api.exportClips(sessionId, ids, asReel, ids ? undefined : who)
      while (job && (job.status === 'queued' || job.status === 'running')) {
        await new Promise((r) => setTimeout(r, 1000))
        job = await api.job(job.job_id)
      }
      rides = await api.rides(sessionId)
    } catch (e) {
      status = (e as Error).message
    }
  }

  async function rerun() {
    if (!(minLength > 0)) return
    try {
      rerunJob = await api.rerun(sessionId, minLength)
      while (rerunJob && (rerunJob.status === 'queued' || rerunJob.status === 'running')) {
        await new Promise((r) => setTimeout(r, 1000))
        rerunJob = await api.job(rerunJob.job_id)
      }
      rides = await api.rides(sessionId)
      edits = (await api.edits(sessionId)).edits
    } catch (e) {
      status = (e as Error).message
    }
  }

  function onkeydown(e: KeyboardEvent) {
    if ((e.target as HTMLElement).tagName === 'INPUT') return
    const k = e.key
    if ((e.ctrlKey || e.metaKey) && k === 'z') undo()
    else if (e.ctrlKey || e.metaKey || e.altKey) return
    else if (k === ' ') toggle()
    else if (k === 'ArrowLeft') step(e.shiftKey ? -Math.round(1 / frame) : -1)
    else if (k === 'ArrowRight') step(e.shiftKey ? Math.round(1 / frame) : 1)
    else if (k === 'ArrowUp') move(-1)
    else if (k === 'ArrowDown') move(1)
    else if (k === 'p') playSelected()
    else if (k === '[') setEdge('start')
    else if (k === ']') setEdge('end')
    else if (k === 's') split()
    else if (k === 'm') mergeNext()
    else if (k === 'Delete' || k === 'x') remove()
    else if (k === 'k') keepShort()
    else if (k === 'n') addRide()
    else if (k === 'u') undo()
    else if (k === 'r') startReel()
    else if (k === ',' && reel) goReel(Math.max(0, reelIdx - 1), !paused)
    else if (k === '.' && reel) goReel(Math.min(rideList.length - 1, reelIdx + 1), !paused)
    else if (k === 'Escape') pendingStart = null
    else if (k === '+' || k === '=') setRate(RATES[Math.min(RATES.length - 1, RATES.indexOf(rate) + 1)])
    else if (k === '-') setRate(RATES[Math.max(0, RATES.indexOf(rate) - 1)])
    else return
    e.preventDefault()
  }
  const thumbAt = (s: number, e: number) => s + Math.min(3, (e - s) / 3)
</script>

<svelte:window {onkeydown} />

{#if error}
  <p class="error">{error}</p>
{:else if !rides || !probe}
  <p class="muted">Loading…</p>
{:else}
  <div class="label-view">
    <section class="player">
      <div class="titlebar">
        <h1>{probe.path.split(/[\\/]/).pop()} <span class="muted small">review</span></h1>
        <span class="muted">
          {#if zoneOrigin === 'proposed'}
            <a href={`#/zone/${sessionId}`} title="The wave zone was set automatically; checking it improves the clips">check the wave zone</a> ·
          {/if}
          {busy ? 'saving…' : status}
        </span>
      </div>
      <!-- svelte-ignore a11y_media_has_caption -->
      <video bind:this={video} bind:paused src={api.videoUrl(sessionId)} preload="auto" {ontimeupdate}
        onclick={toggle}></video>
      <div class="controls">
        <button onclick={() => step(-Math.round(1 / frame))} title="Back 1 s (Shift+←)">−1s</button>
        <button onclick={() => step(-1)} title="Back one frame (←)">◀︎ frame</button>
        <button class="primary" onclick={toggle} title="Play/pause (Space)">{paused ? 'Play' : 'Pause'}</button>
        <button onclick={() => step(1)} title="Forward one frame (→)">frame ▶︎</button>
        <button onclick={() => step(Math.round(1 / frame))} title="Forward 1 s (Shift+→)">+1s</button>
        <span class="time">{clock(current)} / {clock(duration)}</span>
        <span class="rates">
          {#each RATES as r}
            <button class:active={rate === r} onclick={() => setRate(r)}>{r}×</button>
          {/each}
        </span>
      </div>
      <div class="reel">
        <button class:active={reel} onclick={startReel} disabled={rideList.length === 0}
          title="Play the rides back to back (r)">{reel ? '■ stop playing all' : '▶ play all rides'}</button>
        {#if reel}
          <button onclick={() => goReel(Math.max(0, reelIdx - 1), !paused)} title="Previous ride (,)">⏮</button>
          <button onclick={() => goReel(Math.min(rideList.length - 1, reelIdx + 1), !paused)} title="Next ride (.)">⏭</button>
          <span class="time small">ride {reelIdx + 1}/{rideList.length} · {clock(reelPos)} / {clock(reelTotal)}</span>
        {/if}
      </div>
      {#if reel}
        <!-- svelte-ignore a11y_click_events_have_key_events -->
        <div class="reelbar" onclick={reelSeek} role="slider" tabindex="-1" aria-label="All rides"
          aria-valuemin={0} aria-valuemax={reelTotal} aria-valuenow={reelPos}>
          {#each rideList as r, i (r.ride_id)}
            <span class="seg" class:cur={i === reelIdx}
              style:width="{((r.clip_end_s - r.clip_start_s) / reelTotal) * 100}%"></span>
          {/each}
          <span class="head" style:left="{(reelPos / Math.max(reelTotal, 1e-6)) * 100}%"></span>
        </div>
      {/if}
      <Timeline from={0} to={duration} {bars} {activity} {current} {selectedId} {pendingStart}
        onseek={leaveReel} onselect={(id) => select(id)} />
      <Timeline from={zoomFrom} to={zoomFrom + ZOOM_S} {bars} {activity} {current} {selectedId}
        {pendingStart} onseek={leaveReel} onselect={(id) => select(id)} />
      <p class="muted small">
        Top: whole session · bottom: ±30 s around the playhead. Bars: <span style:color={COLOUR.ride}>ride</span>
        · <span style:color={COLOUR.edited}>changed by you</span> · <span style:color={COLOUR.exported}>exported</span>
        {#if showShort}· <span style:color={COLOUR.short}>short attempt</span>{/if}.
        The preview is a 720p SDR copy; exported clips are full quality{rides.source.hdr_format !== 'none' ? ', HDR kept' : ''}.
      </p>
      <details class="help">
        <summary>Keyboard shortcuts</summary>
        <p>
          <kbd>Space</kbd> play/pause · <kbd>←</kbd>/<kbd>→</kbd> one frame · <kbd>Shift</kbd>+arrows
          one second · <kbd>+</kbd>/<kbd>−</kbd> speed (0.25× slow motion) · <kbd>↑</kbd>/<kbd>↓</kbd>
          previous/next · <kbd>p</kbd> play clip · <kbd>[</kbd>/<kbd>]</kbd> start/end to playhead ·
          <kbd>s</kbd> split at playhead · <kbd>m</kbd> merge with next · <kbd>x</kbd>/<kbd>Del</kbd>
          delete · <kbd>k</kbd> keep short attempt · <kbd>n</kbd> add a missed ride (start, then end) ·
          <kbd>u</kbd>/<kbd>Ctrl</kbd>+<kbd>Z</kbd> undo · <kbd>r</kbd> play all rides back to back,
          then <kbd>,</kbd>/<kbd>.</kbd> previous/next ride
        </p>
      </details>
    </section>

    <aside class="rides">
      {#if riderLabels.length}
        <div class="row">
          <label>Rider
            <select class="num wide" bind:value={riderFilter} onchange={() => (reel = false)}>
              <option value="">all riders</option>
              {#each riderLabels as l}<option value={l}>{l}</option>{/each}
            </select>
          </label>
          <a class="small" href={`#/riders/${sessionId}`}>name riders</a>
        </div>
      {/if}
      <div class="progress">
        <span><strong>{rideList.length}</strong> rides · {exported} exported</span>
      </div>
      <div class="row">
        <button class="primary" disabled={job?.status === 'running' || job?.status === 'queued' || rideList.length === 0}
          onclick={() => exportClips()} title="One file per ride; only new or changed rides are encoded">
          Export {toExport > 0 ? `${toExport} clip${toExport === 1 ? '' : 's'}` : 'clips (up to date)'}
        </button>
        <button disabled={job?.status === 'running' || job?.status === 'queued' || rideList.length === 0}
          onclick={() => exportClips(undefined, true)}
          title={riderFilter
            ? "This rider's rides as one video, each with the rider's name, ride number and time for its first seconds"
            : 'All rides in this list joined into one video'}>
          {riderFilter ? 'Export compilation' : 'Export as one video'}
        </button>
      </div>
      {#if job}
        <div class="job small">
          {#if job.status === 'failed'}
            <span class="error">Export failed: {job.error}</span>
          {:else if job.status === 'done' && job.result.reel}
            {riderFilter ? 'Compilation' : 'One video'} of {rideList.length} rides →
            <a href={reelHref()} target="_blank" rel="noreferrer">open ↗</a>
            <code>{job.result.reel}</code>
          {:else if job.status === 'done'}
            Exported {job.result.exported?.length ?? 0}, {job.result.up_to_date?.length ?? 0} already up to
            date → <code>{job.result.folder}</code>
          {:else}
            <progress max="1" value={job.progress}></progress> {job.message || job.status}
          {/if}
        </div>
      {/if}
      <div class="row small">
        <label title="Rides shorter than this become short attempts">min ride
          <input class="num" type="number" min="1" step="1" bind:value={minLength} /> s</label>
        <button onclick={rerun}
          disabled={rerunJob?.status === 'running' || rerunJob?.status === 'queued' || minLength === rides.settings.min_length_s}
          title="Find rides again with this setting; your edits are kept">re-run</button>
        {#if rerunJob && (rerunJob.status === 'running' || rerunJob.status === 'queued')}
          <span class="muted">finding rides…</span>
        {:else if rerunJob?.status === 'failed'}
          <span class="error">{rerunJob.error}</span>
        {/if}
      </div>
      <div class="row small">
        <label><input type="checkbox" bind:checked={byConfidence} /> least confident first</label>
        <label><input type="checkbox" bind:checked={showShort} /> short attempts ({shorts.length})</label>
      </div>

      {#if selRide}
        <div class="selected">
          <div class="row">
            <strong>{selRide.ride_id}</strong>
            <span class="muted">{(selRide.end_s - selRide.start_s).toFixed(1)} s · conf {selRide.confidence.toFixed(2)}</span>
            {#if selRide.flags.lesson}<span class="tag">lesson</span>{/if}
            {#if selRide.flags.truncated}<span class="tag" title="Rider touched the frame edge">edge</span>{/if}
            {#if selRide.flags.user_added}<span class="tag">added</span>{:else if selRide.flags.user_edited}<span class="tag">edited</span>{/if}
          </div>
          <div class="row">
            <button onclick={() => setEdge('start')} title="Start at playhead ([)">[ start</button>
            <span class="time">{clock(selRide.start_s)} – {clock(selRide.end_s)}</span>
            <button onclick={() => setEdge('end')} title="End at playhead (])">end ]</button>
            <button onclick={playSelected} title="Play the padded clip (p)">▶ play</button>
          </div>
          <div class="row">
            <button onclick={split} title="Split at playhead (s)">split</button>
            <button onclick={mergeNext} title="Merge with the next ride (m)">merge next</button>
            <button class="no" onclick={remove} title="Delete (x)">delete</button>
            <button onclick={() => exportClips([selRide!.ride_id])} title="Export only this clip">export</button>
            {#if selRide.export}
              <a href={api.clipUrl(sessionId, selRide.ride_id)} target="_blank" rel="noreferrer">open clip ↗</a>
            {/if}
          </div>
        </div>
      {:else if selShort}
        <div class="selected">
          <div class="row">
            <strong>{selShort.ride_id}</strong>
            <span class="muted">short attempt · {(selShort.end_s - selShort.start_s).toFixed(1)} s</span>
          </div>
          <div class="row">
            <button onclick={playSelected}>▶ play</button>
            <button class="primary" onclick={keepShort} title="Keep as a ride (k)">keep as ride</button>
          </div>
        </div>
      {/if}
      <div class="row">
        <button onclick={addRide} class:active={pendingStart !== null}>
          {pendingStart === null ? '+ add missed ride (n)' : `end ride here (started ${clock(pendingStart)})`}
        </button>
        <button onclick={undo} disabled={!undoable} title={undoable ? `Undo: ${describe(undoable)}` : 'Nothing to undo'}>
          undo
        </button>
      </div>
      {#if rideList.length === 0}
        <p class="small">No rides found. If people were riding, check the
          <a href={`#/zone/${sessionId}`}>wave zone</a>, or lower the minimum ride length.</p>
      {/if}
      <ol class="list">
        {#each items as it (it.id)}
          <li class:sel={it.id === selectedId}>
            <button class="item" onclick={() => select(it.id)} ondblclick={() => select(it.id, true)}>
              <img class="thumb" loading="lazy" alt="" src={api.thumbUrl(sessionId, thumbAt(it.start_s, it.end_s))} />
              <span class="meta">
                <span class="time">{clock(it.start_s)}</span>
                <span class="muted">{(it.end_s - it.start_s).toFixed(1)} s{it.kind === 'ride' ? ` · ${it.ride.confidence.toFixed(2)}` : ''}</span>
                <span>
                  {#if it.kind === 'short'}<span class="tag muted-tag">short</span>{/if}
                  {#if it.kind === 'ride'}
                    {#if it.ride.export}<span class="tag ok">exported</span>{/if}
                    {#if it.ride.flags.user_added}<span class="tag">added</span>{:else if it.ride.flags.user_edited}<span class="tag">edited</span>{/if}
                    {#if it.ride.flags.lesson}<span class="tag">lesson</span>{/if}
                  {/if}
                </span>
              </span>
            </button>
          </li>
        {/each}
      </ol>
    </aside>
  </div>
{/if}

<style>
  .thumb {
    width: 96px;
    height: 54px;
    object-fit: cover;
    border-radius: 3px;
    background: #000;
    flex: none;
  }
  .meta {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  .job {
    margin: 4px 0;
  }
  .job code {
    word-break: break-all;
  }
  .reel {
    display: flex;
    gap: 6px;
    align-items: center;
    margin: 4px 0;
  }
  .reelbar {
    position: relative;
    display: flex;
    height: 18px;
    gap: 2px;
    margin: 4px 0 8px;
    cursor: pointer;
  }
  .reelbar .seg {
    background: #1f6feb;
    opacity: 0.55;
    border-radius: 2px;
  }
  .reelbar .seg.cur {
    opacity: 1;
  }
  .reelbar .head {
    position: absolute;
    top: -2px;
    bottom: -2px;
    width: 2px;
    background: #ff7b72;
  }
  .num.wide {
    width: auto;
  }
  .num {
    width: 4em;
    background: var(--bg);
    color: var(--text);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 2px 4px;
  }
  .muted-tag {
    background: #2d2f33;
    color: var(--muted);
  }
</style>
