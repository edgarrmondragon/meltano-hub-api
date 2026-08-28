set dotenv-load

port := "8000"
ref := "main"

# Update all dependencies and run all tests
build: update pre-commit typing coverage

# Re-build the plugin database
build-db $ONLY_GROUP="build":
    uv run python -I build.py --git-ref={{ref}} --exit-zero

# Update all dependencies
[group('update')]
update: gha-update pre-commit-autoupdate lock

# Upgrade GitHub actions
[group('update')]
gha-update:
    pinact run --update --min-age=7

# Upgrade pre-commit hooks
[group('update')]
pre-commit-autoupdate:
    uvx prek autoupdate --cooldown-days=7

# Refresh uv.lock
[group('update')]
lock:
    uv lock --upgrade --exclude-newer=p7d

# Start the API server
serve: build-db
    uv run --no-dev granian --port={{port}} hub_api.main:app

# Run pre-commit checks with prek
[group('test')]
pre-commit:
    -uvx prek run --all-files

# Run type checks with mypy and ty
[group('test')]
typing:
    uv run mypy src tests build.py
    uv run ty check

# Run tests
[group('test')]
test $ONLY_GROUP="tests": build-db
    uv run pytest

# Compute test coverage
[group('test')]
coverage $ONLY_GROUP="tests": build-db
    uv run coverage run -m pytest -v
    uv run coverage combine --keep
    uv run coverage report --fail-under=100 --show-missing

# Enforce architecture
[group('test')]
tach:
    -uvx tach check

# Run OpenAPI checks with Schemathesis
[group('test')]
api host="127.0.0.1": build-db
    uvx --from=schemathesis st run http://{{host}}:{{port}}/openapi.json
