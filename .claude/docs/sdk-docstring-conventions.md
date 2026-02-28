# SDK Docstring Conventions

Rules for docstrings in `limacharlie/sdk/`. Use this as a checklist during code review.

## Format

Google style. Every public method and class must have a docstring.

## Required Sections

| Section | When required |
|---------|--------------|
| Summary line | Always |
| `Args:` | Method takes parameters (excluding `self`) |
| `Returns:` | Method returns a value (not `None`) |
| `Yields:` | Method is a generator (uses `yield`) — use *instead of* `Returns:` |
| `Raises:` | Method raises an exception that callers should handle (auth errors, validation, not-found, etc.) |

## Style Rules

1. **Summary line**: imperative mood, one sentence, no trailing period when single line.
2. **Args**: one line per param — `name: Description.` (sentence case, ends with period).
3. **Returns / Yields**: `type: Description.` Keep it brief; mention key fields for dicts.
4. **Raises**: `ExceptionType: When it is raised.`
5. **Blank line** between summary and first section, and between sections.
6. **Type info in signatures, not docstrings** — the codebase uses type annotations; don't duplicate types in `Args:` descriptions.
7. **No `Returns:` for trivial wrappers** that clearly return "API response dict" — a one-liner docstring like `"""List all X."""` is fine if the return type annotation is `dict[str, Any]` and there is nothing surprising in the response shape.

## Canonical Examples

### Standard CRUD method

```python
def create(self, name: str, description: str = "") -> dict[str, Any]:
    """Create a new resource.

    Args:
        name: Human-readable name.
        description: Optional long description.

    Returns:
        dict: API response containing the created resource.
    """
```

### Method that returns None

```python
def delete(self, name: str) -> None:
    """Delete a resource by name.

    Args:
        name: Resource name.
    """
```

### Generator

```python
def get_events(self, start: int, end: int) -> Generator[dict[str, Any], None, None]:
    """Get historical events for this sensor.

    Args:
        start: Start time (unix seconds).
        end: End time (unix seconds).

    Yields:
        dict: Event records with ``routing`` and ``event`` keys.
    """
```

### Method that raises

```python
def download_binary(kind: str, platform: str, arch: str) -> bytes:
    """Download a sensor installer or adapter binary.

    Args:
        kind: ``'sensor'`` or ``'adapter'``.
        platform: Platform name (e.g. ``'linux'``, ``'windows'``).
        arch: Architecture (e.g. ``'64'``, ``'arm64'``).

    Returns:
        bytes: Raw binary content.

    Raises:
        ValueError: If the (platform, arch) combination is not valid.
        RuntimeError: If the download fails.
    """
```

### Simple one-liner (acceptable for trivial getters)

```python
def get_info(self) -> dict[str, Any]:
    """Get organization details."""
```

## Anti-patterns

- Duplicating type annotations inside `Args:` descriptions (e.g., `name (str): ...`).
- Writing `Returns: dict` without saying what's in it when the shape is non-obvious.
- Using `Returns:` on a generator — use `Yields:` instead.
- Omitting `Args:` when the method has parameters beyond `self`.
- Adding docstrings to private methods (`_foo`) — not required.
