# CI run locally

Written by `ci-local.py --record`: one line per local run of the GitHub CI (green or red, with what it
did not cover). The PR hook takes a green line whose commit has only content after it as the CI that
GitHub did not start; the person confirms it first ("checked only locally").

- 2026-11-22 · `226284982e6f` · green (6 steps run, event pull_request); not run: 2 setup steps; not covered: check.yml / check › actions/setup-node@v4 (the context needs is not available locally); check.yml / check › Swatinem/rust-cache@v2 (the context needs is not available locally)
- 2026-11-24 · `e3e5b1b8cb2e` · green (7 steps run, event pull_request); not run: 2 setup steps; not covered: check.yml / check › actions/setup-node@v4 (the context needs is not available locally); check.yml / check › Swatinem/rust-cache@v2 (the context needs is not available locally); check.yml / check › Front (E7) - front.py run full (the context needs is not available locally)
