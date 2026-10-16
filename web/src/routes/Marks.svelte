<script lang="ts">
  // Mark rides (004 evaluation): on each of your rides, mark when you turned (t), pumped (p) and
  // how the ride ended (f fall, e exit, u unclear). Marks are evaluation data only: they never
  // change rides or the analysis, and hold times, not names. Saved as you go.
  import { api, clock, type AnalysisMarks, type Ending, type MarkedRide } from '../lib/api'

  let { sessionId }: { sessionId: string } = $props()

  let marks = $state<AnalysisMarks | null>(null)
  let error = $state<string | null>(null)
  let status = $state('')
  let idx = $state(0)
  let video = $state<HTMLVideoElement>()
  let current = $state(0)
  let paused = $state(true)
  let rate = $state(0.5)
  let saveTimer: ReturnType<typeof setTimeout> | null = null

  $effect(() => {
    api.marks(sessionId).then((m) => {
      marks = m
      idx = Math.max(0, m.rides.findIndex((r) => r.ending === null))
    }).catch((e) => (error = e.message))
  })

  const ride = $derived<MarkedRide | null>(marks?.rides[idx] ?? null)
  const done = $derived(marks ? marks.rides.filter((r) => r.ending !== null).length : 0)
  const PAD = 1.5

  function go(i: number, play = true) {
    if (!marks || i < 0 || i >= marks.rides.length) return
    idx = i
    const r = marks.rides[i]
    if (video) {
      video.currentTime = Math.max(0, r.start_s - PAD)
      video.playbackRate = rate
      if (play) void video.play()
    }
  }
  function onloaded() {
    if (ride && video) {
      video.currentTime = Math.max(0, ride.start_s - PAD)
      video.playbackRate = rate
    }
  }
  function ontimeupdate() {
    if (!video) return
    current = video.currentTime
    if (ride && current > ride.end_s + PAD && !video.paused) video.pause()
  }
  function save() {
    if (!marks) return
    marks.final = false
    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = setTimeout(() => {
      if (marks) api.saveMarks(sessionId, $state.snapshot(marks) as AnalysisMarks)
        .then(() => (status = 'saved')).catch((e) => (status = `not saved: ${e.message}`))
    }, 400)
  }
  function mark(kind: 'turns' | 'pumps') {
    if (!ride) return
    const t = Math.round(current * 100) / 100
    if (t < ride.start_s - 1 || t > ride.end_s + 1) {
      status = 'the playhead is outside this ride'
      return
    }
    ride[kind] = [...ride[kind], t].sort((a, b) => a - b)
    status = `${kind === 'turns' ? 'turn' : 'pump'} at ${clock(t)}`
    save()
  }
  function remove(kind: 'turns' | 'pumps', t: number) {
    if (!ride) return
    ride[kind] = ride[kind].filter((x) => x !== t)
    save()
  }
  function undoLast() {
    if (!ride) return
    const last = [...ride.turns.map((t) => ['turns', t] as const), ...ride.pumps.map((t) => ['pumps', t] as const)]
      .sort((a, b) => b[1] - a[1])[0]
    if (last) remove(last[0], last[1])
  }
  function end(e: Ending) {
    if (!ride) return
    ride.ending = e
    status = `ending: ${e}`
    save()
    if (marks && idx + 1 < marks.rides.length) setTimeout(() => go(idx + 1), 300)
  }
  async function finalize() {
    if (saveTimer) clearTimeout(saveTimer)
    try {
      await api.saveMarks(sessionId, $state.snapshot(marks) as AnalysisMarks)
      const r = await api.finalizeMarks(sessionId)
      if (marks) marks.final = true
      status = `finalized: ${r.rides} rides, ${r.turns} turns, ${r.falls} falls`
    } catch (e) {
      status = (e as Error).message
    }
  }
  function setRate(r: number) {
    rate = r
    if (video) video.playbackRate = r
  }
  function step(frames: number) {
    if (!video) return
    video.pause()
    video.currentTime = Math.max(0, video.currentTime + frames / 30)
  }
  function onkeydown(e: KeyboardEvent) {
    if ((e.target as HTMLElement).tagName === 'INPUT' || e.ctrlKey || e.metaKey || e.altKey) return
    const k = e.key
    if (k === ' ') video && (video.paused ? void video.play() : video.pause())
    else if (k === 't') mark('turns')
    else if (k === 'p') mark('pumps')
    else if (k === 'f') end('fall')
    else if (k === 'e') end('exit')
    else if (k === 'u') end('unclear')
    else if (k === 'Backspace') undoLast()
    else if (k === 'n' || k === 'ArrowDown') go(idx + 1)
    else if (k === 'b' || k === 'ArrowUp') go(idx - 1)
    else if (k === 'r') go(idx)
    else if (k === 'ArrowLeft') step(e.shiftKey ? -30 : -3)
    else if (k === 'ArrowRight') step(e.shiftKey ? 30 : 3)
    else return
    e.preventDefault()
  }
  const pos = (t: number) => (ride ? ((t - (ride.start_s - PAD)) / (ride.end_s - ride.start_s + 2 * PAD)) * 100 : 0)
</script>

<svelte:window {onkeydown} />

{#if error}
  <p class="error">{error}</p>
{:else if !marks}
  <p class="muted">Loading…</p>
{:else if marks.rides.length === 0}
  <p>No rides to mark: name yourself in <a href={`#/riders/${sessionId}`}>Riders</a> first.</p>
{:else}
  <div class="marks">
    <section>
      <div class="titlebar">
        <h1>Mark rides <span class="muted small">{marks.source} · {done}/{marks.rides.length} done{marks.final ? ' · finalized' : ''}</span></h1>
        <span class="small muted">{status}</span>
      </div>
      <!-- svelte-ignore a11y_media_has_caption -->
      <video bind:this={video} bind:paused src={api.videoUrl(sessionId)} preload="auto"
        onloadedmetadata={onloaded} {ontimeupdate} onclick={() => video && (video.paused ? void video.play() : video.pause())}></video>
      {#if ride}
        <div class="bar" aria-hidden="true">
          <span class="ride" style:left="{pos(ride.start_s)}%" style:width="{pos(ride.end_s) - pos(ride.start_s)}%"></span>
          {#each ride.turns as t}<span class="tick turn" style:left="{pos(t)}%" title="turn {clock(t)}"></span>{/each}
          {#each ride.pumps as t}<span class="tick pump" style:left="{pos(t)}%" title="pump {clock(t)}"></span>{/each}
          <span class="head" style:left="{Math.min(100, Math.max(0, pos(current)))}%"></span>
        </div>
      {/if}
      <div class="row controls">
        <button onclick={() => go(idx)} title="Replay this ride (r)">↺ replay</button>
        <button class="primary" onclick={() => video && (video.paused ? void video.play() : video.pause())}>{paused ? 'Play' : 'Pause'}</button>
        <span class="time">{clock(current)}</span>
        {#each [0.25, 0.5, 1] as r}
          <button class:active={rate === r} onclick={() => setRate(r)}>{r}×</button>
        {/each}
        <span class="sep"></span>
        <button onclick={() => mark('turns')} title="Turn at the playhead (t)">▼ turn</button>
        <button onclick={() => mark('pumps')} title="Pump at the playhead (p)">· pump</button>
        <button onclick={undoLast} title="Remove the last mark (Backspace)">⌫</button>
        <span class="sep"></span>
        <button class:active={ride?.ending === 'fall'} onclick={() => end('fall')} title="(f)">fall</button>
        <button class:active={ride?.ending === 'exit'} onclick={() => end('exit')} title="(e)">exit</button>
        <button class:active={ride?.ending === 'unclear'} onclick={() => end('unclear')} title="(u)">unclear</button>
      </div>
      <details class="help small" open>
        <summary>How to mark</summary>
        <p>
          Each ride plays at half speed from just before it starts. Press <kbd>t</kbd> at the
          moment of each <strong>turn</strong> (where you change direction, at the bottom of the
          compression), <kbd>p</kbd> for a <strong>pump</strong> (compress and extend without
          changing direction). At the end press <kbd>f</kbd> for a <strong>fall</strong>,
          <kbd>e</kbd> for an <strong>exit</strong> (stepped off, kicked out, rode off the wave)
          or <kbd>u</kbd> if you can't tell; it moves to the next ride. <kbd>Backspace</kbd>
          removes the last mark, <kbd>←</kbd>/<kbd>→</kbd> step, <kbd>↑</kbd>/<kbd>↓</kbd> change ride.
          Marking pumps is optional; turns and endings matter most.
        </p>
      </details>
    </section>
    <aside class="panel">
      <div class="row">
        <button class="primary" onclick={finalize} disabled={done < marks.rides.length}
          title="All rides need an ending">Finalize</button>
        <a href={`#/review/${sessionId}`} class="small">Review</a>
      </div>
      <ol class="list">
        {#each marks.rides as r, i}
          <li class:sel={i === idx}>
            <button class="item" onclick={() => go(i)}>
              <span class="time">{clock(r.start_s)}</span>
              <span class="muted small">{(r.end_s - r.start_s).toFixed(0)} s · {r.turns.length} turns{r.pumps.length ? ` · ${r.pumps.length} pumps` : ''}</span>
              <span class="tag" class:ok={r.ending === 'exit'} class:bad={r.ending === 'fall'}>{r.ending ?? '–'}</span>
            </button>
            {#if i === idx}
              <div class="small marklist">
                {#each [...r.turns.map((t) => ['turns', t] as const), ...r.pumps.map((t) => ['pumps', t] as const)].sort((a, b) => a[1] - b[1]) as [k, t]}
                  <span>{k === 'turns' ? '▼' : '·'} {clock(t)} <button class="link" onclick={() => remove(k, t)}>×</button></span>
                {/each}
              </div>
            {/if}
          </li>
        {/each}
      </ol>
    </aside>
  </div>
{/if}

<style>
  .marks {
    display: grid;
    grid-template-columns: minmax(0, 1fr) 300px;
    gap: 16px;
    align-items: start;
  }
  .titlebar {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
  }
  video {
    width: 100%;
    max-height: calc(100vh - 300px);
    background: #000;
    border-radius: 6px;
  }
  .bar {
    position: relative;
    height: 18px;
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 4px;
    margin: 6px 0;
  }
  .ride {
    position: absolute;
    top: 3px;
    bottom: 3px;
    background: var(--accent);
    opacity: 0.35;
    border-radius: 3px;
  }
  .tick {
    position: absolute;
    top: 0;
    bottom: 0;
    width: 3px;
    margin-left: -1px;
  }
  .tick.turn {
    background: var(--q);
  }
  .tick.pump {
    background: var(--add);
  }
  .head {
    position: absolute;
    top: -3px;
    bottom: -3px;
    width: 2px;
    background: var(--text);
  }
  .controls {
    flex-wrap: wrap;
    gap: 6px;
  }
  .controls .active {
    border-color: var(--accent);
    color: var(--accent);
  }
  .sep {
    width: 10px;
  }
  .time {
    font-variant-numeric: tabular-nums;
  }
  .panel {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 10px;
    max-height: calc(100vh - 90px);
    overflow-y: auto;
  }
  .list {
    list-style: none;
    padding: 0;
    margin: 8px 0 0;
  }
  .list li.sel .item {
    border-color: var(--accent);
  }
  .item {
    display: flex;
    gap: 8px;
    align-items: baseline;
    width: 100%;
    text-align: left;
    background: var(--bg);
    margin: 2px 0;
  }
  .tag.bad {
    color: #ff7b72;
  }
  .marklist {
    display: flex;
    flex-wrap: wrap;
    gap: 4px 10px;
    padding: 2px 6px 6px;
  }
  .link {
    background: none;
    border: none;
    color: var(--accent);
    padding: 0 2px;
    cursor: pointer;
  }
  kbd {
    border: 1px solid var(--border);
    border-radius: 3px;
    padding: 0 4px;
    font-size: 0.9em;
  }
</style>
