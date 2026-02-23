[Documentation](../README.md) > [CLI](README.md) > Other Commands

# Other Commands

Miscellaneous commands: ARL resolution, USP validation, health checks, jobs, schema introspection, shell completion, and help/discovery.

## arl

```bash
limacharlie arl get --arl 'lcr://api/...'      # Resolve an ARL
```

## usp

```bash
limacharlie usp validate                       # Test USP adapter parsing
```

## spotcheck

```bash
limacharlie spotcheck run                      # Quick health check
```

## job

```bash
limacharlie job list
limacharlie job get --id JOB_ID
```

## schema

```bash
limacharlie schema dr create                   # JSON schema for a command
```

## completion

```bash
limacharlie completion bash                    # Shell completion for bash
limacharlie completion zsh                     # Shell completion for zsh
limacharlie completion fish                    # Shell completion for fish
```

## help & discover

```bash
# List all commands grouped by use-case
limacharlie discover
limacharlie discover --profile detection_engineering
limacharlie discover --profile incident_response

# Concept guides
limacharlie help d&r-rules
limacharlie help hive
limacharlie help lcql

# Quick-reference cheat sheets
limacharlie cheatsheet common-operations
limacharlie cheatsheet detection-engineering
limacharlie cheatsheet incident-response

# Detailed explanation of any command
limacharlie dr create --ai-help
```

## See Also

- [CLI Overview](README.md) — Global options and output formats
- [Getting Started](../getting-started.md) — Installation and first steps
