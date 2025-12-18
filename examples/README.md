# LimaCharlie Python SDK Examples

This directory contains example scripts demonstrating how to use the LimaCharlie Python SDK.

## Available Examples

### Search API

**[demo_search_api.py](demo_search_api.py)** - Comprehensive examples for the Search API

Demonstrates:
- Validating search queries and getting estimated pricing
- Executing searches with automatic pagination
- Exporting results to CSV format
- Exporting results to compressed CSV (gzip)
- Using different time formats (relative, ISO dates, Unix timestamps)
- Advanced search configurations
- Custom result flattening for CSV export

**Usage:**
```bash
# Run with default credentials
python examples/demo_search_api.py

# Or use specific credentials
LC_OID="your-oid" LC_API_KEY="your-key" python examples/demo_search_api.py
```

## Common Patterns

### Authentication

All examples use the Manager class which can authenticate in several ways:

```python
from limacharlie import Manager

# 1. Use default credentials from ~/.limacharlie
man = Manager()

# 2. Use environment variables (LC_OID, LC_API_KEY)
man = Manager()

# 3. Pass credentials explicitly
man = Manager(oid="your-oid", secret_api_key="your-key")

# 4. Use a named environment
man = Manager(environment="production")
```

### Time Formats

The Search API CLI supports user-friendly time formats:

```bash
# Relative times (from now)
limacharlie search-api execute \
  --query "event_type = DETECTION" \
  --start "now-1h" \
  --end "now"

# ISO dates
limacharlie search-api execute \
  --query "event_type = DETECTION" \
  --start "2025-12-30" \
  --end "2025-12-31"

# Unix timestamps
limacharlie search-api execute \
  --query "event_type = DETECTION" \
  --start 1234567890 \
  --end 1234567900
```

## Additional Resources

- [Search API Documentation](../docs/SEARCH_API.md)
- [LimaCharlie Python SDK](https://github.com/refractionPOINT/python-limacharlie)
- [LimaCharlie Documentation](https://docs.limacharlie.io/)
