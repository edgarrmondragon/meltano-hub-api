set dotenv-load

port := "8000"
py := "3.14"
ref := "main"

# Update all dependencies and run all tests
build: update pre-commit typing coverage

# Re-build the plugin database
build-db $ONLY_GROUP="build":
    uv run --python={{py}} python -I build.py --git-ref={{ref}} --exit-zero

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
    uvx --python={{py}} prek autoupdate --cooldown-days=7

# Refresh uv.lock
[group('update')]
lock:
    uv lock --upgrade --exclude-newer=p7d

# Start the API server
serve: build-db
    uv run --python={{py}} --no-dev granian --port={{port}} hub_api.main:app

# Run pre-commit checks with prek
[group('test')]
pre-commit:
    -uvx --python={{py}} prek run --all-files

# Run type checks with mypy and ty
[group('test')]
typing:
    uv run --python={{py}} mypy src tests build.py
    uv run --python={{py}} ty check

# Run tests
[group('test')]
test $ONLY_GROUP="tests": build-db
    uv run --python={{py}} pytest

# Compute test coverage
[group('test')]
coverage $ONLY_GROUP="tests": build-db
    uv run --python={{py}} coverage run -m pytest -v
    uv run --python={{py}} coverage combine --keep
    uv run --python={{py}} coverage report --fail-under=100 --show-missing

# Enforce architecture
[group('test')]
tach:
    -uvx --python={{py}} tach check

# Run OpenAPI checks with Schemathesis
[group('test')]
api host="127.0.0.1": build-db
    uvx --python={{py}} --from=schemathesis st run --checks all --base-url http://{{host}}:{{port}} --experimental=openapi-3.1 http://{{host}}:{{port}}/openapi.json
