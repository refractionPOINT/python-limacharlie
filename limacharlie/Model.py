import urllib

from limacharlie import Manager
import yaml
import sys
import json

from .utils import GET
from .utils import POST
from .utils import DELETE

from tabulate import tabulate

# Detect if this is Python 2 or 3
import sys

_IS_PYTHON_2 = False
if sys.version_info[0] < 3:
    _IS_PYTHON_2 = True

if _IS_PYTHON_2:
    from urllib import quote as urlescape
else:
    from urllib.parse import quote as urlescape


def printData(data):
    if isinstance(data, str):
        print(data)
    else:
        print(json.dumps(data, indent=2))


def reportError(msg):
    sys.stderr.write(msg + '\n')
    sys.exit(1)


class Model(object):
    def __init__(self, man, modelName):
        self._modelName = modelName
        self._man = man

    def mget(self, index_key_name, index_key_value):
        return self._man._apiCall('models/%s/model/%s/records' % (self._man._oid, urlescape(self._modelName, safe = '')), GET, queryParams={
            'model_name': self._modelName,
            'index_key_name': index_key_name,
            'index_key_value': index_key_value,
        })

    def get(self, primary_key):
        return self._man._apiCall('models/%s/model/%s/record' % (self._man._oid, urlescape(self._modelName, safe = ''),), GET, queryParams={
            'primary_key': primary_key,
        })

    def delete(self, primary_key):
        return self._man._apiCall('models/%s/model/%s/record' % (self._man._oid, urlescape(self._modelName, safe = ''),), DELETE,
                                  queryParams={
                                      'primary_key': primary_key,
                                  })

    def query(self, start_model_name, start_index_key_name, start_index_key_value, plan=[]):
        # Create the plan parameter list without URL encoding
        plan_params = [('plan', json.dumps(item)) for item in plan]

        # Create the base query parameters
        query_params = {
            'starting_model_name': start_model_name,
            'starting_key_name': start_index_key_name,
            'starting_key_value': start_index_key_value,
        }

        # Combine base query parameters and plan parameters
        combined_query_params = list(query_params.items()) + plan_params

        return self._man._apiCall('models/%s/query' % self._man._oid, GET, queryParams=combined_query_params)

    def add(self, primary_key, fields={}, expiry=None):
        params = {
            'model_name': self._modelName,
            'primary_key': primary_key,
            'fields': json.dumps(fields),
        }
        if expiry is not None:
            params['expiry'] = expiry

        return self._man._apiCall('models/%s/model/%s/record' % (self._man._oid, urlescape(self._modelName, safe = '')), POST,
                                  queryParams=params)

    def list(self, limit=100, show_expiry=False, cursor=""):
        return self._man._apiCall('models/%s/model/%s/records' % (self._man._oid, urlescape(self._modelName, safe = '')), POST, queryParams={
            'model_name': self._modelName,
            'limit': limit,
            'cursor': cursor,
            'show_expiry': 'true' if show_expiry else 'false',
        })

# _do_get Ex command line call: limacharlie model get model-name -pk xyz1234
def _do_get(args, man):
    if args.model_name is None:
        reportError('Model name required')

    if args.primary_key is not None:
        printData(Model(man, args.model_name).get(args.primary_key))
        return

    printData(Model(man, args.model_name).mget(args.index_key_name, args.index_key_value))


# _do_mget Ex: limacharlie model mget model-name -ikn host_name -ikv windows-server-2022-xyz
# _do_mget with table view: limacharlie model mget ping_request -ikn sid -ikv 52b-cd86-46d4-a1a2 -t
def _do_mget(args, man):
    if args.model_name is None:
        reportError('Model name required')

    if args.index_key_name is None or args.index_key_value is None:
        reportError('Index key name and value required')

    data = Model(man, args.model_name).mget(args.index_key_name, args.index_key_value)

    if args.table_view:
        printTableView(data)
    else:
        printData(data)

# _do_list Ex: limacharlie model list model-name
# _do_list with table view: limacharlie model list ping_request -t
def _do_list(args, man):
    if args.model_name is None:
        reportError('Model name required')

    # The CLI limit is not the same as the API limit.
    # If the CLI limit is set, we will just get that one page.
    isAll = args.limit is None
    limit = args.limit if args.limit is not None else 1000

    cursor = ""
    records = {}
    while True:
        data = Model(man, args.model_name).list(limit, True, cursor)
        for k, v in data.get('records', {}).items():
            records[k] = v
        cursor = data.get('cursor', "")
        if not cursor or not isAll:
            break

    if args.table_view:
        printTableView(records)
    else:
        printData(records)

# _do_add EX: limacharlie model add model-name -pk pk-value -d '{"type": "vm-linux-ubuntu", "location": "office-6"}' -e 1722020509
def _do_add(args, man):
    if args.model_name is None:
        reportError('Model name required')

    data = json.loads(args.data)

    printData(Model(man, args.model_name).add(args.primary_key, fields=data, expiry=args.expiry))


# _do_del EX: limacharlie model del model-name -pk test-1234
def _do_del(args, man):
    if args.model_name is None:
        reportError('Model name required')

    printData(Model(man, args.model_name).delete(args.primary_key))


# EX-single hop: limacharlie model query user_event -ikn user_init -ikv user123 -p "yara_scan"
# EX-set valid rels : limacharlie model query user_event -ikn user_init -ikv user123 -p "yara_scan:rel1,rel2" "sensors"
# EX- table print out : limacharlie model query user_event -ikn user_init -ikv user123 -p "yara_scan" "sensors" -t
def _do_query(args, man):
    if args.model_name is None:
        reportError('Model name required')

    if args.index_key_name is None or args.index_key_value is None:
        reportError('Index key name and value required')

    plan = [planStringToDict(p) for p in args.plan] if args.plan else []

    data = Model(man, args.model_name).query(args.model_name, args.index_key_name, args.index_key_value, plan)

    if args.table_view:
        printTableView(data)
    else:
        printData(data)


def printTableView(data):
    if isinstance(data, dict):  # Check if data is a dictionary of objects
        if data:
            first_key = next(iter(data))
            headers = ["PK"] + list(data[first_key].keys())

            # Prepare rows dynamically
            rows = [[key] + list(value.values()) for key, value in data.items()]

            print(tabulate(rows, headers=headers, tablefmt="grid"))
        else:
            print("No data found.")
    else:
        print("Data format is not a dictionary of objects.")


def planStringToDict(plan):
    if plan is None:
        return None

    ret = {}
    components = plan.split(':')
    if len(components) < 1 or len(components) > 2:
        raise Exception(
            'Invalid plan format ("target_model_name:relationship1,relationship2,..." or "target_model_name")'
        )

    # Required value
    ret['target_model_name'] = components[0]

    if len(components) == 2: # we have relatioship values
        ret['only_relationships'] = components[1].split(',')

    return ret


def main(sourceArgs=None):
    import argparse

    actions = {
        'get': _do_get,
        'mget': _do_mget,
        'list': _do_list,
        'add': _do_add,
        'del': _do_del,
        'query': _do_query,
    }

    parser = argparse.ArgumentParser(prog='limacharlie model')
    parser.add_argument('action',
                        type=str,
                        help='the action to take, one of: %s' % (', '.join(actions.keys(), )))

    parser.add_argument('model_name',
                        type=str,
                        help='the model name')

    parser.add_argument('-ikn', '--index-key-name',
                        type=str,
                        required=False,
                        dest='index_key_name',
                        default=None,
                        help='the name of the index key')
    parser.add_argument('-ikv', '--index-key-value',
                        type=str,
                        required=False,
                        dest='index_key_value',
                        default=None,
                        help='the value of the index key')
    parser.add_argument('-pk', '--primary-key',
                        type=str,
                        required=False,
                        dest='primary_key',
                        default=None,
                        help='the primary key')
    parser.add_argument('-p', '--plan',
                        type=str,
                        required=False,
                        dest='plan',
                        default=None,
                        nargs='*',
                        help='the query plan')
    parser.add_argument('-d', '--data',
                        type=str,
                        required=False,
                        dest='data',
                        default=None,
                        help='a JSON object to use as record data')
    parser.add_argument('-e', '--expiry',
                        type=int,
                        required=False,
                        dest='expiry',
                        default=None,
                        help='the expiry time as epoch (Unix timestamp)')
    parser.add_argument('-l', '--limit',
                        type=int,
                        required=False,
                        dest='limit',
                        default=None,
                        help='the limit')
    parser.add_argument('-t', '--table-view',
                        action='store_true',
                        required=False,
                        dest='table_view',
                        help='display the data in a table view')

    args = parser.parse_args(sourceArgs)

    man = Manager(None, None)
    actions[args.action.lower()](args, man)


if '__main__' == __name__:
    main()
