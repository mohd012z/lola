# Historical Transfer v2

This evidence tier tests whether LOLA can use an abstract diagnostic priority learned from independent real repository incidents on a distinct later historical incident.

## Learned abstraction

`preflight_validity`: validate the artifact's parser/compile/config integrity before spending diagnostic actions on runtime, semantic, or consumer-output hypotheses.

## Training evidence

Two frozen historical incidents are treated as independent origins:

1. PowerShell parser failure in `scan-security.ps1`
   - before: `2d111721f88c794506c5e56a9471afee7474c635`
   - fix: `475d5cb2487334b282aa0b7616258f36e769c35d`
   - failure: extra closing bracket in `ValidateSet`
2. Python parser failure in `lola_office_layout.py`
   - before: `39425e889a26c769b3fe09d6f4eaaaeb0c3b20a6`
   - fix: `79c62b3cfbc002d800df09526c0451101758849a`
   - failure: invalid Python import syntax

The fixture stores commit and blob provenance plus SHA-256 digests of the exact frozen excerpts.

## Historical holdout

The holdout comes from `codex-security.yaml`:

- before: `66d9bd02d5b9ed195aaccf6d922b8b08d522505e`
- fix: `6b1929f587050e378bfb4ae86817d7c9a9370e10`
- origin domain: `semgrep-yaml-parser`
- transfer distance: T3

The baseline diagnostic order reaches `preflight_validity` after four inspections. Governed historical learning moves that probe first, reducing the same verified diagnosis to one inspection. A separate semantic-logic regression probe must still pass.

## Falsification

An unresolved `FALSIFIED` counterexample is injected in the negative test. Transfer governance must then refuse promotion, learned ordering must collapse back to baseline ordering, and the Tiny-to-Beast growth gate must fail.

## Claim boundary

The holdout was selected after examining repository history, so it is not prospective and not blind. A passing run may report only:

- `historical_transfer_claim: true`
- `blind_holdout_claim: false`
- `prospective_claim: false`
- `production_world_claim: false`

This result supports cross-language transfer of the narrow `preflight_validity` diagnostic priority across frozen historical LOLA incidents. It does not establish broad autonomous intelligence, prospective performance, or production-world reliability.

## Reproduce

```bash
python lola.py --historical-transfer-benchmark
```
