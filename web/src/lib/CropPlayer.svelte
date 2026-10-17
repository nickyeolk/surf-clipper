<script lang="ts">
  // Review video cropped to one surfer (004 US1): a CSS transform keeps the analysed crop box
  // (smoothed, so the view doesn't jitter) filling the panel, and a canvas in the same
  // transformed space draws the skeleton, interpolated between analysis frames. Mirror flips
  // the whole panel. The parent drives time through the exported functions.
  import { api, type KeypointData, type KeypointFrame } from './api'

  let {
    sessionId,
    rideId,
    mirror = false,
    skeleton = true,
    colour = '#58a6ff',
    start = null,
    ontime,
  }: {
    sessionId: string
    rideId: string
    mirror?: boolean
    skeleton?: boolean
    colour?: string
    start?: number | null // where to open once loaded (seconds in the session)
    ontime?: (t: number) => void
  } = $props()

  let video = $state<HTMLVideoElement>()
  let canvas = $state<HTMLCanvasElement>()
  let panel = $state<HTMLDivElement>()
  let data = $state<KeypointData | null>(null)
  let error = $state('')
  let transform = $state('')
  let boxes: [number, number, number, number][] = []

  const EDGES = [[5, 6], [5, 11], [6, 12], [11, 12], [11, 13], [13, 15], [12, 14], [14, 16], [5, 7], [7, 9], [6, 8], [8, 10]]
  const SMOOTH = 7 // frames each side for the crop box (about 0.5 s at 15 fps)

  $effect(() => {
    const ride = rideId
    data = null
    error = ''
    api.keypoints(sessionId, ride).then((d) => {
      data = d
      boxes = smoothBoxes(d.frames)
    }).catch((e) => (error = e.message))
  })

  function smoothBoxes(frames: KeypointFrame[]): [number, number, number, number][] {
    const raw = frames.map((f) => f.box.map((v) => v ?? NaN) as [number, number, number, number])
    return raw.map((_, i) => {
      const acc = [0, 0, 0, 0]
      let n = 0
      for (let j = Math.max(0, i - SMOOTH); j <= Math.min(raw.length - 1, i + SMOOTH); j++) {
        if (raw[j].every(Number.isFinite)) {
          for (let k = 0; k < 4; k++) acc[k] += raw[j][k]
          n++
        }
      }
      return (n ? acc.map((v) => v / n) : raw[i]) as [number, number, number, number]
    })
  }

  function indexAt(t: number): number {
    const d = data!
    const f = (t - d.frames[0].t) * d.fps
    return Math.max(0, Math.min(d.frames.length - 1, f))
  }

  function draw() {
    if (!data || !video || !panel || !canvas || data.frames.length === 0) return
    const t = video.currentTime
    const f = indexAt(t)
    const i = Math.floor(f)
    const j = Math.min(data.frames.length - 1, i + 1)
    const a = f - i
    const b0 = boxes[i], b1 = boxes[j]
    const box = b0.map((v, k) => v + (b1[k] - v) * a)
    const pw = panel.clientWidth, ph = panel.clientHeight
    const bw = box[2] - box[0], bh = box[3] - box[1]
    if ([bw, bh].every((v) => Number.isFinite(v) && v > 0)) {
      const s = Math.min(6, (ph * 0.8) / bh, (pw * 0.8) / bw)
      const cx = (box[0] + box[2]) / 2, cy = (box[1] + box[3]) / 2
      transform = `translate(${pw / 2 - cx * s}px, ${ph / 2 - cy * s}px) scale(${s})`
      const ctx = canvas.getContext('2d')!
      ctx.clearRect(0, 0, canvas.width, canvas.height)
      const inRide = t >= data.frames[0].t - 0.1 && t <= data.frames[data.frames.length - 1].t + 0.1
      if (skeleton && inRide) {
        const k0 = data.frames[i].kp, k1 = data.frames[j].kp
        const pt = (k: number): [number, number] | null => {
          const p = k0[k], q = k1[k]
          if (p[0] === null || p[1] === null || p[2] < 0.3) return null
          if (q[0] === null || q[1] === null || q[2] < 0.3) return [p[0], p[1]]
          return [p[0] + (q[0] - p[0]) * a, p[1] + (q[1] - p[1]) * a]
        }
        ctx.lineWidth = 2.5 / s
        ctx.strokeStyle = colour
        ctx.fillStyle = '#fff'
        for (const [u, v] of EDGES) {
          const p = pt(u), q = pt(v)
          if (!p || !q) continue
          ctx.beginPath()
          ctx.moveTo(p[0], p[1])
          ctx.lineTo(q[0], q[1])
          ctx.stroke()
        }
        for (let k = 5; k < 17; k++) {
          const p = pt(k)
          if (!p) continue
          ctx.beginPath()
          ctx.arc(p[0], p[1], 3 / s, 0, Math.PI * 2)
          ctx.fill()
        }
      }
    }
  }

  $effect(() => {
    let raf = 0
    const loop = () => {
      draw()
      if (video) ontime?.(video.currentTime)
      raf = requestAnimationFrame(loop)
    }
    raf = requestAnimationFrame(loop)
    return () => cancelAnimationFrame(raf)
  })

  // ---- driven by the parent -------------------------------------------------------------------
  export function time(): number {
    return video?.currentTime ?? 0
  }
  export function seek(t: number) {
    if (video) video.currentTime = Math.max(0, t)
  }
  export function play() {
    void video?.play()
  }
  export function pause() {
    video?.pause()
  }
  export function paused(): boolean {
    return video?.paused ?? true
  }
  export function setRate(r: number) {
    if (video) video.playbackRate = r
  }
  export function fps(): number {
    return data?.fps ?? 15
  }
  export function span(): [number, number] | null {
    return data && data.frames.length ? [data.frames[0].t, data.frames[data.frames.length - 1].t] : null
  }
</script>

<div class="panel" bind:this={panel}>
  {#if error}
    <p class="error small">{error}</p>
  {/if}
  <div class="mirror" style:transform={mirror ? 'scaleX(-1)' : ''}>
    <div class="stage" style:transform={transform} style:width="{data?.width ?? 1280}px" style:height="{data?.height ?? 720}px">
      <!-- svelte-ignore a11y_media_has_caption -->
      <video bind:this={video} src={api.videoUrl(sessionId)} preload="auto" muted
        onloadedmetadata={() => start !== null && seek(start)}></video>
      <canvas bind:this={canvas} width={data?.width ?? 1280} height={data?.height ?? 720}></canvas>
    </div>
  </div>
</div>

<style>
  .panel {
    position: relative;
    width: 100%;
    height: min(56vh, 520px);
    overflow: hidden;
    background: #000;
    border-radius: 6px;
  }
  .mirror {
    position: absolute;
    inset: 0;
  }
  .stage {
    position: absolute;
    left: 0;
    top: 0;
    transform-origin: 0 0;
  }
  video,
  canvas {
    position: absolute;
    left: 0;
    top: 0;
    width: 100%;
    height: 100%;
  }
  video {
    max-height: none; /* the global video style caps height; here the video must fill the stage */
    border-radius: 0;
    object-fit: fill;
  }
  canvas {
    pointer-events: none;
  }
</style>
