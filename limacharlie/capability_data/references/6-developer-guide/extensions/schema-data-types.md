# Schema & Data Types

The schema describes an extension's configuration and its actions. It is what the web app renders a user interface from — and it is also a contract that LimaCharlie enforces before your extension is called.

## The Schema Is Enforced

It is tempting to treat the schema as a hint for the UI. It is not. For every incoming request, the platform:

1. **Fills in defaults.** Any parameter with a `default_value` that was not supplied is added to the request.
2. **Checks `requirements`.** A request that does not satisfy them is rejected.
3. **Rejects unknown parameters.** A field the action does not declare is an error, not something quietly ignored.
4. **Type-checks every value** against its `data_type`.
5. **Resolves secrets.** `secret` parameters are replaced with the referenced secret's value.

Only then is your extension called. A request that fails any of these never reaches your code, and the caller gets an error — which is also filed against the organization as an org error.

This is the answer to most cases of "my extension is not being called." Check the schema before you check the handler; the [troubleshooting table](runtime-contract.md#troubleshooting) lists the exact messages.

### Configuration Is Treated Differently

The configuration attached to requests and events goes through a similar but *not* identical pass. The differences matter:

| | Request parameters | Configuration |
| --- | --- | --- |
| Defaults applied | Yes | No |
| `requirements` checked | Yes | No |
| Unknown keys | Rejected with an error | **Silently dropped** before your extension sees them |
| Types checked | Yes | Yes |
| Secrets resolved | Yes | Yes |

The silent drop is the one to watch: removing a field from your config schema does not just hide it, it strips any stored value for that field out of the configuration your extension receives, with no error anywhere. Keep a field in the schema until you are sure nothing depends on it.

!!! warning "Validation is top-level only"
    The platform validates the top level of a request or config. For a field whose `data_type` is `object` or `record`, it checks only that the value *is* an object — the nested `fields`, their types, and any nested `requirements` are **not** enforced.

    Nested structure is a UI description, not a guarantee. Validate the contents of nested objects in your own handler, and never rely on nested schema as a security control.

## Schema Element Fields

Each field in a schema is a `SchemaElement`:

| Field | Type | Description |
| --- | --- | --- |
| `label` | string | Human-readable label for the field |
| `description` | string | Description of the field, shown as a tooltip |
| `placeholder` | string | Placeholder text to display |
| `data_type` | string | One of the data types listed below |
| `is_list` | bool | Whether this field accepts a list of items |
| `display_index` | int | Controls the display order in the UI. Starts at **1** |
| `default_value` | any | Default value, applied by the platform when the field is absent |
| `required` | bool | Marks the field required in the UI. Complements the schema-level `requirements` |
| `object` | object | If `data_type` is `object` or `record`, the nested schema definition |
| `enum_values` | list | If `data_type` is `enum`, the list of possible values |
| `complex_enum_values` | list | If `data_type` is `complex_enum`, objects with `label`, `value`, `category_key` and `reference_link` |
| `filter` | object | UI-side input constraints (see below) |

!!! note "`display_index` starts at 1"
    A `display_index` of `0` is indistinguishable from an unset value once the schema is serialized, and fields without one sort last. Number your fields from 1.

### Requirements

`requirements` is a list of field-name sets. **Every set must be satisfied, and a set is satisfied by any one of its members** — an AND of ORs.

```text
[["denominator"], ["numerator"]]            -> denominator AND numerator
[["denominator"], ["numerator", "default"]] -> denominator AND (numerator OR default)
```

A field with a `default_value` is always present by the time requirements are checked, because defaults are applied first.

### Filters

`filter` constrains what the UI will let a user enter:

- `min` and `max` — for `integer`, `time` and `duration`
- `whitelist` and `blacklist` — for `event_name` and `string`
- `valid_re` and `invalid_re` — regular expressions, for `string`
- `platforms` — for `sid` and `platform`

!!! warning "Filters are not enforced by the platform"
    Filters shape the form the user sees. They are **not** checked server-side, and they are not applied at all to requests arriving from a D&R rule, the API, the CLI, or another extension. A value outside a filter's range reaches your handler normally.

    Treat filters as a convenience for users, and validate anything you actually depend on inside your handler.

## Primitives

| Name | Description |
| --- | --- |
| `string` | Free-form text input |
| `integer` | Numeric integer value |
| `bool` | Boolean true/false toggle |
| `enum` | Single selection from a list. Requires `enum_values` |
| `complex_enum` | Selection with categories, labels and reference links. Requires `complex_enum_values` |
| `sid` | Sensor ID, picked from your organization's sensors. Must be a UUID |
| `oid` | Organization ID. Must be a UUID |
| `platform` | Platform selector |
| `architecture` | Architecture selector |
| `sensor_selector` | Sensor selector expression |
| `tag` | Sensor tag selector |
| `duration` | Duration in milliseconds |
| `time` | Timestamp in milliseconds since epoch |
| `url` | URL input. Must contain `://` |
| `domain` | Domain name input |
| `yara_rule_name` | Selector from your organization's YARA rules |
| `secret` | Reference to an entry in your organization's secrets manager |

### Secrets

`secret` is the mechanism for handling third-party credentials, and it is worth understanding properly: it is not just a picker.

The user selects a secret from their organization's secrets manager, and what is stored is only a *reference*, of the form `hive://secret/<secret-name>`. When a request or configuration carrying that reference reaches the platform, the reference is **replaced with the secret's actual value** before it is forwarded to your extension. Your handler receives the plaintext credential; the credential is never stored by, or visible to, your extension outside of that call.

Substitution is triggered by the `hive://secret/` prefix, not by the field's type. A `secret` field holding anything else is passed through unchanged, so a caller can supply a literal value — do not assume a `secret` parameter always arrived by reference.

This means an extension can integrate a credentialed third-party API without ever asking users to paste a key into extension-specific storage, and without holding long-lived customer credentials of its own. Prefer it over a `string` field for anything sensitive.

Secret resolution happens in the platform, so it does not happen under test. See [Testing](testing.md#what-the-simulator-does-not-cover).

## Code Blocks

| Name | Description |
| --- | --- |
| `json` | JSON editor. The value must parse as JSON |
| `yaml` | YAML editor. The value must parse as YAML |
| `yara_rule` | YARA rule editor |
| `code` | Generic code. Accepted as a string, but see the caveat below |

!!! note
    Code blocks do not support `is_list`. To accept a set of them, wrap them in a `record` (see below).

    `code` is accepted by the platform, but the web app has no dedicated editor for it and renders it as a single-line text input. For a multi-line editing experience today, use `json`, `yaml` or `yara_rule`.

    YARA rule UI support is limited.

## Objects and Records

Objects and records provide structured, nested data. Objects group related fields; records define key-value collections where the keys are user-specified. Remember that the platform does not validate inside either.

### Single Objects

Plain objects allow for nested fields, displayed as though flattened, with the parent's description providing context.

```json
{
  "my_config": {
    "data_type": "object",
    "is_list": false,
    "description": "Configuration group",
    "object": {
      "fields": {
        "field_a": { "data_type": "string", "description": "..." },
        "field_b": { "data_type": "integer", "description": "..." }
      },
      "requirements": null
    }
  }
}
```

### Lists of Objects

Setting `is_list` on an object turns it into a table.

```json
{
  "my_table": {
    "data_type": "object",
    "is_list": true,
    "description": "A table of entries",
    "object": {
      "fields": {
        "name": { "data_type": "string", "description": "Entry name" },
        "value": { "data_type": "string", "description": "Entry value" }
      },
      "requirements": null
    }
  }
}
```

### Records

Records define key-value collections where each entry has a user-specified key and a structured value. The `key` field names and types the key. Optional `element_name` and `element_desc` label each entry in the UI.

```json
{
  "my_records": {
    "data_type": "record",
    "is_list": true,
    "description": "A set of named configurations",
    "object": {
      "key": {
        "name": "config_name",
        "data_type": "string"
      },
      "element_name": "configuration",
      "element_desc": "A named configuration entry",
      "fields": {
        "enabled": { "data_type": "bool", "description": "Whether this config is active" },
        "threshold": { "data_type": "integer", "description": "Alert threshold" }
      },
      "requirements": null
    }
  }
}
```

## Unsupported Data Types

Two values are defined by the SDKs and rendered by the web app, but are **not** recognised by the platform's validator. A top-level field declared with either one causes the whole request or config to be rejected with `unknown datatype` as soon as a value is supplied:

| Name | Use instead |
| --- | --- |
| `text` | `string`, or `json` / `yaml` when a multi-line editor is wanted |
| `event_name` | `string`, with a `whitelist` filter to guide the UI |

Because validation does not descend into nested structures, these types are only a problem at the top level of a request's parameters or of the configuration. Nested inside an `object` or `record` they pass through untouched.

## Language References

The authoritative type definitions live in the SDKs:

- Go — [`common/config_schema.go`](https://github.com/refractionPOINT/lc-extension/blob/master/common/config_schema.go) and [`common/request_schema.go`](https://github.com/refractionPOINT/lc-extension/blob/master/common/request_schema.go)
- Python — [`lcextension/schema.py`](https://github.com/refractionPOINT/lc-extension/blob/master/python/lcextension/schema.py)

!!! note "Python schema differences"
    The Python SDK's schema support trails the Go SDK in a few places. `SchemaElement` has no `complex_enum_values`, `RequestSchema` has no `messages`, and `SchemaObject` serializes its record element name as `list_element_name` rather than the `element_name` the web app reads — so record labels set from Python do not appear. Use Go where these matter.
