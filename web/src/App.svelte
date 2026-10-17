<script lang="ts">
  import Sessions from './routes/Sessions.svelte'
  import Label from './routes/Label.svelte'
  import Zone from './routes/Zone.svelte'
  import Review from './routes/Review.svelte'
  import RiderLabels from './routes/RiderLabels.svelte'
  import Riders from './routes/Riders.svelte'
  import Viewer from './routes/Viewer.svelte'
  import Compare from './routes/Compare.svelte'
  import Reference from './routes/Reference.svelte'
  import Best from './routes/Best.svelte'
  import Tricks from './routes/Tricks.svelte'

  let hash = $state(location.hash)
  $effect(() => {
    const onHash = () => (hash = location.hash)
    addEventListener('hashchange', onHash)
    return () => removeEventListener('hashchange', onHash)
  })
  const route = $derived(hash.replace(/^#\/?/, '').split('?')[0].split('/'))
  const query = $derived(hash.includes('?') ? hash.slice(hash.indexOf('?') + 1) : '')
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
  {:else if route[0] === 'tricks'}
    <Tricks />
  {:else if route[0] === 'best' && route[1]}
    {#key route[1]}
      <Best sessionId={route[1]} />
    {/key}
  {:else if route[0] === 'reference' && route[1]}
    {#key route[1]}
      <Reference sessionId={route[1]} />
    {/key}
  {:else if route[0] === 'compare'}
    <Compare {query} />
  {:else if route[0] === 'viewer' && route[1]}
    {#key route[1]}
      <Viewer sessionId={route[1]} />
    {/key}
  {:else if route[0] === 'zone' && route[1]}
    {#key route[1]}
      <Zone sessionId={route[1]} />
    {/key}
  {:else}
    <Sessions />
  {/if}
</main>
