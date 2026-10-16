<script lang="ts">
  import Sessions from './routes/Sessions.svelte'
  import Label from './routes/Label.svelte'
  import Zone from './routes/Zone.svelte'
  import Review from './routes/Review.svelte'
  import RiderLabels from './routes/RiderLabels.svelte'
  import Riders from './routes/Riders.svelte'

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
  {:else if route[0] === 'rider-labels' && route[1]}
    {#key route[1]}
      <RiderLabels sessionId={route[1]} />
    {/key}
  {:else if route[0] === 'riders' && route[1]}
    {#key route[1]}
      <Riders sessionId={route[1]} />
    {/key}
  {:else if route[0] === 'review' && route[1]}
    {#key route.join('/')}
      <Review sessionId={route[1]} rider={route[2] === 'rider' && route[3] ? decodeURIComponent(route[3]) : undefined} />
    {/key}
  {:else if route[0] === 'zone' && route[1]}
    {#key route[1]}
      <Zone sessionId={route[1]} />
    {/key}
  {:else}
    <Sessions />
  {/if}
</main>
