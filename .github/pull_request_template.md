## Problem

What production or maintenance problem does this PR solve?

## Change

What behavior, command, Skill, or rule changed?

## Verification

- [ ] Control-plane tests pass
- [ ] Video-edit tests pass
- [ ] Daily Evolution tests pass
- [ ] Registry and contracts pass
- [ ] Clean-clone smoke passes on GitHub Actions
- [ ] Layout changes include migration and recovery instructions
- [ ] Production-path changes include real Canary evidence
- [ ] No personal content, credentials, absolute home paths, or large media are included
- [ ] Stable v2 and legacy fallback impact is documented

## Linked TopK Issues

- [ ] Each linked TopK candidate has passed `vp evolve complete`
- [ ] Nightly Issue sync has applied `status:verified`
- [ ] Use `Closes #<issue-number>` only after both checks above pass
- [ ] Do not manually close a TopK Issue before the PR reaches `main`
- [ ] Top-K repair branches use `fix/topk-<candidate-id>`
- [ ] Top-K repair PRs are marked Ready for review before merge
- [ ] Top-K repair PRs pass `vp evolve issues check-pr --require-topk`

## Rollback

How can this change be disabled or reverted without modifying production media?
