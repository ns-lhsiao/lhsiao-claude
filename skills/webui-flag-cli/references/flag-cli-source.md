# flag-cli upstream source

## Where it lives

- CLI package: https://github.com/netSkope/script-utils/tree/main/flag-cli
  - Full command reference: `flag-cli` README (linked above)
  - Team registry / how to add your team's tenant IDs:
    https://github.com/netSkope/script-utils/tree/main/flag-cli/src/teams
- Python fallback scripts (`feature_flag.py`, `control_flag.py`):
  https://github.com/netSkope/script-utils/tree/main/flags

## When to look here instead of just running the CLI

- A team key from the Supported Teams table in `SKILL.md` doesn't resolve
  via `flag list` -- the registry may have changed; check `src/teams` in
  the CLI repo for the current definitions.
- A write needs a flag alias that doesn't exist yet for a team -- that's an
  onboarding change to the team's config in `flag-cli/src/teams`, not
  something this skill can add at read/write time.
- The CLI errors in a way that looks like a bug in the tool itself (not a
  usage error) -- reproduce with `--dry-run` first, then check the
  `flag-cli` source/issues before assuming it's a local environment problem.

## Related Confluence doc

The WebUI team's internal usage guide (examples, demo, safety-warning
table) is mirrored from:
https://netskope.atlassian.net/wiki/spaces/ENG/pages/7976224453/WebUI+Flag+Tools+feature_flag+control_flag+and+team+scripts

If that doc and the CLI's own `--help` / README disagree, the CLI's own
output wins -- the Confluence page can lag behind CLI releases.
