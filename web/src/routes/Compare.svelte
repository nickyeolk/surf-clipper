<script lang="ts">
  // Side by side (004 US1). Two steps:
  //  1. Line up: each side has its own controls; find the same moment in both (e.g. the bottom
  //     of a turn, the take-off of a trick).
  //  2. Link: both play together from there, at the same speed, frame steps move both.
  // Under the videos, four body measures of both on one time axis, aligned at the lined-up
  // moments. Each side is picked as session → ride.
  import { api, clock, type Job, type RideAnalysis, type TrickTag } from '../lib/api'
  import CropPlayer from '../lib/CropPlayer.svelte'
  import { untrack } from 'svelte'

  let { query }: { query: string } = $props()

  interface Source {
    sid: string
    name: string
    reference: boolean
    rides: RideAnalysis[] | null // null: not analysed yet
    job: Job | null
  }
  interface Side {
    sid: string
    ride: string
    sync: number | null // where this side lines up (set when linking)
    mirror: boolean
  }

  const params = new URLSearchParams(untrack(() => query)) // the URL only seeds the picks
  function parse(key: string | null, sync: string | null): Side {
    const [sid, ride] = (key ?? '').split(':')
    return { sid: sid ?? '', ride: ride ?? '', sync: sync ? Number(sync) : null, mirror: false }
  }
  let a = $state<Side>(parse(params.get('a'), params.get('sa')))
  let b = $state<Side>(parse(params.get('b'), params.get('sb')))
  let linked = $state(a.sync !== null && b.sync !== null)
  let sources = $state<Source[]>([])
  let tricks = $state<TrickTag[]>([])
  let loading = $state(true)
  let pa = $state<CropPlayer>()
  let pb = $state<CropPlayer>()
  let ta = $state(0)
  let tb = $state(0)
  let playing = $state(false)
  let rate = $state(0.5)
  let skeleton = $state(true)
  let status = $state('')

  async function analysisOf(sid: string): Promise<RideAnalysis[] | null> {
    try {
      return (await api.analysis(sid)).rides
    } catch {
      return null
    }
  }
  $effect(() => {
    void (async () => {
      const [sessions, refs] = await Promise.all([api.sessions(), api.references().catch(() => [])])
      const out: Source[] = []
      for (const s of sessions) out.push({ sid: s.session_id, name: s.name, reference: false, rides: await analysisOf(s.session_id), job: null })
      for (const r of refs) {
        if (r.status === 'ready') out.push({ sid: r.session_id, name: r.video, reference: true, rides: await analysisOf(r.session_id), job: null })
      }
      sources = out
      tricks = await api.tricks().catch(() => [])
      loading = false
    })()
  })

  async function analyse(src: Source) {
    try {
      src.job = await api.runAnalysis(src.sid)
      while (src.job.status === 'queued' || src.job.status === 'running') {
        await new Promise((r) => setTimeout(r, 1500))
        src.job = await api.job(src.job.job_id)
      }
      src.rides = await analysisOf(src.sid)
      if (!src.rides?.length) status = `nothing analysed in ${src.name}: name yourself (or the surfer) in Riders first`
    } catch (e) {
      status = (e as Error).message
    }
  }

  const sourceOf = (s: Side) => sources.find((x) => x.sid === s.sid) ?? null
  const rideOf = (s: Side) => sourceOf(s)?.rides?.find((r) => r.ride_id === s.ride) ?? null
  const rideA = $derived(rideOf(a))
  const rideB = $derived(rideOf(b))

  function rideLabel(src: Source, r: RideAnalysis): string {
    if (src.reference) return `${r.rider} · ${(r.span[1] - r.span[0]).toFixed(0)} s`
    const mine = (src.rides ?? []).filter((x) => x.rider === r.rider).sort((p, q) => p.span[0] - q.span[0])
    const k = mine.findIndex((x) => x.ride_id === r.ride_id) + 1
    const score = r.score ? ` · score ${r.score.value.toFixed(0)}` : ''
    return `${r.rider} · ride ${k} of ${mine.length} · ${clock(r.span[0]).replace(/\.\d+$/, '')} · ${(r.span[1] - r.span[0]).toFixed(0)} s${score}${r.starred ? ' ★' : ''}`
  }
  function sourceLabel(src: Source): string {
    if (src.rides === null) return `${src.name} (not analysed)`
    if (!src.rides.length) return `${src.name} (no named riders)`
    return `${src.reference ? 'reference: ' : ''}${src.name} (${src.rides.length} rides)`
  }
  function pickSource(side: Side, sid: string) {
    side.sid = sid
    side.ride = ''
    side.sync = null
    unlink()
  }
  function pickRide(side: Side, ride: string) {
    side.ride = ride
    side.sync = null
    unlink()
  }

  $effect(() => {
    const p = new URLSearchParams()
    if (a.sid && a.ride) p.set('a', `${a.sid}:${a.ride}`)
    if (b.sid && b.ride) p.set('b', `${b.sid}:${b.ride}`)
    if (linked && a.sync !== null && b.sync !== null) {
      p.set('sa', a.sync.toFixed(3))
      p.set('sb', b.sync.toFixed(3))
    }
    history.replaceState(null, '', `#/compare?${p}`)
  })

  // ---- step 1: line up (each side on its own) ---------------------------------------------
  function own(side: 'a' | 'b') {
    return side === 'a' ? pa : pb
  }
  function ownToggle(side: 'a' | 'b') {
    const p = own(side)
    if (!p) return
    if (p.paused()) {
      p.setRate(rate)
      p.play()
    } else p.pause()
  }
  function ownStep(side: 'a' | 'b', seconds: number) {
    const p = own(side)
    if (!p) return
    p.pause()
    p.seek(p.time() + seconds)
  }
  function snap(side: 'a' | 'b') {
    const r = side === 'a' ? rideA : rideB
    const t = side === 'a' ? ta : tb
    if (!r) return
    const marks = [...r.turns.map((e) => e.t), ...r.tricks.map((e) => e.t)]
    if (!marks.length) {
      status = 'no turns or tags in this ride'
      return
    }
    const next = marks.filter((m) => m > t + 0.05)
    const best = next.length ? Math.min(...next) : marks[0]
    own(side)?.pause()
    own(side)?.seek(best)
    status = `${side.toUpperCase()}: next turn/tag at ${clock(best)}`
  }
  function useTrick(side: Side, which: 'a' | 'b', tag: TrickTag) {
    side.sid = tag.session_id
    side.ride = tag.ride_id
    side.sync = null
    unlink()
    setTimeout(() => own(which)?.seek(tag.t), 800)
  }

  // ---- step 2: link -------------------------------------------------------------------------
  function link() {
    if (!pa || !pb) return
    pa.pause()
    pb.pause()
    playing = false
    a.sync = pa.time()
    b.sync = pb.time()
    linked = true
    status = `linked: A ${clock(a.sync)} = B ${clock(b.sync)}`
  }
  function unlink() {
    linked = false
    playing = false
    pa?.pause()
    pb?.pause()
  }
  function toSync() {
    if (!linked || a.sync === null || b.sync === null) return
    pa?.pause()
    pb?.pause()
    playing = false
    pa?.seek(a.sync - 1)
    follow()
  }
  function toggle() {
    if (!pa || !pb) return
    if (playing) {
      pa.pause()
      pb.pause()
      playing = false
    } else {
      pa.setRate(rate)
      pb.setRate(rate)
      follow()
      pa.play()
      pb.play()
      playing = true
    }
  }
  function setRate(r: number) {
    rate = r
    pa?.setRate(r)
    pb?.setRate(r)
  }
  function step(frames: number) {
    jump(frames / 30)
  }
  /** Put B at the moment matching A (when linked). */
  function follow() {
    if (linked && pa && pb && a.sync !== null && b.sync !== null) pb.seek(b.sync + (pa.time() - a.sync))
  }
  function jump(seconds: number) {
    if (!pa) return
    pa.pause()
    pb?.pause()
    playing = false
    pa.seek(pa.time() + seconds)
    follow()
  }
  /** Seconds from the linked moment covered by both rides together (for the shared scrubber). */
  const linkedRange = $derived.by((): [number, number] => {
    if (!rideA || !rideB || a.sync === null || b.sync === null) return [0, 0]
    return [
      Math.min(rideA.span[0] - a.sync, rideB.span[0] - b.sync) - 1,
      Math.max(rideA.span[1] - a.sync, rideB.span[1] - b.sync) + 1,
    ]
  })
  function scrubLinked(rel: number) {
    if (!pa || a.sync === null) return
    pa.pause()
    pb?.pause()
    playing = false
    pa.seek(a.sync + rel)
    follow()
  }
  // when linked, B follows A
  $effect(() => {
    let raf = 0
    const loop = () => {
      if (linked && pa && pb && a.sync !== null && b.sync !== null) {
        const target = b.sync + (pa.time() - a.sync)
        const drift = pb.time() - target
        if (!playing || pa.paused()) {
          if (Math.abs(drift) > 0.5 / 30) pb.seek(target)
          if (playing && pa.paused()) {
            playing = false
            pb.pause()
          }
        } else if (Math.abs(drift) > 0.25) {
          pb.seek(target)
        } else {
          pb.setRate(rate * Math.max(0.97, Math.min(1.03, 1 - drift * 0.6)))
        }
      }
      raf = requestAnimationFrame(loop)
    }
    raf = requestAnimationFrame(loop)
    return () => cancelAnimationFrame(raf)
  })

  function onkeydown(e: KeyboardEvent) {
    const tag = (e.target as HTMLElement).tagName
    if (tag === 'INPUT' || tag === 'SELECT' || e.ctrlKey || e.metaKey || e.altKey || !linked) return
    if (e.key === ' ') toggle()
    else if (e.key === 'ArrowLeft' && e.shiftKey) jump(-1)
    else if (e.key === 'ArrowRight' && e.shiftKey) jump(1)
    else if (e.key === ',' || e.key === 'ArrowLeft') step(-1)
    else if (e.key === '.' || e.key === 'ArrowRight') step(1)
    else return
    e.preventDefault()
  }

  // ---- measures -----------------------------------------------------------------------------
  const MEASURES = [
    { key: 'compression', label: 'how low (1 = that surfer\'s usual; lower = more crouched)', lo: 0.4, hi: 1.3 },
    { key: 'lean', label: 'torso lean ° (as each camera sees it)', lo: -60, hi: 60 },
    { key: 'arms', label: 'arm spread (torso lengths)', lo: 0, hi: 4 },
    { key: 'stance', label: 'stance width (torso lengths)', lo: 0, hi: 3 },
  ] as const
  const W = 600
  const H = 64
  // aligned at the linked moments; while lining up, at the current positions (rounded so the
  // charts don't redraw every frame)
  const syncA = $derived(linked && a.sync !== null ? a.sync : Math.round(ta * 10) / 10)
  const syncB = $derived(linked && b.sync !== null ? b.sync : Math.round(tb * 10) / 10)
  const range = $derived.by((): [number, number] => {
    const spans: [number, number][] = []
    if (rideA) spans.push([rideA.span[0] - syncA, rideA.span[1] - syncA])
    if (rideB) spans.push([rideB.span[0] - syncB, rideB.span[1] - syncB])
    if (!spans.length) return [-5, 5]
    return [Math.min(...spans.map((s) => s[0])), Math.max(...spans.map((s) => s[1]))]
  })
  function path(r: RideAnalysis | null, sync: number, key: string, lo: number, hi: number): string {
    if (!r) return ''
    const series = (r as unknown as Record<string, (number | null)[]>)[key] ?? []
    const [r0, r1] = range
    let d = ''
    let pen = false
    series.forEach((v, i) => {
      if (v === null) {
        pen = false
        return
      }
      const x = ((r.t0 + i / r.fps - sync - r0) / (r1 - r0)) * W
      const y = H - ((Math.max(lo, Math.min(hi, v)) - lo) / (hi - lo)) * H
      d += `${pen ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`
      pen = true
    })
    return d
  }
  const headA = $derived(((ta - syncA - range[0]) / (range[1] - range[0])) * W)
  const zeroX = $derived(((0 - range[0]) / (range[1] - range[0])) * W)
</script>

<svelte:window {onkeydown} />

<div class="compare">
  <div class="titlebar">
    <h1>Compare <span class="muted small">{status}</span></h1>
    <label class="small"><input type="checkbox" bind:checked={skeleton} /> skeletons</label>
  </div>
  {#if loading}
    <p class="muted">Loading sessions…</p>
  {:else}
    <ol class="steps small">
      <li class:done={rideA && rideB}><strong>Pick</strong> a ride on each side (session, then ride).</li>
      <li class:done={linked}><strong>Line up</strong>: with each side's own controls, find the same moment in both, e.g. the bottom of a turn.</li>
      <li class:done={linked}><strong>Link</strong>: both then play together from that moment.</li>
    </ol>
    <div class="sides">
      {#each [['a', a, rideA, '#58a6ff'], ['b', b, rideB, '#f0883e']] as const as [name, side, ride, colour]}
        {@const src = sourceOf(side)}
        <section>
          <div class="pick">
            <strong style:color={colour}>{name.toUpperCase()}</strong>
            <select value={side.sid} onchange={(e) => pickSource(side, e.currentTarget.value)}>
              <option value="">session…</option>
              {#each sources as s (s.sid)}
                <option value={s.sid}>{sourceLabel(s)}</option>
              {/each}
            </select>
            {#if src?.rides?.length}
              <select value={side.ride} onchange={(e) => pickRide(side, e.currentTarget.value)}>
                <option value="">ride…</option>
                {#each [...src.rides].sort((p, q) => p.span[0] - q.span[0]) as r (r.ride_id)}
                  <option value={r.ride_id}>{rideLabel(src, r)}</option>
                {/each}
              </select>
            {/if}
          </div>
          {#if src && src.rides === null}
            <p class="small">
              This session isn't analysed yet.
              {#if src.job && ['queued', 'running'].includes(src.job.status)}
                <progress max="1" value={src.job.progress}></progress> {src.job.message}
              {:else}
                <button onclick={() => analyse(src)}>Analyse it</button>
                (only riders you named in Riders are analysed)
              {/if}
            </p>
          {:else if src && src.rides?.length === 0}
            <p class="small">No named riders here: name yourself (or the surfer) in <a href={`#/riders/${src.sid}`}>Riders</a>, then analyse again.</p>
          {/if}
          {#if ride}
            {#key side.sid + side.ride}
              {#if name === 'a'}
                <CropPlayer bind:this={pa} sessionId={side.sid} rideId={side.ride} mirror={side.mirror}
                  {skeleton} {colour} start={(side.sync ?? ride.span[0]) - 1} ontime={(t) => (ta = t)} />
              {:else}
                <CropPlayer bind:this={pb} sessionId={side.sid} rideId={side.ride} mirror={side.mirror}
                  {skeleton} {colour} start={(side.sync ?? ride.span[0]) - 1} ontime={(t) => (tb = t)} />
              {/if}
            {/key}
            {#if !linked}
              <div class="row small own">
                <button onclick={() => ownStep(name, -1)} title="Back 1 s">−1s</button>
                <button onclick={() => ownStep(name, -1 / 30)} title="Back one frame">◀︎</button>
                <button onclick={() => ownToggle(name)}>play / pause</button>
                <button onclick={() => ownStep(name, 1 / 30)} title="Forward one frame">▶︎</button>
                <button onclick={() => ownStep(name, 1)} title="Forward 1 s">+1s</button>
                <button onclick={() => snap(name)} title="Jump to the next detected turn or trick tag">next turn/tag</button>
              </div>
              <input class="scrub" type="range" min={ride.span[0] - 1} max={ride.span[1] + 1} step="0.033"
                value={name === 'a' ? ta : tb} oninput={(e) => own(name)?.seek(Number(e.currentTarget.value))} />
            {/if}
            <div class="row small">
              <span class="time">{clock(name === 'a' ? ta : tb)}</span>
              <span class="muted">({((name === 'a' ? ta : tb) - ride.span[0]).toFixed(1)} s into the ride)</span>
              <label><input type="checkbox" bind:checked={side.mirror} /> mirror</label>
              {#if tricks.length}
                <select class="tiny" onchange={(e) => { const t = tricks[Number(e.currentTarget.value)]; if (t) useTrick(side, name, t); e.currentTarget.value = '' }}>
                  <option value="">jump to a tagged trick…</option>
                  {#each tricks as t, i}
                    <option value={i}>{t.name} · {t.rider} · {t.video} {clock(t.t).replace(/\.\d+$/, '')}</option>
                  {/each}
                </select>
              {/if}
            </div>
            <p class="small muted">{ride.score?.explanation ?? ''}</p>
          {:else}
            <div class="empty">{name === 'a' ? 'Pick your ride' : 'Pick a ride to compare with (a named surfer, or a reference clip)'}</div>
          {/if}
        </section>
      {/each}
    </div>

    {#if rideA && rideB}
      <div class="row transport">
        {#if !linked}
          <button class="primary" onclick={link} title="The two moments now on screen are the same moment: play them together from here">
            Link here — these two moments match
          </button>
          <span class="small muted">A {clock(ta)} ↔ B {clock(tb)}</span>
        {:else}
          <button onclick={toSync} title="Both to 1 s before the linked moment">⇤ linked moment</button>
          <button onclick={() => jump(-1)} title="Both back 1 s (Shift+←)">−1s</button>
          <button onclick={() => step(-1)} title="One frame back (, or ←)">◀︎ frame</button>
          <button class="primary" onclick={toggle} title="Play/pause both (Space)">{playing ? 'Pause' : 'Play both'}</button>
          <button onclick={() => step(1)} title="One frame on (. or →)">frame ▶︎</button>
          <button onclick={() => jump(1)} title="Both forward 1 s (Shift+→)">+1s</button>
          {#each [0.25, 0.5, 1] as r}
            <button class:active={rate === r} onclick={() => setRate(r)}>{r}×</button>
          {/each}
          <span class="small muted">{(ta - syncA >= 0 ? '+' : '')}{(ta - syncA).toFixed(2)} s from the linked moment</span>
          <button class="secondary" onclick={unlink} title="Adjust each side again">unlink to adjust</button>
          <input class="scrub" type="range" min={linkedRange[0]} max={linkedRange[1]} step="0.033"
            value={ta - (a.sync ?? 0)} oninput={(e) => scrubLinked(Number(e.currentTarget.value))}
            title="Scrub both together (0 = the linked moment)" />
        {/if}
      </div>
    {/if}

    {#if rideA || rideB}
      <div class="charts">
        {#each MEASURES as m}
          <div class="chart">
            <span class="small muted">{m.label}</span>
            <svg viewBox="0 0 {W} {H}" preserveAspectRatio="none">
              <line x1={zeroX} x2={zeroX} y1="0" y2={H} class="zero" />
              <path d={path(rideA, syncA, m.key, m.lo, m.hi)} class="a" />
              <path d={path(rideB, syncB, m.key, m.lo, m.hi)} class="b" />
              <line x1={headA} x2={headA} y1="0" y2={H} class="head" />
            </svg>
          </div>
        {/each}
        <p class="small muted">
          <span style:color="#58a6ff">A</span> and <span style:color="#f0883e">B</span>, seconds
          from the {linked ? 'linked moment' : 'current positions'} (dashed line). Lean is as each
          camera sees it; the other measures are body proportions, so different cameras and
          distances compare.
        </p>
      </div>
    {/if}
  {/if}
</div>

<style>
  .titlebar {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
  }
  .steps {
    margin: 0 0 8px;
    padding-left: 1.4em;
    color: var(--muted);
  }
  .steps li.done {
    color: var(--ok);
  }
  .sides {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
    gap: 12px;
  }
  .pick {
    display: flex;
    gap: 6px;
    align-items: center;
    margin-bottom: 6px;
  }
  .pick select {
    flex: 1;
    min-width: 0;
    max-width: 100%;
  }
  select {
    background: var(--bg);
    color: var(--text);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 3px;
  }
  select.tiny {
    max-width: 14em;
  }
  .empty {
    height: min(56vh, 520px);
    display: grid;
    place-items: center;
    border: 1px dashed var(--border);
    border-radius: 6px;
    color: var(--muted);
    text-align: center;
    padding: 12px;
  }
  .row {
    display: flex;
    gap: 6px;
    align-items: center;
    flex-wrap: wrap;
    margin: 6px 0;
  }
  .scrub {
    width: 100%;
  }
  .transport {
    padding: 8px;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: var(--panel);
  }
  .transport .active {
    border-color: var(--accent);
    color: var(--accent);
  }
  .time {
    font-variant-numeric: tabular-nums;
  }
  .charts {
    max-width: 1100px;
    margin-top: 8px;
  }
  .chart svg {
    width: 100%;
    height: 64px;
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 4px;
    display: block;
    margin-bottom: 6px;
  }
  path {
    fill: none;
    stroke-width: 2;
    vector-effect: non-scaling-stroke;
  }
  path.a {
    stroke: #58a6ff;
  }
  path.b {
    stroke: #f0883e;
  }
  .zero {
    stroke: var(--muted);
    stroke-dasharray: 4 4;
    vector-effect: non-scaling-stroke;
  }
  .head {
    stroke: var(--text);
    vector-effect: non-scaling-stroke;
  }
  @media (max-width: 900px) {
    .sides {
      grid-template-columns: 1fr;
    }
  }
</style>
