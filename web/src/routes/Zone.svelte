<script lang="ts">
  // Zone editor (US2): starts from the zone proposed from riders' movement (or the saved zone);
  // drag the four corners by role on a full-resolution still, with riders' feet shown as hints;
  // corners may sit outside the frame. Save re-runs rides.
  import { api, type FaceBand, type Zone, type ZoneInfo } from '../lib/api'
  import { apply, isSimple, poolToImage, type Corners, type Pt } from '../lib/geometry'

  let { sessionId }: { sessionId: string } = $props()

  let info = $state<ZoneInfo | null>(null)
  let corners = $state<Corners | null>(null)
  let entry = $state<{ side_a: boolean; side_b: boolean }>({ side_a: true, side_b: true })
  let face = $state<FaceBand | null>(null)
  let keyT = $state(600)
  let showFeet = $state(true)
  let dragging = $state<keyof Corners | null>(null)
  let status = $state('')
  let error = $state<string | null>(null)
  let saving = $state(false)
  let svg = $state<SVGSVGElement>()

  $effect(() => {
    api.zone(sessionId).then((z) => {
      info = z
      face = z.face
      keyT = Math.min(600, Math.floor(z.frame.duration_s / 2))
      const { width: w, height: h } = z.frame
      corners = z.zone
        ? structuredClone(z.zone.corners)
        : z.proposal
          ? structuredClone(z.proposal.zone.corners)
          : { back_a: [w * 0.3, h * 0.35], back_b: [w * 0.7, h * 0.35], front_a: [w * 0.1, h * 0.9], front_b: [w * 0.9, h * 0.9] }
      if (z.zone) entry = { side_a: z.zone.entry_walls.includes('side_a'), side_b: z.zone.entry_walls.includes('side_b') }
    }).catch((e) => (error = e.message))
  })

  function useProposal() {
    if (!info?.proposal) return
    corners = structuredClone(info.proposal.zone.corners)
    face = null
  }
  const w = $derived(info?.frame.width ?? 1)
  const h = $derived(info?.frame.height ?? 1)
  const pad = $derived(Math.max(w, h) * 0.6)
  const valid = $derived(corners ? isSimple(corners) : false)
  const H = $derived.by(() => {
    if (!corners || !valid) return null
    try {
      return poolToImage(corners)
    } catch {
      return null
    }
  })

  function line(a: Pt, b: Pt, n = 30): string {
    if (!H) return ''
    const pts: string[] = []
    for (let i = 0; i <= n; i++) {
      const p = apply(H, [a[0] + ((b[0] - a[0]) * i) / n, a[1] + ((b[1] - a[1]) * i) / n])
      if (p) pts.push(`${p[0].toFixed(1)},${p[1].toFixed(1)}`)
    }
    return pts.join(' ')
  }
  const grid = $derived.by(() => {
    if (!H) return []
    const out: string[] = []
    for (let i = 0; i <= 10; i++) {
      const t = i / 10
      out.push(line([t, 0], [t, 1]), line([0, t], [1, t]))
    }
    return out
  })
  const faceBand = $derived.by(() => {
    if (!H || !face?.face_v) return ''
    const [lo, hi] = face.face_v
    const a = line([0, lo], [1, lo])
    const b = line([1, hi], [0, hi])
    return a && b ? `${a} ${b}` : ''
  })

  function toSvg(e: PointerEvent): Pt {
    const m = svg!.getScreenCTM()!.inverse()
    const p = new DOMPoint(e.clientX, e.clientY).matrixTransform(m)
    return [Math.round(p.x), Math.round(p.y)]
  }
  function down(role: keyof Corners, e: PointerEvent) {
    dragging = role
    ;(e.target as Element).setPointerCapture(e.pointerId)
  }
  function move(e: PointerEvent) {
    if (!dragging || !corners) return
    corners[dragging] = toSvg(e)
    face = null // the estimated face belongs to the saved zone; re-estimated on save
  }
  function up() {
    dragging = null
  }

  async function save() {
    if (!info || !corners) return
    saving = true
    status = 'saving and re-running ride detection…'
    const zone: Zone = {
      epoch_id: 0,
      corners: $state.snapshot(corners) as Zone['corners'],
      entry_walls: (['side_a', 'side_b'] as const).filter((s) => entry[s]),
      side_areas: [],
      image_to_pool: null,
      undistort: null,
      origin: 'user',
      proposal_confidence: null,
      face_v: null,
    }
    try {
      const r = await api.saveZone(sessionId, zone)
      face = r.face
      status = `saved: ${r.rides} rides, ${r.short_attempts} short attempts` +
        (r.face?.face_v ? ` · wave face at depth ${r.face.face_v[0].toFixed(2)}–${r.face.face_v[1].toFixed(2)}` : '')
    } catch (e) {
      status = `not saved: ${(e as Error).message}`
    } finally {
      saving = false
    }
  }

  const ROLES: { key: keyof Corners; label: string; colour: string }[] = [
    { key: 'back_a', label: 'back a', colour: '#58a6ff' },
    { key: 'back_b', label: 'back b', colour: '#58a6ff' },
    { key: 'front_a', label: 'front a', colour: '#f0b429' },
    { key: 'front_b', label: 'front b', colour: '#f0b429' },
  ]
</script>

{#if error}
  <p class="error">{error}</p>
{:else if !info || !corners}
  <p class="muted">Loading…</p>
{:else}
  <div class="zone-editor">
    <section>
      <svg bind:this={svg} viewBox="{-pad} {-pad} {w + 2 * pad} {h + 2 * pad}"
        onpointermove={move} onpointerup={up} role="application" aria-label="Zone editor">
        <rect x={-pad} y={-pad} width={w + 2 * pad} height={h + 2 * pad} fill="#0d1117" />
        <image href={api.keyframeUrl(sessionId, keyT)} x="0" y="0" width={w} height={h} />
        <rect x="0" y="0" width={w} height={h} fill="none" stroke="#8b949e" stroke-width={w / 600} />
        {#if showFeet}
          {#each info.feet as [x, y]}
            <circle cx={x} cy={y} r={w / 400} fill="#ff7b72" opacity="0.5" />
          {/each}
        {/if}
        {#if faceBand}
          <polygon points={faceBand} fill="#3fb950" opacity="0.25" />
        {/if}
        {#each grid as pts}
          <polyline points={pts} fill="none" stroke="#ffffff" stroke-opacity="0.45" stroke-width={w / 900} />
        {/each}
        {#if H}
          <polyline points={line([0, 0], [1, 0])} fill="none" stroke="#8b949e" stroke-width={w / 250} />
          <polyline points={line([0, 0], [0, 1])} fill="none"
            stroke={entry.side_a ? '#f0b429' : '#8b949e'} stroke-width={w / 250} />
          <polyline points={line([1, 0], [1, 1])} fill="none"
            stroke={entry.side_b ? '#f0b429' : '#8b949e'} stroke-width={w / 250} />
        {/if}
        {#each ROLES as r}
          {@const [x, y] = corners[r.key]}
          <g class="handle" onpointerdown={(e) => down(r.key, e)} role="button" tabindex="-1"
            aria-label={r.label}>
            <circle cx={x} cy={y} r={w / 70} fill={r.colour} stroke="#fff" stroke-width={w / 500} />
            <text x={x + w / 50} y={y - w / 60} fill={r.colour} font-size={w / 32}>{r.label}</text>
          </g>
        {/each}
      </svg>
    </section>
    <aside class="panel">
      <h1>Wave zone</h1>
      <p class="small">
        Drag the corners so the grid lies flat on the pool. <strong>back a / back b</strong>: the
        two ends of the back wall. <strong>front a / front b</strong>: the front ends of the side
        walls (side wall a runs back a → front a). Corners may sit outside the photo.
      </p>
      <p class="small muted">
        Red dots: where people stood on boards in this session; riding should fall inside the
        grid. Green: the wave face estimated from the saved zone.
      </p>
      {#if info.proposal}
        {@const pr = info.proposal}
        <div class="proposal small" class:bad={pr.unreliable}>
          {#if pr.unreliable}
            <strong>No reliable proposal</strong> — drag the corners onto the pool yourself.
          {:else}
            <strong>Proposed from how riders moved</strong> (confidence {Math.round(pr.confidence * 100)}%,
            {pr.points} positions). Check that the side walls sit on the walls, then save.
          {/if}
          {#each pr.notes as note}<br />· {note}{/each}
          {#if info.zone}
            <br /><button onclick={useProposal}>use proposal</button>
          {/if}
        </div>
      {/if}
      {#if !valid}<p class="error small">The edges cross: check which corner is which.</p>{/if}
      <div class="row">
        <label><input type="checkbox" bind:checked={entry.side_a} /> riders enter over side a</label>
      </div>
      <div class="row">
        <label><input type="checkbox" bind:checked={entry.side_b} /> riders enter over side b</label>
      </div>
      <div class="row">
        <label><input type="checkbox" bind:checked={showFeet} /> show riders' feet</label>
      </div>
      <div class="row">
        <label class="small">Still at
          <input type="range" min="0" max={Math.floor(info.frame.duration_s)} step="10" bind:value={keyT} />
          {Math.floor(keyT / 60)}:{String(keyT % 60).padStart(2, '0')}
        </label>
      </div>
      <div class="row">
        <button class="primary" disabled={!valid || saving} onclick={save}>Save & re-run rides</button>
        <a class="button secondary" href={`#/label/${sessionId}`}>Label rides →</a>
      </div>
      <p class="small">{status}</p>
    </aside>
  </div>
{/if}

<style>
  .zone-editor {
    display: grid;
    grid-template-columns: minmax(0, 1fr) 320px;
    gap: 16px;
    align-items: start;
  }
  svg {
    width: 100%;
    max-height: calc(100vh - 90px);
    touch-action: none;
    user-select: none;
  }
  .handle {
    cursor: grab;
  }
  .panel {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 12px;
  }
  .proposal {
    border-left: 3px solid var(--ok);
    padding: 4px 8px;
    margin: 8px 0;
    background: var(--bg);
  }
  .proposal.bad {
    border-color: var(--q);
  }
  .secondary {
    background: var(--panel);
    border-color: var(--border);
  }
</style>
