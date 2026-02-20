# Copyright 2024 Refraction Point, Inc.
# Licensed under the Apache License, Version 2.0

"""
USP (Universal Sensor Protocol) CLI module for LimaCharlie.

Provides commands for validating USP adapter configurations before deployment.
"""

from limacharlie import Manager
import yaml
import json
import sys


def printData(data):
    """
    Print data in a human-readable format.

    Parameters:
        data: The data to print (str, dict, or list).

    Return:
        None
    """
    if isinstance(data, str):
        print(data)
    else:
        print(yaml.safe_dump(data, default_flow_style=False))


def reportError(msg):
    """
    Report an error message to stderr and exit with code 1.

    Parameters:
        msg (str): The error message to display.

    Return:
        None (exits the program)
    """
    sys.stderr.write(msg + '\n')
    sys.exit(1)


def _load_file_content(file_path, as_json=False):
    """
    Load content from a file.

    Parameters:
        file_path (str): Path to the file to load.
        as_json (bool): If True, parse as JSON. If False, return raw text.

    Return:
        The file content (parsed JSON or raw string).
    """
    try:
        with open(file_path, 'rb') as f:
            content = f.read().decode('utf-8')
            if as_json:
                return json.loads(content)
            return content
    except FileNotFoundError:
        reportError(f'File not found: {file_path}')
    except json.JSONDecodeError as e:
        reportError(f'Invalid JSON in file {file_path}: {e}')
    except Exception as e:
        reportError(f'Error reading file {file_path}: {e}')


def _load_mapping(args):
    """
    Load mapping configuration from file or inline argument.

    Parameters:
        args: Parsed arguments containing mapping or mapping_file.

    Return:
        dict: The mapping configuration, or None if not provided.
    """
    if args.mapping_file:
        try:
            with open(args.mapping_file, 'rb') as f:
                content = f.read()
                # Try YAML first (also handles JSON)
                return yaml.safe_load(content)
        except Exception as e:
            reportError(f'Error loading mapping file: {e}')
    elif args.mapping:
        try:
            return json.loads(args.mapping)
        except json.JSONDecodeError as e:
            reportError(f'Invalid JSON in mapping argument: {e}')
    return None


def do_validate(args):
    """
    Validate a USP adapter configuration against sample data.

    Tests parsing rules by sending sample data through the parsing engine
    and returning the parsed events or error messages. This allows verification
    of parsing configurations before deploying adapters to production.

    Parameters:
        args: Parsed arguments containing platform, mapping, and input data.

    Return:
        None (prints validation results to stdout)
    """
    # Platforms with built-in parsers that don't require custom mapping
    builtin_parser_platforms = ['cef', 'wel', 'gcp', 'aws', '1password', 'duo', 'slack']

    # Load mapping configuration
    mapping = _load_mapping(args)
    if mapping is None and args.mappings_file is None:
        # Only require mapping for platforms that need custom parsing rules
        if args.platform not in builtin_parser_platforms:
            reportError(f'Platform "{args.platform}" requires a mapping configuration.\n'
                       f'Use --mapping, --mapping-file, or --mappings-file to provide one.\n'
                       f'Platforms with built-in parsers (no mapping required): {", ".join(builtin_parser_platforms)}')

    # Load mappings array if provided
    mappings = None
    if args.mappings_file:
        mappings = _load_file_content(args.mappings_file, as_json=True)
        if not isinstance(mappings, list):
            reportError('--mappings-file must contain a JSON array of mapping descriptors')

    # Load input data
    text_input = None
    json_input = None

    if args.input_file:
        if args.json_input:
            json_input = _load_file_content(args.input_file, as_json=True)
            if not isinstance(json_input, list):
                reportError('JSON input must be an array of objects')
        else:
            text_input = _load_file_content(args.input_file, as_json=False)
    elif args.input:
        if args.json_input:
            try:
                json_input = json.loads(args.input)
                if not isinstance(json_input, list):
                    reportError('JSON input must be an array of objects')
            except json.JSONDecodeError as e:
                reportError(f'Invalid JSON in input argument: {e}')
        else:
            text_input = args.input

    if text_input is None and json_input is None:
        reportError('Either --input or --input-file is required')

    # Load indexing rules if provided
    indexing = None
    if args.indexing_file:
        indexing = _load_file_content(args.indexing_file, as_json=True)
        if not isinstance(indexing, list):
            reportError('--indexing-file must contain a JSON array of indexing rules')

    # Call the validation API
    man = Manager(None, None)
    try:
        result = man.validateUSP(
            platform=args.platform,
            hostname=args.hostname,
            mapping=mapping,
            mappings=mappings,
            indexing=indexing,
            text_input=text_input,
            json_input=json_input,
        )
    except Exception as e:
        reportError(f'API error: {e}')

    # Format and display results
    errors = result.get('errors', [])
    results = result.get('results', [])

    if errors:
        print('VALIDATION FAILED\n')
        print('Errors:')
        for err in errors:
            print(f'  - {err}')
        print('')
        if results:
            print(f'Partially parsed {len(results)} event(s) before failure.')
        sys.exit(1)
    elif len(results) == 0:
        # No events parsed - this likely indicates misconfigured parsing rules
        print('VALIDATION FAILED\n')
        print('WARNING: No events were parsed from the sample data.\n')
        print('This usually indicates one of the following issues:')
        print('  - The parsing_re regex does not match the input format')
        print('  - The platform type does not match the data format')
        print('  - The sample data is empty or contains only whitespace')
        print('')
        print('Suggestions:')
        print('  - Verify your parsing_re regex matches the sample data')
        print('  - Check that the platform matches your data format (text, json, cef, etc.)')
        print('  - Ensure the sample file contains valid log data')
        sys.exit(1)
    else:
        print('VALIDATION SUCCESSFUL\n')
        print(f'Parsed {len(results)} event(s):\n')

        if args.output_format == 'json':
            print(json.dumps(results, indent=2))
        elif args.output_format == 'yaml':
            print(yaml.safe_dump(results, default_flow_style=False))
        else:
            # Default: summary format
            for i, event in enumerate(results, 1):
                print(f'Event {i}:')
                # Show routing info if present
                routing = event.get('routing', {})
                if routing:
                    hostname = routing.get('hostname', routing.get('this', {}).get('hostname', ''))
                    if hostname:
                        print(f'  hostname: {hostname}')
                # Show event data
                evt = event.get('event', event)
                for key, value in evt.items():
                    if key != 'routing':
                        print(f'  {key}: {value}')
                print('')


def main(sourceArgs=None):
    """
    Main entry point for the USP CLI.

    Parameters:
        sourceArgs (list): Optional list of CLI arguments. If None, uses sys.argv.

    Return:
        None
    """
    import argparse

    actions = {
        'validate': do_validate,
    }

    parser = argparse.ArgumentParser(
        prog='limacharlie usp',
        description='USP (Universal Sensor Protocol) adapter management and validation.'
    )
    parser.add_argument(
        'action',
        type=str,
        help='the action to take, one of: %s' % (', '.join(actions.keys()))
    )

    # Platform selection
    parser.add_argument(
        '-p', '--platform',
        type=str,
        required=False,
        default='text',
        dest='platform',
        choices=['text', 'json', 'cef', 'gcp', 'aws'],
        help='parser platform type (default: text)'
    )

    # Mapping configuration (mutually exclusive options)
    parser.add_argument(
        '-m', '--mapping',
        type=str,
        required=False,
        default=None,
        dest='mapping',
        help='inline JSON mapping configuration'
    )
    parser.add_argument(
        '-f', '--mapping-file',
        type=str,
        required=False,
        default=None,
        dest='mapping_file',
        help='path to YAML/JSON file containing mapping configuration'
    )
    parser.add_argument(
        '--mappings-file',
        type=str,
        required=False,
        default=None,
        dest='mappings_file',
        help='path to JSON file containing array of mapping descriptors (for multi-mapping selection)'
    )

    # Input data
    parser.add_argument(
        '-i', '--input',
        type=str,
        required=False,
        default=None,
        dest='input',
        help='inline sample data to validate (text or JSON depending on --json-input)'
    )
    parser.add_argument(
        '--input-file',
        type=str,
        required=False,
        default=None,
        dest='input_file',
        help='path to file containing sample data to validate'
    )
    parser.add_argument(
        '--json-input',
        action='store_true',
        default=False,
        dest='json_input',
        help='treat input as JSON array instead of newline-separated text'
    )

    # Optional parameters
    parser.add_argument(
        '--hostname',
        type=str,
        required=False,
        default=None,
        dest='hostname',
        help='default hostname for sensors (defaults to "validation-test")'
    )
    parser.add_argument(
        '--indexing-file',
        type=str,
        required=False,
        default=None,
        dest='indexing_file',
        help='path to JSON file containing indexing rules'
    )

    # Output format
    parser.add_argument(
        '-o', '--output-format',
        type=str,
        required=False,
        default='summary',
        dest='output_format',
        choices=['summary', 'json', 'yaml'],
        help='output format for parsed events (default: summary)'
    )

    args = parser.parse_args(sourceArgs)
    actions[args.action.lower()](args)


if '__main__' == __name__:
    main()
