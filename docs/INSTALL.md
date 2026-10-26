# Installation and development

This checkout is Nexa Code `3.0.0.dev0`. Its runtime dependency is the released [Nexa v3.0.0](https://github.com/Nexa-Language/Nexa/releases/tag/v3.0.0), pinned to `274379606e53c90d2d25774f6bb8984c777d0759`, with `NexaAgent.continue_run`. The repository lockfile uses a sibling editable runtime. Wheel metadata pins the same Git source, and the installation steps below use that explicit source.

## Source installation

Install Python 3.10+, uv, Node.js 20+, and pnpm 10.18.3 using their supported installers. Use a fresh directory for this example:

```bash
mkdir nexa-work
cd nexa-work
mkdir -p Nexa-Facility/.runtime
git clone https://github.com/Nexa-Language/Nexa.git Nexa-Facility/.runtime/nexa-3.0.0
git -C Nexa-Facility/.runtime/nexa-3.0.0 checkout 274379606e53c90d2d25774f6bb8984c777d0759
git clone https://github.com/Nexa-Language/Nexa-Code.git Nexa-Facility/Nexa-Code
cd Nexa-Facility/Nexa-Code
uv sync --locked --all-extras
pnpm --dir ui-ink install --frozen-lockfile
pnpm --dir ui-ink build
```

The application changes described here must be present in your Code checkout. Until this work is published, use the local review checkout in the same layout. `uv.lock` resolves `../.runtime/nexa-3.0.0` from the Code directory; a different layout needs an explicit local source override and a regenerated lockfile.

The `mcp` and `anthropic` extras install optional provider/transport dependencies. Omit an extra when that feature is unused. `uv sync --locked` installs the base host and development checks.

Run from any project, with the Code launcher pointing at this checkout:

```bash
/absolute/Nexa-Code/nexa-cc.sh --cwd /absolute/project
/absolute/Nexa-Code/nexa-cc-engine.sh --cwd /absolute/project --doctor
```

Windows launchers are `nexa-cc.bat` and `nexa-cc-engine.cmd`; they use Node and uv from PATH. The legacy `ui/app.py` entry point launches Ink. The engine is also available as `uv run --project /absolute/Nexa-Code --no-sync nexa-code-engine --cwd /absolute/project` for JSON Lines clients.

For the native terminal, add `--program <source.nx> --environment <environment.json>`; [Open Programs](OPEN_PROGRAMS.md) documents goals, budgets, exact grants and recovery. The configuration below applies to the preserved conversation entry.

## Model configuration

The host selects the workspace before importing Nexa configuration. The runtime loads `.nxs` from that directory and its parents, with the nearest scope taking precedence. Use the runtime's configuration format and secret management. A non-secret example is:

```nexa
config default {
    BASE_URL = "https://api.openai.com/v1"
    MODEL_NAME = {"strong": "your-configured-model", "weak": "your-configured-model"}
}
```

Set the matching provider credential through your existing environment/secret manager. Chat/Responses accept runtime `API_KEY`/`OPENAI_API_KEY`; Anthropic uses `ANTHROPIC_API_KEY`. Keep credential values outside version control. Select the matching protocol with `--provider chat`, `--provider responses`, or `--provider anthropic`; add `--model <configured model>` when overriding the symbolic `strong` model. Live provider requests require valid credentials. A launch and `--doctor` work without a provider request.

`--doctor` reports runtime version/source, Python executable, Node version support, uv/pnpm presence, explicit cwd, definition availability and credential *presence*. Inspect it first when startup fails. Persisted sessions require their original workspace/model/provider/definition digest; after changing those, use a new session or transcript import.

## Engine wheel

The Python wheel includes the host and all authoritative `.nx` definitions. The Ink frontend remains a separately built source-checkout application. Build and install the engine with explicit runtime provenance:

```bash
uv build --wheel
uv venv /absolute/engine-env
uv pip install --python /absolute/engine-env/bin/python 'nexa-lang @ git+https://github.com/Nexa-Language/Nexa.git@274379606e53c90d2d25774f6bb8984c777d0759' 'httpx>=0.28,<1'
uv pip install --python /absolute/engine-env/bin/python --no-deps dist/nexa_code-3.0.0.dev0-py3-none-any.whl
/absolute/engine-env/bin/nexa-code-engine --cwd /absolute/project --doctor
```

Use `Scripts/python.exe` and `Scripts/nexa-code-engine.exe` on Windows. For optional providers, install the explicit Git requirement with `[mcp,anthropic]` extras. A verified locally built Nexa runtime wheel can replace the Git requirement. The PyPI name `nexa-lang` is owned by a different project: keep the explicit source/artifact reference or `--no-deps` workflow.

`scripts/check_wheel.py <code-wheel> --runtime-wheel <runtime-wheel>` creates a fresh isolated environment, installs both actual wheels, asserts their import paths, loads all 50 legacy tools, executes one fixture turn and exercises native check/build/locked replay. `--keep <new-directory>` retains this environment for downstream integration checks.

## Offline and live checks

`uv run pytest -q` disables network sockets and allows Unix sockets for the MCP SDK fixture. `scripts/pty_smoke.py` requires POSIX and a built Ink frontend. It creates a temporary workspace and uses the explicit `--fixture` provider.

Live Web validation is opt-in:

```bash
NEXA_CODE_INTEGRATION=1 uv run pytest -m integration --enable-socket
```

This makes a real external request. Provider and desktop integration checks are separate from the offline suite. The benchmark adapter requires `--run-live --harness-path <checkout>`; `--allow-tools` explicitly enables bypass for each disposable benchmark workspace. Keep credentials in the calling environment. New benchmark results must record the runtime, model, task set and settings used.
