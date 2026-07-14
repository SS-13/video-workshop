# 3.0.0 Test Report

## Automated Tests

- Control Plane: `37 passed`
- Video Edit: `8 passed`
- Daily Engineering Loop: `11 passed`
- Total: `56 passed`

## Registry And Contracts

- Content types: `3`
- Profiles: `3`
- Commands: `58`
- Agents: `6`
- Registry errors: `0`
- Run / Artifact / PublishPackage contracts: pass

## Clean Clone

A temporary workspace containing only Git-eligible files passed:

- `npm run setup`
- `npm run doctor`
- `npm run context -- --json`
- `npm run new-day -- 2026-01-01` -> `Day 1`
- `vp observe`
- `vp evolve` -> TopK selected
- repeated `vp evolve` -> existing TopK reused

The clone reported `readyForContent=true`, `readyForRender=true`, and
`loopReady=true` on the verification machine.

Bootstrap coverage also verifies that every required ignored directory exists
and that a second initialization preserves locally edited seed files.

## Privacy And Portability

- Personal ideas, scripts, media, logs, style profiles, dictionaries, reports,
  cookies, credentials, runtime state, and generated covers are ignored.
- Public script and subtitle defaults remain available without private files.
- Subtitle correction succeeds unchanged when optional dictionaries are absent.
- Synthetic 3:4 and 4:3 cover renders passed QC at `1080x1440` and `1440x1080`.
- Cover export uses the current Node executable or `NODE_BIN`, not a user home
  path.
- Public files contain no absolute home-directory dependency.

## Media And Release Gates

- Short golden regression: pass
- Historical Shadow isolation: pass
- Golden transcript normalized accuracy gate: pass
- Legacy fallback: pass
- Real-video Canary: pass
- Manual activation: pass

Raw personal-media reports and Canary Run IDs are intentionally not published.
The deterministic control-plane and helper tests remain in the repository.
