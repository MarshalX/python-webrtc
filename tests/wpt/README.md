# web-platform-tests

Runs the WebRTC tests of [web-platform-tests](https://github.com/web-platform-tests/wpt) unmodified against python-webrtc.
Each test file is evaluated in [PythonMonkey](https://github.com/Distributive-Network/PythonMonkey), where `shim.js`
exposes the library as the browser WebRTC API.

## Setup

The suite expects a WPT checkout in `wpt/` at the root of the repository. Only a few directories are needed:

```sh
git clone --depth 1 --filter=blob:none --sparse --branch epochs/daily https://github.com/web-platform-tests/wpt.git
git -C wpt sparse-checkout set --no-cone '/webrtc*/' '/resources/' '/common/' '/interfaces/' \
    '/mediacapture-streams/permission-helper.js'
uv sync --group wpt
```

Without the checkout or PythonMonkey the tests are skipped.

## Running

```sh
uv run pytest tests/wpt -n auto                  # compare every case with expectations.json
uv run python -m tests.wpt run <case>            # print every result of a case
uv run python -m tests.wpt update [<case> ...]   # record current results as expected
uv run python -m tests.wpt update --repeat 5     # the same, running each case 5 times to find flaky tests
```

A case is a path under `wpt/` plus its variant, like `webrtc/RTCPeerConnection-addTransceiver.https.html?rest`.

## Expectations

`expectations.json` lists every result that isn't a pass. A case fails when a result differs from its expectation in
either direction, so after implementing something, run `update` for the affected cases and commit the new
expectations along with the change.

Files that can't apply to a Python library (workers, DOM elements, identity providers) are listed under `skip` with
the reason. Flaky results are lists of allowed statuses; `update --repeat 5` finds them by running every case
several times.

## The shim

`shim.js` must stay a binding: it maps names, converts types, keeps object identity and maps errors to the right
exception types, the way WebIDL bindings do in a browser. Behavior belongs to the library. If a test only passes by
adding logic to the shim, the library is still missing that behavior.

`polyfills.js`, evaluated before it, adds the platform globals the shell lacks (like `TextEncoder`, `Blob` or
`performance`), as far as the tests use them.

Every case runs in its own process, because PythonMonkey has a single global object and WPT helpers declare
top-level constants.
