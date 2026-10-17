<script lang="ts">
  // Side by side (004 US1): two analysed rides, each cropped to its surfer with the skeleton,
  // a sync point per side, one transport for both, and four body measures of both on one time
  // axis aligned at the sync points. A drives the clock; B follows (re-seeked when paused,
  // nudged in speed when playing).
  import { api, clock, type RideAnalysis, type TrickTag } from '../lib/api'
  import CropPlayer from '../lib/CropPlayer.svelte'
  import { untrack } from 'svelte'

  let { query }: { query: string } = $props()

  interface Option {
    sid: string
    video: string
    ride: RideAnalysis
  }
  interface Side {
    key: string // "<sid>:<ride>"
    sync: number | null
    mirror: boolean
  }

  const params = new URLSearchParams(untrack(() => query)) // the URL only seeds the picks
  let options = $state<Option[]>([])
  let tricks = $state<TrickTag[]>([])
  let loading = $state(true)
  let a = $state<Side>({ key: params.get('a') ?? '', sync: num(params.get('sa')), mirror: false })
  let b = $state<Side>({ key: params.get('b') ?? '', sync: num(params.get('sb')), mirror: false })
  let pa = $state<CropPlayer>()
  let pb = $state<CropPlayer>()
  let ta = $state(0)
  let tb = $state(0)
  let playing = $state(false)
  let rate = $state(0.5)
  let skeleton = $state(true)
  let status = $state('')

  function num(v: string | null): number | null {
    return v === null || v === '' ? null : Number(v)
  }

  $effect(() => {
    void (async () => {
      const sessions = await api.sessions()
      const out: Option[] = []
      for (const s of sessions) {
        try {
          const an = await api.analysis(s.session_id)
          for (const r of an.rides) out.push({ sid: s.session_id, video: s.name, ride: r })
        } catch {
          /* not analysed */
        }
      }
      for (const r of await api.references().catch(() => [])) {
        if (r.status !== 'ready') continue
        try {
          const an = await api.analysis(r.session_id)
          for (const ride of an.rides) out.push({ sid: r.session_id, video: `reference: ${r.video}`, ride })
        } catch {
          /* not analysed */
        }
      }
      options = out
      tricks = await api.tricks().catch(() => [])
      loading = false
    })()
  })

  const optA = $derived(options.find((o) => `${o.sid}:${o.ride.ride_id}` === a.key) ?? null)
  const optB = $derived(options.find((o) => `${o.sid}:${o.ride.ride_id}` === b.key) ?? null)
  const label = (o: Option) =>
    `${o.ride.rider} · ${o.video} · ${clock(o.ride.span[0]).replace(/\.\d+$/, '')} · ${o.ride.span[1] - o.ride.span[0] > 0 ? (o.ride.span[1] - o.ride.span[0]).toFixed(0) : 0} s${o.ride.starred ? ' ★' : ''}`

  // default sync: the ride's start, so both play from the beginning until the user sets one
  const syncA = $derived(a.sync ?? optA?.ride.span[0] ?? 0)
  const syncB = $derived(b.sync ?? optB?.ride.span[0] ?? 0)

  $effect(() => {
    const p = new URLSearchParams()
    if (a.key) p.set('a', a.key)
    if (b.key) p.set('b', b.key)
    if (a.sync !== null) p.set('sa', a.sync.toFixed(3))
    if (b.sync !== null) p.set('sb', b.sync.toFixed(3))
    history.replaceState(null, '', `#/compare?${p}`)
  })

  // ---- transport ------------------------------------------------------------------------------
  function toSync() {
    pa?.pause()
    pb?.pause()
    playing = false
    pa?.seek(syncA - 1)
    pb?.seek(syncB - 1)
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
    if (!pa) return
    pa.pause()
    pb?.pause()
    playing = false
    pa.seek(pa.time() + frames / 30)
  }
  // B follows A
  $effect(() => {
    let raf = 0
    const loop = () => {
      if (pa && pb && optA && optB) {
        const target = syncB + (pa.time() - syncA)
        const drift = pb.time() - target
        const half = 0.5 / 30
        if (!playing || pa.paused()) {
          if (Math.abs(drift) > half) pb.seek(target)
          if (playing && pa.paused()) playing = false
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

  function setSync(side: 'a' | 'b') {
    if (side === 'a') a.sync = ta
    else b.sync = tb
    status = `sync ${side.toUpperCase()} at ${clock(side === 'a' ? ta : tb)}`
  }
  function snap(side: 'a' | 'b') {
    const o = side === 'a' ? optA : optB
    const t = side === 'a' ? ta : tb
    if (!o) return
    const marks = [...o.ride.turns.map((e) => e.t), ...o.ride.tricks.map((e) => e.t)]
    if (!marks.length) {
      status = 'no turns or tags in this ride'
      return
    }
    const best = marks.reduce((x, y) => (Math.abs(y - t) < Math.abs(x - t) ? y : x))
    if (side === 'a') a.sync = best
    else b.sync = best
    if (side === 'a') pa?.seek(best)
    else pb?.seek(best)
    status = `sync ${side.toUpperCase()} snapped to ${clock(best)}`
  }
  function useTrick(side: 'a' | 'b', tag: TrickTag) {
    const s = side === 'a' ? a : b
    s.key = `${tag.session_id}:${tag.ride_id}`
    s.sync = tag.t
  }

  function onkeydown(e: KeyboardEvent) {
    const tag = (e.target as HTMLElement).tagName
    if (tag === 'INPUT' || tag === 'SELECT' || e.ctrlKey || e.metaKey || e.altKey) return
    if (e.key === ' ') toggle()
    else if (e.key === ',' || e.key === 'ArrowLeft') step(-1)
    else if (e.key === '.' || e.key === 'ArrowRight') step(1)
    else if (e.key === 's') toSync()
    else return
    e.preventDefault()
  }

  // ---- measures -------------------------------------------------------------------------------
  const MEASURES = [
    { key: 'compression', label: 'how low (1 = your usual)', lo: 0.4, hi: 1.3 },
    { key: 'lean', label: 'torso lean ° (as the camera sees it)', lo: -60, hi: 60 },
    { key: 'arms', label: 'arm spread (torso lengths)', lo: 0, hi: 4 },
    { key: 'stance', label: 'stance width (torso lengths)', lo: 0, hi: 3 },
  ] as const
  const W = 600
  const H = 64
  const range = $derived.by((): [number, number] => {
    const spans: [number, number][] = []
    if (optA) spans.push([optA.ride.span[0] - syncA, optA.ride.span[1] - syncA])
    if (optB) spans.push([optB.ride.span[0] - syncB, optB.ride.span[1] - syncB])
    if (!spans.length) return [-5, 5]
    return [Math.min(...spans.map((s) => s[0])), Math.max(...spans.map((s) => s[1]))]
  })
  function path(o: Option | null, sync: number, key: string, lo: number, hi: number): string {
    if (!o) return ''
    const series = (o.ride as unknown as Record<string, (number | null)[]>)[key] ?? []
    const [r0, r1] = range
    let d = ''
    let pen = false
    series.forEach((v, i) => {
      if (v === null) {
        pen = false
        return
      }
      const x = ((o.ride.t0 + i / o.ride.fps - sync - r0) / (r1 - r0)) * W
      const y = H - ((Math.max(lo, Math.min(hi, v)) - lo) / (hi - lo)) * H
      d += `${pen ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`
      pen = true
    })
    return d
  }
  const headX = $derived(((ta - syncA - range[0]) / (range[1] - range[0])) * W)
  const zeroX = $derived(((0 - range[0]) / (range[1] - range[0])) * W)
  function seekChart(e: MouseEvent) {
    const el = e.currentTarget as SVGElement
    const f = e.offsetX / el.clientWidth
    const rel = range[0] + f * (range[1] - range[0])
    pa?.pause()
    pb?.pause()
    playing = false
    pa?.seek(syncA + rel)
  }
</script>

<svelte:window {onkeydown} />

<div class="compare">
  <div class="titlebar">
    <h1>Compare <span class="muted small">{status}</span></h1>
    <label class="small"><input type="checkbox" bind:checked={skeleton} /> skeletons</label>
  </div>
  {#if loading}
    <p class="muted">Loading analysed rides…</p>
  {:else if options.length === 0}
    <p>No analysed rides yet: name yourself in Riders, then <em>Analyse rides</em> on Sessions.</p>
  {:else}
    <div class="sides">
      {#each [['a', a, optA, '#58a6ff'], ['b', b, optB, '#f0883e']] as const as [name, side, opt, colour]}
        <section>
          <div class="row pick">
            <strong style:color={colour}>{name.toUpperCase()}</strong>
            <select bind:value={side.key} onchange={() => (side.sync = null)}>
              <option value="">choose a ride…</option>
              {#each options as o (o.sid + o.ride.ride_id)}
                <option value={`${o.sid}:${o.ride.ride_id}`}>{label(o)}</option>
              {/each}
            </select>
            {#if tricks.length}
              <select onchange={(e) => { const t = tricks[Number(e.currentTarget.value)]; if (t) useTrick(name, t); e.currentTarget.value = '' }}>
                <option value="">or a trick…</option>
                {#each tricks as t, i}
                  <option value={i}>{t.name} · {t.rider} · {t.video} {clock(t.t).replace(/\.\d+$/, '')}</option>
                {/each}
              </select>
            {/if}
          </div>
          {#if opt}
            {#key side.key}
              {#if name === 'a'}
                <CropPlayer bind:this={pa} sessionId={opt.sid} rideId={opt.ride.ride_id} mirror={side.mirror}
                  {skeleton} {colour} start={syncA - 1} ontime={(t) => (ta = t)} />
              {:else}
                <CropPlayer bind:this={pb} sessionId={opt.sid} rideId={opt.ride.ride_id} mirror={side.mirror}
                  {skeleton} {colour} start={syncB - 1} ontime={(t) => (tb = t)} />
              {/if}
            {/key}
            <div class="row small">
              <span class="time">{clock(name === 'a' ? ta : tb)}</span>
              <button onclick={() => setSync(name)} title="This moment lines up with the other side's sync">set sync here</button>
              <button onclick={() => snap(name)} title="Snap the sync to the nearest detected turn or trick tag">snap to turn/tag</button>
              <label><input type="checkbox" bind:checked={side.mirror} /> mirror</label>
              <span class="muted">sync {clock(name === 'a' ? syncA : syncB)}{side.sync === null ? ' (ride start)' : ''}</span>
            </div>
            <p class="small muted">{opt.ride.score?.explanation ?? ''}</p>
          {:else}
            <div class="empty">Pick a ride{name === 'b' ? ' to compare with (a named surfer, or an imported clip)' : ''}</div>
          {/if}
        </section>
      {/each}
    </div>

    <div class="row transport">
      <button onclick={toSync} title="Both to 1 s before their sync points (s)">⇤ sync</button>
      <button onclick={() => step(-1)} title="One frame back (, or ←)">◀︎ frame</button>
      <button class="primary" onclick={toggle} title="Play/pause both (Space)">{playing ? 'Pause' : 'Play'}</button>
      <button onclick={() => step(1)} title="One frame on (. or →)">frame ▶︎</button>
      {#each [0.25, 0.5, 1] as r}
        <button class:active={rate === r} onclick={() => setRate(r)}>{r}×</button>
      {/each}
      <span class="small muted">{optA && optB ? `${(ta - syncA >= 0 ? '+' : '')}${(ta - syncA).toFixed(2)} s from sync` : ''}</span>
    </div>

    {#if optA || optB}
      <div class="charts">
        {#each MEASURES as m}
          <div class="chart">
            <span class="small muted">{m.label}</span>
            <!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
            <svg viewBox="0 0 {W} {H}" preserveAspectRatio="none" onclick={seekChart}>
              <line x1={zeroX} x2={zeroX} y1="0" y2={H} class="zero" />
              <path d={path(optA, syncA, m.key, m.lo, m.hi)} class="a" />
              <path d={path(optB, syncB, m.key, m.lo, m.hi)} class="b" />
              <line x1={headX} x2={headX} y1="0" y2={H} class="head" />
            </svg>
          </div>
        {/each}
        <p class="small muted">
          Time runs left to right in seconds from the sync points (dashed line). Click a chart to
          jump there. Lean is as each camera sees it; the other measures are in body proportions,
          so different cameras and distances compare.
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
  .sides {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
  }
  .pick select {
    max-width: 100%;
    flex: 1;
    background: var(--bg);
    color: var(--text);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 3px;
  }
  .empty {
    height: min(56vh, 520px);
    display: grid;
    place-items: center;
    border: 1px dashed var(--border);
    border-radius: 6px;
    color: var(--muted);
  }
  .row {
    display: flex;
    gap: 6px;
    align-items: center;
    flex-wrap: wrap;
    margin: 6px 0;
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
  }
  .chart svg {
    width: 100%;
    height: 64px;
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 4px;
    cursor: pointer;
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
