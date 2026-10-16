# Contract: CLI additions (002)

Conventions as in [001](../../001-ride-detection-clipping/contracts/cli.md): exit 0 success,
1 failure, 2 usage error; `--json` for machine output; nothing writes to the source folder.

| Command | Purpose |
| --- | --- |
| `surfclip run VIDEO` | now ends with the `riders` stage (after rides) |
| `surfclip riders VIDEO [--json]` | list groups (name or "Rider N", ride count, example ride) and the queue length |
| `surfclip riders name VIDEO --ride RIDE_ID --name NAME` | name the group containing that ride |
| `surfclip export VIDEO --rider NAME [--reel] [--per-rider] [--manifest]` | export one rider's clips or reel; all riders' folders; the manifest |
| `surfclip labels riders propose VIDEO` / `finalize VIDEO` | create / finalize rider labels from the current groups (editing is done in the UI) |
| `surfclip eval riders VIDEO [--json]` | SC-001 (share of rides in their true rider's group) and SC-002 (simulated corrections for named riders) |
| `surfclip models download` | also fetches the embedding weights if `riders.descriptor` uses them |
