# Release surface

This confidential fork keeps only the tagged `release-provenance.yml` release
workflow active. It builds the browser distribution, emits the public
`/release.json` and `/.well-known/adverserial-build.json` identity manifests,
attests the release archive, and uploads immutable release assets.

The upstream Docker, Docker Hub, Helm-dispatch, PyPI, and automatic generic
release workflows are retained as `.disabled` files for audit history but do
not run in this repository. They publish broad upstream artifacts and are not
part of the confidential chat deployment path.

The provenance workflow is tag-only and pins every credentialed GitHub Action
to an immutable commit. A deployment should reference a tagged release archive
or its published digest, then compare the served identity manifest with that
release before treating the browser build as the expected confidential client.
