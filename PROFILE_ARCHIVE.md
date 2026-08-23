# Profile Archive

## Stored designs

| Tag | Design | Recovery command |
|---|---|---|
| `profile-high-energy-v1` | The prior bold high-energy profile with a prominent cinematic-style header, badges, and direct build narrative. | `git checkout profile-high-energy-v1 -- README.md .github/workflows/refresh-profile.yml` |
| `profile-minimal-dynamic-v1` | The minimal build-mode profile containing the live-build signal and generic project table. | `git checkout profile-minimal-dynamic-v1 -- README.md .github/workflows/refresh-profile.yml` |
| `profile-recursion-field-v1` | The minimal build-mode profile featuring the generated Fractal Tree recursion field. | `git checkout profile-recursion-field-v1 -- README.md .github/workflows/refresh-profile.yml` |

## Revision rule

Before publishing any future profile design, create a uniquely named Git tag for the current `main` revision. The next style is then treated as an independent experiment, not an overwrite without recovery. If a design is not liked, restore the chosen archive tag or publish a clearly different direction while retaining the previous tag.
