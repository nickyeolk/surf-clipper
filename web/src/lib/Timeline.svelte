<script lang="ts">
  // One timeline lane: activity strip, ride bars coloured by verdict, scanned span, playhead.
  // Click to seek; click a bar to select that ride.
  import type { Activity, LabelItem } from './api'

  interface Props {
    from: number
    to: number
    items: LabelItem[]
    activity: Activity | null
    current: number
    scannedTo: number
    selectedId: string | null
    pendingStart: number | null
    onseek: (t: number) => void
    onselect: (id: string) => void
  }
  let { from, to, items, activity, current, scannedTo, selectedId, pendingStart, onseek, onselect }:
    Props = $props()

  const COLOURS: Record<string, string> = {
    '?': '#f0b429', ok: '#3fb950', fix: '#58a6ff', no: '#6e7681', add: '#bc8cff',
  }
  let canvas: HTMLCanvasElement
  let width = $state(800)
  const height = 64

  const x = (t: number) => ((t - from) / (to - from)) * width

  $effect(() => {
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    const dpr = devicePixelRatio || 1
    canvas.width = width * dpr
    canvas.height = height * dpr
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    ctx.clearRect(0, 0, width, height)
    ctx.fillStyle = '#161b22'
    ctx.fillRect(0, 0, width, height)
    // scanned-for-misses span
    if (scannedTo > from) {
      ctx.fillStyle = 'rgba(88,166,255,0.10)'
      ctx.fillRect(0, 0, Math.min(width, x(scannedTo)), height)
    }
    // activity strip (top): how much of each second looks like riding
    if (activity) {
      const { bin_s, values } = activity
      const i0 = Math.max(0, Math.floor(from / bin_s))
      const i1 = Math.min(values.length, Math.ceil(to / bin_s))
      for (let i = i0; i < i1; i++) {
        const v = values[i]
        if (v <= 0) continue
        ctx.fillStyle = `rgba(63,185,80,${0.25 + 0.75 * v})`
        ctx.fillRect(x(i * bin_s), 2, Math.max(1, x((i + 1) * bin_s) - x(i * bin_s)), 12)
      }
    }
    // ride bars
    for (const it of items) {
      if (it.end_s < from || it.start_s > to) continue
      const x0 = x(it.start_s)
      const w = Math.max(2, x(it.end_s) - x0)
      ctx.fillStyle = COLOURS[it.verdict]
      ctx.globalAlpha = it.detected_as === 'short' && it.verdict === '?' ? 0.55 : 0.9
      ctx.fillRect(x0, 20, w, 30)
      ctx.globalAlpha = 1
      if (it.id === selectedId) {
        ctx.strokeStyle = '#ffffff'
        ctx.lineWidth = 2
        ctx.strokeRect(x0 - 1, 19, w + 2, 32)
      }
    }
    if (pendingStart !== null && pendingStart >= from && pendingStart <= to) {
      ctx.fillStyle = COLOURS.add
      ctx.fillRect(x(pendingStart), 16, Math.max(2, x(current) - x(pendingStart)), 38)
    }
    // playhead
    ctx.fillStyle = '#ff7b72'
    ctx.fillRect(x(current) - 1, 0, 2, height)
  })

  function click(e: MouseEvent) {
    const rect = canvas.getBoundingClientRect()
    const t = from + ((e.clientX - rect.left) / rect.width) * (to - from)
    const y = e.clientY - rect.top
    if (y >= 20 && y <= 50) {
      const hit = items.find((it) => it.start_s <= t && it.end_s >= t)
      if (hit) {
        onselect(hit.id)
        return
      }
    }
    onseek(t)
  }
</script>

<div class="lane" bind:clientWidth={width}>
  <canvas bind:this={canvas} style:width="{width}px" style:height="{height}px" onclick={click}
  ></canvas>
</div>

<style>
  .lane {
    width: 100%;
  }
  canvas {
    display: block;
    cursor: pointer;
    border-radius: 4px;
  }
</style>
