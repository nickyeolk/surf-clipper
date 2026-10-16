<script lang="ts" module>
  export interface Chapter {
    start: number // seconds in this video
    end: number
    label: string
  }
</script>

<script lang="ts">
  // Full-quality player for exported files (003 US3): frame steps, slow motion, chapters (the
  // rides of a compilation) and "save still". Plays the exported HEVC/H.264 file itself.
  import { clock } from './api'

  let {
    src,
    fps,
    chapters = [],
    onstill,
  }: { src: string; fps: number; chapters?: Chapter[]; onstill?: (t: number) => void } = $props()

  const RATES = [0.25, 0.5, 1]
  let video = $state<HTMLVideoElement>()
  let paused = $state(true)
  let current = $state(0)
  let duration = $state(0)
  let rate = $state(1)
  let failed = $state(false)
  const frame = $derived(1 / (fps || 30))
  const hevc = typeof document !== 'undefined' &&
    document.createElement('video').canPlayType('video/mp4; codecs="hvc1.2.4.L153.B0"') !== ''

  $effect(() => {
    void src
    failed = false
    current = 0
  })

  const total = $derived(chapters.length ? chapters[chapters.length - 1].end : duration || 1)
  const chapterIdx = $derived(chapters.findIndex((c) => current >= c.start && current < c.end))

  function seek(t: number) {
    if (video) video.currentTime = Math.max(0, Math.min(duration || t, t))
  }
  function step(n: number) {
    video?.pause()
    seek(current + n * frame)
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
  function goChapter(d: number) {
    const i = Math.max(0, Math.min(chapters.length - 1, (chapterIdx < 0 ? 0 : chapterIdx) + d))
    if (chapters[i]) seek(chapters[i].start)
  }
  function still() {
    video?.pause()
    onstill?.(current)
  }
  function onkeydown(e: KeyboardEvent) {
    const tag = (e.target as HTMLElement).tagName
    if (tag === 'INPUT' || tag === 'SELECT' || e.ctrlKey || e.metaKey || e.altKey) return
    const k = e.key
    if (k === ' ') toggle()
    else if (k === ',' || k === 'ArrowLeft') step(e.shiftKey ? -Math.round(fps) : -1)
    else if (k === '.' || k === 'ArrowRight') step(e.shiftKey ? Math.round(fps) : 1)
    else if (k === '[') goChapter(-1)
    else if (k === ']') goChapter(1)
    else if (k === 'c' && onstill) still()
    else if (k === '-') setRate(RATES[Math.max(0, RATES.indexOf(rate) - 1)])
    else if (k === '+' || k === '=') setRate(RATES[Math.min(RATES.length - 1, RATES.indexOf(rate) + 1)])
    else return
    e.preventDefault()
  }
</script>

<svelte:window {onkeydown} />

<div class="player">
  <!-- svelte-ignore a11y_media_has_caption -->
  <video bind:this={video} bind:paused bind:duration {src} preload="auto" onclick={toggle}
    ontimeupdate={() => (current = video?.currentTime ?? 0)}
    onloadedmetadata={() => video && (video.playbackRate = rate)}
    onerror={() => (failed = true)}></video>
  {#if failed}
    <p class="error small">
      This browser could not play the file{hevc ? '' : ' (it cannot decode HEVC, used for HDR clips)'}.
      Edge or Chrome on Windows play it; or <a href={src} download>download it</a>.
    </p>
  {/if}
  <div class="controls">
    <button onclick={() => step(-Math.round(fps))} title="Back 1 s (Shift+←)">−1s</button>
    <button onclick={() => step(-1)} title="Back one frame (, or ←)">◀︎ frame</button>
    <button class="primary" onclick={toggle} title="Play/pause (Space)">{paused ? 'Play' : 'Pause'}</button>
    <button onclick={() => step(1)} title="Forward one frame (. or →)">frame ▶︎</button>
    <button onclick={() => step(Math.round(fps))} title="Forward 1 s (Shift+→)">+1s</button>
    <span class="time">{clock(current)} / {clock(duration || 0)}</span>
    <span class="rates">
      {#each RATES as r}
        <button class:active={rate === r} onclick={() => setRate(r)}>{r}×</button>
      {/each}
    </span>
    {#if onstill}
      <button onclick={still} title="Save this frame as a full-resolution photo (c)">save still</button>
    {/if}
  </div>
  {#if chapters.length > 1}
    <div class="chapters">
      <button onclick={() => goChapter(-1)} title="Previous ride ([)">⏮</button>
      <div class="bar" role="group" aria-label="Rides">
        {#each chapters as c, i}
          <button class="seg" class:cur={i === chapterIdx} title={c.label}
            style:width="{((c.end - c.start) / total) * 100}%"
            onclick={() => seek(c.start)} aria-label={c.label}></button>
        {/each}
        <span class="head" style:left="{Math.min(100, (current / total) * 100)}%"></span>
      </div>
      <button onclick={() => goChapter(1)} title="Next ride (])">⏭</button>
    </div>
    <p class="small muted">{chapterIdx >= 0 ? chapters[chapterIdx].label : ''}</p>
  {/if}
</div>

<style>
  video {
    width: 100%;
    max-height: calc(100vh - 260px);
    background: #000;
    border-radius: 6px;
  }
  .controls,
  .chapters {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    align-items: center;
    margin-top: 6px;
  }
  .time {
    font-variant-numeric: tabular-nums;
    margin: 0 6px;
  }
  .rates .active {
    border-color: var(--accent);
    color: var(--accent);
  }
  .bar {
    position: relative;
    flex: 1;
    min-width: 0;
    overflow: hidden;
    display: flex;
    height: 14px;
    gap: 1px;
  }
  .seg {
    flex: none;
    height: 100%;
    padding: 0;
    border: none;
    border-radius: 2px;
    background: var(--border);
    min-width: 2px;
  }
  .seg.cur {
    background: var(--accent);
  }
  .head {
    position: absolute;
    top: -3px;
    bottom: -3px;
    width: 2px;
    background: var(--text);
    pointer-events: none;
  }
</style>
