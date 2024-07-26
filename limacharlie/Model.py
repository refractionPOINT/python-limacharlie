import urllib

from limacharlie import Manager
import yaml
import sys
import json

from .utils import GET
from .utils import POST
from .utils import DELETE

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
        return self._man._apiCall('models/%s/model/%s/records' % (self._man._oid, self._modelName), GET, queryParams={
            'model_name': self._modelName,
            'index_key_name': index_key_name,
            'index_key_value': index_key_value,
        })

    def get(self, primary_key):
        return self._man._apiCall('models/%s/model/%s/record' % (self._man._oid, self._modelName,), GET, queryParams={
            'primary_key': primary_key,
        })

    def delete(self, primary_key):
        return self._man._apiCall('models/%s/model/%s/record' % (self._man._oid, self._modelName,), DELETE,
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

        return self._man._apiCall('models/%s/model/%s/record' % (self._man._oid, self._modelName), POST, queryParams=params)


# _do_get Ex command line call: limacharlie model get model-name -pk xyz1234
def _do_get(args, man):
    if args.model_name is None:
        reportError('Model name required')

    if args.primary_key is not None:
        printData(Model(man, args.model_name).get(args.primary_key))
        return

    printData(Model(man, args.model_name).mget(args.index_key_name, args.index_key_value))


# _do_mget Ex: limacharlie model mget model-name -ikn host_name -ikv windows-server-2022-xyz
def _do_mget(args, man):
    if args.model_name is None:
        reportError('Model name required')

    if args.index_key_name is None or args.index_key_value is None:
        reportError('Index key name and value required')

    printData(Model(man, args.model_name).mget(args.index_key_name, args.index_key_value))

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


#_do_query EX: limacharlie model query user_event -ikn user_init -ikv user123 -p "yara_scan:3:rel1,rel2" "sensors" "another_model:2"
#_do_query EX: limacharlie model query user_event -ikn user_init -ikv user123 -p "yara_scan" "sensors"
def _do_query(args, man):
    if args.model_name is None:
        reportError('Model name required')

    if args.index_key_name is None or args.index_key_value is None:
        reportError('Index key name and value required')

    plan = [planStringToDict(p) for p in args.plan] if args.plan else []
    print("plan in do query ", plan)

    printData(Model(man, args.model_name).query(args.model_name, args.index_key_name, args.index_key_value, plan))


def planStringToDict(plan):
    if plan is None:
        return None

    ret = {}
    components = plan.split(':')
    if len(components) < 1:
        raise Exception(
            'Invalid plan format ("target_model_name:hop_limit:relationship1,relationship2,..." or "target_model_name:relationship1,relationship2,..." or "target_model_name")'
        )

    # Required value
    ret['target_model_name'] = components[0]

    if len(components) == 2:
        try:
            ret['hop_limit'] = int(components[1])
        except ValueError:
            ret['only_relationships'] = components[1].split(',')

    if len(components) == 3:
        try:
            ret['hop_limit'] = int(components[1])
        except ValueError:
            raise Exception('Invalid hop limit value, it should be an integer')
        ret['only_relationships'] = components[2].split(',')

    print("this is ret ", ret)
    return ret


def main(sourceArgs=None):
    import argparse

    actions = {
        'get': _do_get,
        'mget': _do_mget,
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

    args = parser.parse_args(sourceArgs)

    man = Manager(None, None)
    actions[args.action.lower()](args, man)


if '__main__' == __name__:
    main()
