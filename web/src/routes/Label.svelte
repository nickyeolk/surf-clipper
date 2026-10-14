<script lang="ts">
  // Label mode: validate the tool's proposed rides against the video, add missed ones.
  // Label work is ground truth: it never changes detected rides or edits.json.
  import { api, clock, type Activity, type LabelItem, type LabelWork, type SourceInfo } from '../lib/api'
  import Timeline from '../lib/Timeline.svelte'

  let { sessionId }: { sessionId: string } = $props()

  let work = $state<LabelWork | null>(null)
  let probe = $state<SourceInfo | null>(null)
  let activity = $state<Activity | null>(null)
  let error = $state<string | null>(null)
  let status = $state('')
  let video = $state<HTMLVideoElement>()
  let current = $state(0)
  let paused = $state(true)
  let rate = $state(1)
  let selectedId = $state<string | null>(null)
  let pendingStart = $state<number | null>(null)
  let onlyPending = $state(false)
  let stopAt: number | null = null

  const RATES = [0.25, 0.5, 1, 2, 4, 8]
  const ZOOM_S = 60

  $effect(() => {
    Promise.all([api.labels(sessionId), api.session(sessionId), api.activity(sessionId)])
      .then(([w, s, a]) => {
        work = w
        probe = s.probe
        activity = a
        selectedId = w.items.find((i) => i.verdict === '?')?.id ?? w.items[0]?.id ?? null
      })
      .catch((e) => (error = e.message))
  })

  const duration = $derived(probe?.duration_s ?? 1)
  const frame = $derived(1 / (probe?.avg_fps ?? 30))
  const items = $derived(work ? [...work.items].sort((a, b) => a.start_s - b.start_s) : [])
  const shown = $derived(onlyPending ? items.filter((i) => i.verdict === '?') : items)
  const selected = $derived(items.find((i) => i.id === selectedId) ?? null)
  const remaining = $derived(items.filter((i) => i.verdict === '?').length)
  // Rides lying entirely inside a longer kept ride count as part of it (same rule as finalize).
  const inside = $derived.by(() => {
    const kept = items.filter((i) => i.verdict !== 'no')
    const ids = new Set<string>()
    for (const a of kept)
      for (const b of kept)
        if (a !== b && b.end_s - b.start_s > a.end_s - a.start_s &&
            b.start_s - 0.5 <= a.start_s && a.end_s <= b.end_s + 0.5) ids.add(a.id)
    return ids
  })
  const zoomFrom = $derived(Math.max(0, Math.min(current - ZOOM_S / 2, duration - ZOOM_S)))

  // ---- saving -------------------------------------------------------------------------------
  let saveTimer: ReturnType<typeof setTimeout> | undefined
  function changed() {
    if (!work) return
    status = 'unsaved'
    clearTimeout(saveTimer)
    saveTimer = setTimeout(save, 700)
  }
  async function save() {
    if (!work) return
    status = 'saving…'
    try {
      work = await api.saveLabels(sessionId, $state.snapshot(work) as LabelWork)
      status = 'saved'
    } catch (e) {
      status = `save failed: ${(e as Error).message}`
    }
  }
  async function finish() {
    await save()
    try {
      const r = await api.finalize(sessionId)
      status = `labels written: ${r.rides} rides → ${r.path}`
      if (work) work.finalized = true
    } catch (e) {
      status = (e as Error).message
    }
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
    if (stopAt !== null && current >= stopAt) {
      video.pause()
      stopAt = null
    }
  }
  // Track how far the user has watched continuously (the miss scan).
  let lastT = 0
  $effect(() => {
    const t = current
    if (work && !paused && t >= work.scanned_to_s - 1 && t - lastT < 3) {
      if (t > work.scanned_to_s) {
        work.scanned_to_s = t
        changed()
      }
    }
    lastT = t
  })

  // ---- selection and verdicts -----------------------------------------------------------------
  function select(id: string, play = false) {
    selectedId = id
    const it = items.find((i) => i.id === id)
    if (it) {
      seek(it.start_s - 1)
      if (play) playRide()
    }
  }
  function move(delta: number) {
    const list = shown
    const i = list.findIndex((it) => it.id === selectedId)
    const next = list[Math.max(0, Math.min(list.length - 1, i + delta))]
    if (next) select(next.id)
  }
  function playRide() {
    if (!selected || !video) return
    seek(selected.start_s - 1)
    stopAt = selected.end_s + 1.5
    void video.play()
  }
  function moved(it: LabelItem): boolean {
    return (
      it.proposed_start_s !== null &&
      it.proposed_end_s !== null &&
      (Math.abs(it.start_s - it.proposed_start_s) > 1e-3 || Math.abs(it.end_s - it.proposed_end_s) > 1e-3)
    )
  }
  function verdict(v: LabelItem['verdict']) {
    if (!selected) return
    if (selected.detected_as === null && v !== 'no') v = 'add'
    else if (v === 'ok' && moved(selected)) v = 'fix' // times were changed: keep it "corrected"
    selected.verdict = v
    changed()
    if (v !== '?') move(1)
  }
  function setEdge(which: 'start' | 'end') {
    if (!selected) return
    if (which === 'start') selected.start_s = Math.min(current, selected.end_s - frame)
    else selected.end_s = Math.max(current, selected.start_s + frame)
    if (selected.detected_as !== null) selected.verdict = 'fix'
    changed()
  }
  function toggleAcid() {
    if (!selected) return
    selected.acid_drop = !selected.acid_drop
    changed()
  }
  function addRide() {
    if (!work) return
    if (pendingStart === null) {
      pendingStart = current
      return
    }
    const [s, e] = pendingStart < current ? [pendingStart, current] : [current, pendingStart]
    pendingStart = null
    const id = `u${Date.now().toString(36)}`
    work.items.push({
      id, start_s: s, end_s: e, verdict: 'add', acid_drop: false, detected_as: null,
      proposed_start_s: null, proposed_end_s: null, confidence: null, notes: '',
    })
    selectedId = id
    changed()
  }
  function removeAdded() {
    if (!work || !selected || selected.detected_as !== null) return
    work.items = work.items.filter((i) => i.id !== selected!.id)
    selectedId = null
    changed()
  }

  function onkeydown(e: KeyboardEvent) {
    if ((e.target as HTMLElement).tagName === 'INPUT') return
    const k = e.key
    if (k === ' ') toggle()
    else if (k === 'ArrowLeft') step(e.shiftKey ? -Math.round(1 / frame) : -1)
    else if (k === 'ArrowRight') step(e.shiftKey ? Math.round(1 / frame) : 1)
    else if (k === 'ArrowUp') move(-1)
    else if (k === 'ArrowDown') move(1)
    else if (k === '1') verdict('ok')
    else if (k === '2') verdict('no')
    else if (k === '0') verdict('?')
    else if (k === '[') setEdge('start')
    else if (k === ']') setEdge('end')
    else if (k === 'a') toggleAcid()
    else if (k === 'n') addRide()
    else if (k === 'p') playRide()
    else if (k === 'Escape') pendingStart = null
    else if (k === '+' || k === '=') setRate(RATES[Math.min(RATES.length - 1, RATES.indexOf(rate) + 1)])
    else if (k === '-') setRate(RATES[Math.max(0, RATES.indexOf(rate) - 1)])
    else return
    e.preventDefault()
  }
</script>

<svelte:window {onkeydown} />

{#if error}
  <p class="error">{error}</p>
{:else if !work || !probe}
  <p class="muted">Loading…</p>
{:else}
  <div class="label-view">
    <section class="player">
      <div class="titlebar">
        <h1>{work.source}</h1>
        <span class="muted">{status}</span>
      </div>
      <!-- svelte-ignore a11y_media_has_caption -->
      <video
        bind:this={video}
        bind:paused
        src={api.videoUrl(sessionId)}
        preload="auto"
        {ontimeupdate}
        onclick={toggle}
      ></video>
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
      <Timeline from={0} to={duration} {items} {activity} {current} scannedTo={work.scanned_to_s}
        {selectedId} {pendingStart} onseek={seek} onselect={(id) => select(id)} />
      <Timeline from={zoomFrom} to={zoomFrom + ZOOM_S} {items} {activity} {current}
        scannedTo={work.scanned_to_s} {selectedId} {pendingStart} onseek={seek}
        onselect={(id) => select(id)} />
      <p class="muted small">
        Top: whole session · bottom: ±30 s around the playhead. Green strip = someone looks like
        they're riding. Blue shading = watched for missed rides
        ({clock(work.scanned_to_s)} of {clock(duration)}).
      </p>
      <details class="small rule">
        <summary><strong>Labelling rule</strong> (start / end)</summary>
        <p>
          <strong>Start:</strong> the instant the rider leaves the side wall (bum or board off it;
          for acid drops the jump, not the run-up), or their first frame if the wall is out of
          shot.<br />
          <strong>End:</strong> the first frame they are clearly no longer riding the board: a
          hand, knee or body in the water, the board separating, the feet going behind the face
          into the whitewater, or exiting over a side wall. A landed air is part of the ride; a
          failed air ends when they hit the water.<br />
          <span class="muted">Within a second is fine: clips have padding, and the evaluation
          checks that nothing is cut off.</span>
        </p>
      </details>
      <details class="help">
        <summary>Keyboard shortcuts</summary>
        <p>
          <kbd>Space</kbd> play/pause · <kbd>←</kbd>/<kbd>→</kbd> one frame ·
          <kbd>Shift</kbd>+arrows one second · <kbd>+</kbd>/<kbd>−</kbd> speed ·
          <kbd>↑</kbd>/<kbd>↓</kbd> previous/next ride · <kbd>p</kbd> play ride ·
          <kbd>1</kbd> correct · <kbd>2</kbd> not a ride · <kbd>0</kbd> undecided ·
          <kbd>[</kbd>/<kbd>]</kbd> set start/end to now · <kbd>a</kbd> acid drop ·
          <kbd>n</kbd> add a missed ride (press at start, again at end) · <kbd>Esc</kbd> cancel add
        </p>
      </details>
    </section>

    <aside class="rides">
      <div class="progress">
        <strong>{items.length - remaining}</strong> of {items.length} decided
        <label><input type="checkbox" bind:checked={onlyPending} /> only undecided</label>
      </div>
      {#if selected}
        <div class="selected">
          <div class="row">
            <strong>{selected.id}</strong>
            <span class="muted">
              {selected.detected_as === null ? 'added by you' : selected.detected_as}
              {selected.confidence !== null ? `· conf ${selected.confidence.toFixed(2)}` : ''}
            </span>
          </div>
          <div class="row">
            <button onclick={() => setEdge('start')} title="Set start to playhead ([)">[ start</button>
            <span class="time">{clock(selected.start_s)} – {clock(selected.end_s)}</span>
            <button onclick={() => setEdge('end')} title="Set end to playhead (])">end ]</button>
            <button onclick={playRide} title="Play this ride (p)">▶ play ride</button>
          </div>
          <div class="row">
            <button class="ok" class:active={selected.verdict === 'ok'} onclick={() => verdict('ok')}>
              ✓ correct (1)</button>
            <button class="no" class:active={selected.verdict === 'no'} onclick={() => verdict('no')}>
              ✗ not a ride (2)</button>
            <label><input type="checkbox" checked={selected.acid_drop} onchange={toggleAcid} /> acid drop (a)</label>
            {#if selected.detected_as === null}
              <button onclick={removeAdded}>remove</button>
            {/if}
          </div>
          {#if selected.verdict === 'fix'}
            <p class="muted small">
              Times corrected (detected {clock(selected.proposed_start_s ?? 0)} –
              {clock(selected.proposed_end_s ?? 0)}).
            </p>
          {/if}
        </div>
      {/if}
      <div class="row">
        <button onclick={addRide} class:active={pendingStart !== null}>
          {pendingStart === null ? '+ add missed ride (n)' : `end ride here (started ${clock(pendingStart)})`}
        </button>
        <button class="primary" disabled={remaining > 0} onclick={finish}
          title={remaining > 0 ? 'Decide every ride first' : 'Write the labels file'}>
          Finish ({remaining} left)
        </button>
      </div>
      <ol class="list">
        {#each shown as it (it.id)}
          <li class:sel={it.id === selectedId}>
            <button class="item" onclick={() => select(it.id)} ondblclick={() => select(it.id, true)}>
              <span class="dot v-{it.verdict === '?' ? 'q' : it.verdict}"></span>
              <span class="time">{clock(it.start_s)}</span>
              <span class="muted">{(it.end_s - it.start_s).toFixed(1)}s</span>
              <span class="muted">{it.detected_as ?? 'added'}</span>
              {#if it.acid_drop}<span class="tag">acid</span>{/if}
              {#if inside.has(it.id)}<span class="tag" title="Inside a longer ride: counted as part of it">part of ride</span>{/if}
            </button>
          </li>
        {/each}
      </ol>
    </aside>
  </div>
{/if}
