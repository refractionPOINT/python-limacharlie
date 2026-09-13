"""Compact search results; raw diagnostic envelopes remain available on request."""
import json
import tempfile
from pathlib import Path

import click

from .. import agent_state


def output_summary(ctx, results, execution):
    """Stream full rows to an artifact and return bounded rows plus final coverage."""
    directory = agent_state.directory() / 'artifacts'
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    rows, row_count, sample_bytes = [], 0, 0
    statistics, aggregations = {}, []
    fields = ('eventsScanned', 'eventsMatched', 'bytesScanned', 'billedEvents',
              'freeEvents', 'batchesCompleted', 'batchesInScope', 'eventsInScope',
              'bytesInScope', 'estimatedPrice')
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', prefix='search-',
                                     suffix='.jsonl', dir=directory, delete=False) as output:
        path = Path(output.name).resolve()
        try:
            for item in results:
                # Keep event rows as returned, including metadata/projection columns.
                if item.get('type') == 'events':
                    for row in item.get('rows') or []:
                        line = json.dumps(row, ensure_ascii=False)
                        output.write(line + '\n')
                        row_count += 1
                        if len(rows) < 20 and sample_bytes + len(line.encode()) <= 6000:
                            rows.append(row)
                            sample_bytes += len(line.encode())
                # Aggregation output is evidence too. Save it without diagnostics.
                for key in ('facets', 'timeseries'):
                    if item.get(key):
                        record = {key: item[key]}
                        output.write(json.dumps(record, ensure_ascii=False) + '\n')
                        if len(json.dumps(aggregations + [record]).encode()) <= 3000:
                            aggregations.append(record)
                stats = item.get('stats') or {}
                cumulative = stats.get('cumulativeStats') or stats
                if any(cumulative.get(k) for k in ('eventsScanned', 'batchesInScope', 'eventsInScope')):
                    statistics = {k: cumulative[k] for k in fields if k in cumulative}
            status = 'complete' if execution.get('complete') is True else 'partial'
        except BaseException:
            # Preserve a valid JSON summary of partial evidence even on failure.
            status = 'error'
            raise
        finally:
            output.flush()
            summary = {
                'status': status,
                'complete': status == 'complete',
                'stop_reason': execution.get('stop_reason', 'unknown'),
                'query': execution.get('query'),
                'requested_window': {'start': execution.get('start'), 'end': execution.get('end')},
                'pages_completed': execution.get('pages_completed', 0),
                'matching_rows_returned': row_count,
                'rows': rows,
                'displayed_rows_complete': len(rows) == row_count,
                'aggregations_preview': aggregations,
                'artifact_path': str(path),
                'artifact_format': 'jsonl: event rows and aggregation records; no API diagnostics',
                'reported_statistics': statistics,
                'continuation': execution.get('continuation'),
                'coverage_note': 'Only completed searches cover the requested query scope. '
                                 'Partial results cannot establish absence. Reported scan statistics '
                                 'do not measure the percentage of wall-clock days covered.',
            }
            click.echo(json.dumps(summary, ensure_ascii=False))
