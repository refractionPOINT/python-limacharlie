import argparse
from . import Manager
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
import uuid

def massUpgrade():
    parser=argparse.ArgumentParser(prog='limacharlie mass-upgrade')
    # A sensor selector to apply the version only to these.
    parser.add_argument('--selector',
                            default=None,
                            type=str,
                            dest='sensor_selector',
                            help='sensor selector expression.')
    # A repeated list of OIDs to apply the version to.
    parser.add_argument('--orgs',
                            nargs='+',
                            default=[],
                            dest='orgs',
                            help='a list of OIDs to apply the new version to.')
    # The version to apply.
    parser.add_argument('--version',
                            type=str,
                            required=True,
                            dest='version',
                            help='the version to apply, "latest" or "stable" or "-" or a specific version (like 4.30.0).')
    args=parser.parse_args(sys.argv[2:])
    if args.version.lower() not in ['latest', 'stable', '-'] and args.sensor_selector:
        print('Version must be either "latest" or "stable" (or "-" if a sensor selector is specified, or specific version like 4.30.0 if a sensor selector is not specified).')
        return
    if args.version == '-' and not args.sensor_selector:
        print('Version "-" can only be used with a sensor selector.')
        return

    # If we have an org with a "-" value it means we should read the STDIN for the list.
    # If we have an org with a non-"-" value it AND not a UUID, it means we should read the file at that path.
    # Merge the OIDs found in the file or STDIN into the list.
    orgs=[]
    for oid in args.orgs:
        if oid == '-':
            orgs += sys.stdin.read().strip().split('\n')
        else:
            try:
                uuid.UUID(oid)
            except Exception as e:
                with open(oid, 'r') as f:
                    orgs += f.read().strip().split('\n')
            else:
                orgs.append(oid)
    if not orgs:
        print('No orgs specified.')
        return
    for oid in orgs:
        try:
            uuid.UUID(oid)
        except Exception as e:
            print(f'Invalid org ID: {oid}')
            return

    isFallback=args.version.lower() == 'stable'
    if isFallback:
        print('Applying stable version.')
    else:
        print(f'Applying {args.version.lower()} version.')

    for oid in orgs:
        print(f'Processing org {oid}')
        _man=Manager(oid=oid)
        # If a selector was specified, we will apply via tags. Otherwise, we will apply to the whole org.
        if args.sensor_selector:
            print(f'Applying to sensors matching selector: {args.sensor_selector}')
            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = {executor.submit(_doSensorTag, sensor, isFallback, args.version == '-'): sensor for sensor in _man.sensors(selector=args.sensor_selector)}
                for future in as_completed(futures):
                    sensor = futures[future]
                    try:
                        result = future.result()
                    except Exception as e:
                        print(f"Task {sensor.sid} generated an exception: {e}")
        else:
            print(f'Applying to entire org {oid}')
            if args.version.lower() in ['latest', 'stable']:
                _man.setSensorVersion(isFallbackVersion=isFallback)
            else:
                _man.setSensorVersion(specificVersion=args.version)

def _doSensorTag(sensor, isFallback, isRemove=False):
    print(f'Applying to sensor {sensor.sid}')
    if isRemove:
        sensor.untag('lc:stable')
        sensor.untag('lc:latest')
    else:
        sensor.tag('lc:stable' if isFallback else 'lc:latest')
        sensor.untag('lc:stable' if not isFallback else 'lc:latest')