# hermes-HeadlessX

A Hermes Agent plugin that implements `web.extract_backend` with
[HeadlessX](https://github.com/saifyxpro/HeadlessX).

The provider sends each URL to HeadlessX's browser-backed markdown endpoint
and returns the standard Hermes `web_extract` result shape. It is extract-only;
keep `web.search_backend` configured separately.

## Requirements

- Hermes Agent with web provider plugin support
- A running HeadlessX instance
- A HeadlessX API key created in the dashboard

The plugin is an API client; it does not launch HeadlessX itself. For a local
self-hosted runtime, install and initialize the official CLI:

```bash
npm install -g @headlessx-cli/core
headlessx init --mode self-host --yes
headlessx status
```

After initialization, use `headlessx start`, `headlessx stop`, and
`headlessx restart` to manage the service. A connection-refused error means
the API configured by `HEADLESSX_API_URL` is not running.

## Install

```bash
hermes plugins install borgius/hermes-HeadlessX --enable
```

For local development, link the repository into Hermes:

```bash
mkdir -p ~/.hermes/plugins/web
ln -s /opt/apps/hermes-HeadlessX ~/.hermes/plugins/web/headlessx
hermes plugins enable web/headlessx
```

## Configure

Set these values in `~/.hermes/.env`:

```dotenv
HEADLESSX_API_URL=http://127.0.0.1:38473
HEADLESSX_API_KEY=hx_your_key
```

`HX_API_URL` and `HX_API_KEY`, used by the HeadlessX CLI, are also accepted.
The default API URL is `http://127.0.0.1:38473`.

Then select the provider in `~/.hermes/config.yaml`:

```yaml
web:
  extract_backend: headlessx
```

## Verify

```bash
hermes -t web -z \
  'Use web_extract on https://example.com and report the page title.'
```

## Development

Run the tests with Hermes' Python environment:

```bash
~/.hermes/hermes-agent/venv/bin/python -m pytest -q
```

## Security

Hermes performs its normal private-network URL checks before invoking the
provider. The plugin also honors Hermes website access policy before each
request and after any final URL returned by HeadlessX.
