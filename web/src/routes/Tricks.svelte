<script lang="ts">
  // Tricks (004 US4): every trick you tagged, across sessions, grouped by name. Open one in
  // Compare (the tag becomes the sync point) or remove it.
  import { api, clock, type TrickTag } from '../lib/api'

  let tags = $state<TrickTag[] | null>(null)
  let error = $state('')
  let filter = $state('')

  async function load() {
    try {
      tags = await api.tricks()
    } catch (e) {
      error = (e as Error).message
    }
  }
  $effect(() => {
    void load()
  })

  const groups = $derived.by(() => {
    const out = new Map<string, TrickTag[]>()
    for (const t of tags ?? []) {
      const key = t.name.toLowerCase()
      if (filter && !key.includes(filter.toLowerCase())) continue
      out.set(key, [...(out.get(key) ?? []), t])
    }
    return [...out.entries()].sort((a, b) => b[1].length - a[1].length)
  })

  async function remove(t: TrickTag) {
    if (!confirm(`Remove the ${t.name} tag at ${clock(t.t)}?`)) return
    await api.deleteTrick(t.session_id, t.edit_id)
    await load()
  }
  const href = (t: TrickTag) => `#/compare?a=${t.session_id}:${t.ride_id}&sa=${t.t.toFixed(3)}`
</script>

<h1>Tricks</h1>
{#if error}
  <p class="error">{error}</p>
{:else if !tags}
  <p class="muted">Loading…</p>
{:else if tags.length === 0}
  <p>No tricks tagged yet. In Review, select one of your rides, put the playhead on the trick and press <kbd>g</kbd>.</p>
{:else}
  <input placeholder="filter by name" bind:value={filter} />
  {#each groups as [name, list] (name)}
    <h2>{list[0].name} <span class="muted small">{list.length}</span></h2>
    <ul>
      {#each list as t (t.session_id + t.edit_id)}
        <li class="small">
          <span>{t.rider} · {t.video} · {clock(t.t).replace(/\.\d+$/, '')}</span>
          <a href={href(t)}>compare</a>
          <button class="link" onclick={() => remove(t)}>remove</button>
        </li>
      {/each}
    </ul>
  {/each}
{/if}

<style>
  ul {
    list-style: none;
    padding: 0;
  }
  li {
    display: flex;
    gap: 12px;
    padding: 3px 0;
  }
  .link {
    background: none;
    border: none;
    color: var(--accent);
    cursor: pointer;
    padding: 0;
  }
  input {
    background: var(--bg);
    color: var(--text);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 4px 6px;
  }
  kbd {
    border: 1px solid var(--border);
    border-radius: 3px;
    padding: 0 4px;
  }
</style>
