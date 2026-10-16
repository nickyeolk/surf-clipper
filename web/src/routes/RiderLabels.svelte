<script lang="ts">
  // Rider labels (evaluation, feature 002): say who rode each labelled ride. The tool's groups
  // are shown as proposals; name a group to label all its rides, then fix single rides.
  // Labels never change rides, rider edits or groups.
  import { api, clock, type RiderLabelItem, type RiderLabelWork } from '../lib/api'

  let { sessionId }: { sessionId: string } = $props()

  let work = $state<RiderLabelWork | null>(null)
  let error = $state<string | null>(null)
  let status = $state('')
  let video = $state<HTMLVideoElement>()
  let playing = $state<string | null>(null)
  let groupNames = $state<Record<string, string>>({})
  let namedText = $state('')
  let onlyOpen = $state(false)
  let stopAt: number | null = null

  $effect(() => {
    api.riderLabels(sessionId)
      .then((w) => {
        work = w
        namedText = w.named.join(', ')
      })
      .catch((e) => (error = e.message))
  })

  const items = $derived(work ? work.items : [])
  const names = $derived(
    [...new Set([...items.map((i) => i.rider).filter((r): r is string => !!r), ...(work?.named ?? [])])].sort(),
  )
  const remaining = $derived(items.filter((i) => !i.rider).length)
  // Sections: one per proposed group, largest first; rides without a proposal last.
  const sections = $derived.by(() => {
    const by = new Map<string, RiderLabelItem[]>()
    for (const it of items) {
      const key = it.proposed ?? '(no proposal)'
      if (!by.has(key)) by.set(key, [])
      by.get(key)!.push(it)
    }
    return [...by.entries()].sort((a, b) =>
      a[0] === '(no proposal)' ? 1 : b[0] === '(no proposal)' ? -1 : b[1].length - a[1].length,
    )
  })

  // ---- saving ---------------------------------------------------------------------------------
  let saveTimer: ReturnType<typeof setTimeout> | undefined
  function changed() {
    status = 'unsaved'
    clearTimeout(saveTimer)
    saveTimer = setTimeout(save, 600)
  }
  async function save() {
    if (!work) return
    status = 'saving…'
    try {
      work = await api.saveRiderLabels(sessionId, $state.snapshot(work) as RiderLabelWork)
      status = 'saved'
    } catch (e) {
      status = `save failed: ${(e as Error).message}`
    }
  }
  async function finish() {
    await save()
    try {
      const r = await api.finalizeRiderLabels(sessionId)
      status = `labels written: ${r.rides} rides, ${r.riders} riders`
      if (work) work.finalized = true
    } catch (e) {
      status = (e as Error).message
    }
  }

  // ---- actions --------------------------------------------------------------------------------
  function labelGroup(key: string, list: RiderLabelItem[], overwrite: boolean) {
    const name = (groupNames[key] ?? '').trim()
    if (!name) return
    for (const it of list) if (overwrite || !it.rider) it.rider = name
    changed()
  }
  function setRider(it: RiderLabelItem, value: string) {
    if (value === '__new') {
      const name = prompt('Rider name')?.trim()
      if (!name) return
      it.rider = name
    } else {
      it.rider = value || null
    }
    changed()
  }
  function setNamed() {
    if (!work) return
    work.named = namedText.split(',').map((s) => s.trim()).filter(Boolean)
    changed()
  }
  function play(it: RiderLabelItem) {
    if (!video) return
    playing = it.id
    video.currentTime = Math.max(0, it.start_s - 1)
    stopAt = it.end_s + 1
    void video.play()
  }
  function ontimeupdate() {
    if (video && stopAt !== null && video.currentTime >= stopAt) {
      video.pause()
      stopAt = null
    }
  }
  const stillOf = (it: RiderLabelItem) =>
    it.detected_ride ? api.riderStillUrl(sessionId, it.detected_ride) : null
</script>

{#if error}
  <p class="error">{error}</p>
{:else if !work}
  <p class="muted">Loading… (the first time, the tool groups the rides; this can take a minute)</p>
{:else}
  <div class="rl">
    <section class="side">
      <h1>{work.source} <span class="muted small">rider labels</span></h1>
      <!-- svelte-ignore a11y_media_has_caption -->
      <video bind:this={video} src={api.videoUrl(sessionId)} preload="metadata" {ontimeupdate} controls></video>
      <p class="small"><strong>{items.length - remaining}</strong> of {items.length} rides labelled · {status}</p>
      <label class="small">
        Riders you'd name in normal use (comma separated, at least yourself):
        <input class="text" bind:value={namedText} onchange={setNamed} placeholder="me" />
      </label>
      <div class="row">
        <button class="primary" disabled={remaining > 0 || !work.named.length} onclick={finish}
          title={remaining > 0 ? 'Label every ride first' : !work.named.length ? 'Say who you would name' : 'Write the labels file'}>
          Finish ({remaining} left)
        </button>
        <label class="small"><input type="checkbox" bind:checked={onlyOpen} /> only unlabelled</label>
      </div>
      <details class="help small" open>
        <summary>How to label</summary>
        <p>
          Each block is a group the tool thinks is one person. Type the person's name in the
          block's box and press <em>label group</em> (only unlabelled rides change); then fix any
          ride that is someone else with its menu. Click a still to play the ride. Use the same
          name for the same person across groups. Names only need to be consistent within this
          session.
        </p>
      </details>
    </section>

    <section class="groups">
      {#each sections as [key, list] (key)}
        {@const shown = onlyOpen ? list.filter((i) => !i.rider) : list}
        {#if shown.length}
          <div class="group">
            <div class="ghead">
              <strong>{key}</strong> <span class="muted">{list.length} rides</span>
              <input class="text" list="rider-names" placeholder="who is this?" bind:value={groupNames[key]}
                onkeydown={(e) => e.key === 'Enter' && labelGroup(key, list, false)} />
              <button onclick={() => labelGroup(key, list, false)}>label group</button>
            </div>
            <div class="cards">
              {#each shown as it (it.id)}
                <div class="card" class:done={!!it.rider} class:playing={playing === it.id}>
                  <button class="thumb" onclick={() => play(it)} title="Play this ride">
                    {#if stillOf(it)}
                      <img loading="lazy" alt="" src={stillOf(it)} />
                    {:else}
                      <span class="muted small">no still</span>
                    {/if}
                  </button>
                  <span class="small time">{clock(it.start_s)}</span>
                  <select value={it.rider ?? ''} onchange={(e) => setRider(it, (e.currentTarget as HTMLSelectElement).value)}>
                    <option value="">—</option>
                    {#each names as n}<option value={n}>{n}</option>{/each}
                    <option value="__new">+ new name…</option>
                  </select>
                </div>
              {/each}
            </div>
          </div>
        {/if}
      {/each}
    </section>
  </div>
  <datalist id="rider-names">
    {#each names as n}<option value={n}></option>{/each}
  </datalist>
{/if}

<style>
  .rl {
    display: grid;
    grid-template-columns: 380px minmax(0, 1fr);
    gap: 16px;
    align-items: start;
  }
  .side {
    position: sticky;
    top: 8px;
  }
  .side video {
    max-height: 240px;
  }
  .text {
    background: var(--bg);
    color: var(--text);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 3px 6px;
    font: inherit;
  }
  .side .text {
    width: 100%;
    margin-top: 4px;
  }
  .group {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 8px;
    margin-bottom: 10px;
  }
  .ghead {
    display: flex;
    gap: 8px;
    align-items: center;
    margin-bottom: 6px;
  }
  .cards {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }
  .card {
    display: flex;
    flex-direction: column;
    gap: 2px;
    width: 104px;
    padding: 3px;
    border-radius: 6px;
    border: 1px solid transparent;
  }
  .card.done {
    border-color: #12361f;
    background: #0f2117;
  }
  .card.playing {
    border-color: var(--accent);
  }
  .thumb {
    padding: 0;
    height: 120px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: #000;
    overflow: hidden;
  }
  .thumb img {
    max-height: 120px;
    max-width: 100%;
  }
  select {
    background: var(--bg);
    color: var(--text);
    border: 1px solid var(--border);
    border-radius: 4px;
    font: inherit;
    font-size: 12px;
  }
</style>
