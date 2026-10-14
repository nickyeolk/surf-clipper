<script lang="ts">
  import Sessions from './routes/Sessions.svelte'
  import Label from './routes/Label.svelte'

  let hash = $state(location.hash)
  $effect(() => {
    const onHash = () => (hash = location.hash)
    addEventListener('hashchange', onHash)
    return () => removeEventListener('hashchange', onHash)
  })
  const route = $derived(hash.replace(/^#\/?/, '').split('/'))
</script>

<header>
  <a href="#/">Surf Session Clipper</a>
</header>

<main>
  {#if route[0] === 'label' && route[1]}
    {#key route[1]}
      <Label sessionId={route[1]} />
    {/key}
  {:else}
    <Sessions />
  {/if}
</main>
