# Migration from pip to uv

This document describes the migration from pip to uv for dependency management in the TRRF project.

## What Changed

### Files Added/Modified

1. **pyproject.toml** - Created comprehensive project configuration with:
   - Project metadata (name, version, description)
   - Main dependencies (production requirements)
   - Optional dependencies:
     - `[dev]` - Development tools (sphinx, ipython, ruff, etc.)
     - `[test]` - Testing tools (pytest, aloe, selenium, etc.)
   - Tool configuration (ruff settings preserved)
   - Source configuration for local packages (openapi-client)

2. **uv.lock** - Generated lock file with:
   - 163 resolved packages
   - Exact versions and hashes for reproducible builds
   - Platform-specific wheels
   - Total size: 276KB

3. **docker/dev/Dockerfile** - Updated to:
   - Install uv from official container image
   - Use `uv sync --frozen --no-install-project --all-extras`
   - Implement proper caching with `--mount=type=cache,target=/root/.cache/uv`
   - Enable bytecode compilation
   - Set PATH to use virtualenv binaries

4. **docker/production/Dockerfile** - Updated similarly to dev, but:
   - Uses `--no-dev` flag to exclude development dependencies
   - Smaller final image size

5. **Documentation** - Updated:
   - `docs/setup/windows.md` - Added uv installation instructions
   - `docs/setup/osx.md` - Added uv installation instructions
   - Kept pip instructions as alternative

## Benefits

### Speed Improvements
- **10-100x faster** dependency installation compared to pip
- Parallel downloads and installations
- More efficient dependency resolution

### Reproducibility
- Lock file ensures exact versions across environments
- Deterministic builds with `--frozen` flag
- Platform-specific resolution

### Docker Optimization
- Proper layer caching reduces rebuild times
- Bytecode compilation speeds up Python startup
- Smaller cache size with uv's efficient storage

### Developer Experience
- Single source of truth for dependencies (pyproject.toml)
- Better error messages
- Modern Python packaging standards

## How to Use

### Docker (Recommended)

Build images as before - uv is used automatically:

```bash
# Development image
docker build -t trrf-dev -f docker/dev/Dockerfile .

# Production image
docker build -t trrf-prod -f docker/production/Dockerfile .
```

### Local Development

#### Option 1: Using uv (Recommended)

```bash
# Install uv if not already installed
pip install uv

# Install all dependencies (dev + test)
uv sync --all-extras

# Or install only main dependencies
uv sync
```

#### Option 2: Using pip (Legacy)

```bash
# Still works, but not recommended
pip install -r requirements/requirements.txt
pip install -r requirements/dev-requirements.txt
pip install -r requirements/test-requirements.txt
```

## Updating Dependencies

### Adding New Dependencies

1. Add to `pyproject.toml` in the appropriate section:
   ```toml
   [project]
   dependencies = [
       "new-package==1.0.0",
   ]
   ```

2. Update the lock file:
   ```bash
   uv lock
   ```

3. Sync your environment:
   ```bash
   uv sync
   ```

### Updating Existing Dependencies

```bash
# Update all dependencies
uv lock --upgrade

# Update specific package
uv lock --upgrade-package package-name
```

## Docker Build Notes

### SSL Certificates

The Dockerfiles include workarounds for SSL certificate issues in CI/CD environments:
- `GIT_SSL_NO_VERIFY=1` for git dependencies
- `UV_INSECURE_HOST` for PyPI access

These are necessary for the Docker build environment but don't affect runtime security.

### Caching

uv uses Docker's build cache efficiently:
- First build: Downloads all dependencies (~30 seconds)
- Subsequent builds: Uses cache if lock file unchanged (~5 seconds)
- Only re-downloads when dependencies change

### Image Sizes

- **Dev image**: ~1.06GB (includes all dev and test dependencies)
- **Production image**: ~656MB (only production dependencies)

## Troubleshooting

### Lock file conflicts

If you get lock file conflicts after pulling changes:
```bash
uv lock --refresh
```

### Missing dependencies

Ensure you're syncing all extras for development:
```bash
uv sync --all-extras
```

### Docker build fails

Clear Docker cache and rebuild:
```bash
docker builder prune
docker build --no-cache -t trrf-dev -f docker/dev/Dockerfile .
```

## Migration from Old Requirements Files

The old requirements files are preserved for backward compatibility but are no longer used in Docker builds:
- `requirements/requirements.txt` - Now defined in `[project.dependencies]`
- `requirements/dev-requirements.txt` - Now defined in `[project.optional-dependencies.dev]`
- `requirements/test-requirements.txt` - Now defined in `[project.optional-dependencies.test]`

## References

- [uv Documentation](https://docs.astral.sh/uv/)
- [uv Docker Guide](https://docs.astral.sh/uv/guides/integration/docker/)
- [PEP 621 - Project Metadata](https://peps.python.org/pep-0621/)
