# encoding: utf-8

import json
import fylr_lib_plugin_python3.util as util
import sequence


def __search_pool_ids(api_url, access_token, pool_ids):
    if not pool_ids:
        return []

    response, statuscode = util.post_to_api(
        api_url,
        'search',
        access_token,
        payload=util.dumpjs(
            {
                'search': [
                    {
                        'bool': 'must',
                        'fields': [
                            'pool._id',
                        ],
                        'in': list(pool_ids),
                        'type': 'in',
                    }
                ],
                'limit': 1000,
                'type': 'pool',
            }
        ),
        log_in_tmp_file=True,
    )

    if statuscode != 200:
        # parse the response, if it is an api error return it to fylr
        hint = 'search pool ids'
        util.return_if_api_error(response, hint)

        # not an api error, some other response
        util.return_error_response_with_parameters(
            error_code=f'error.{sequence.PLUGIN_NAME}',
            error_msg=f'{hint}: unexpected response',
            parameters={
                'response': response,
                'statuscode': statuscode,
            },
        )

    pools = util.get_json_value(json.loads(response), 'objects')
    if isinstance(pools, list):
        return pools

    return []


def load_pool_data(
    api_url: str,
    access_token: str,
    pool_ids: str,
) -> tuple[
    dict,  # pool info
    dict,  # inherited custom data
    bool,  # all pools have been found?
]:
    pool_info = {}
    inherited_custom_data = {}

    # step 1: load all pools by given ids and collect their info, as well as all ids of parent pools

    pool_paths = {}
    parent_pool_ids = set()

    pools = __search_pool_ids(api_url, access_token, pool_ids)
    for pool in pools:

        id = util.get_json_value(pool, 'pool._id')
        if not isinstance(id, int):
            continue

        pool_info[id] = pool

        custom_data = util.get_json_value(pool, 'pool.custom_data.sequence_plugin')

        pool_paths[id] = []
        inherited_custom_data[id] = {}

        path = util.get_json_value(pool, '_path')
        if not isinstance(path, list):
            continue

        for p in path:
            pool_id = util.get_json_value(p, 'pool._id')
            if not isinstance(pool_id, int):
                continue

            p_obj = {
                'id': pool_id,
            }

            if pool_id == id:
                p_obj['custom_data'] = custom_data
            else:
                parent_pool_ids.add(pool_id)

            pool_paths[id].append(p_obj)

    if len(pool_info) < len(pool_ids):
        # not all pools for the ids were found
        return pool_info, inherited_custom_data, False

    # step 2: load all pools by the collect parent pool ids
    # assume all pools were found
    all_pools_found = True

    parent_pools = __search_pool_ids(api_url, access_token, parent_pool_ids)
    for pool in parent_pools:

        id = util.get_json_value(pool, 'pool._id')
        if not isinstance(id, int):
            all_pools_found = False
            continue

        pool_info[id] = pool

        custom_data = util.get_json_value(pool, 'pool.custom_data.sequence_plugin')
        if not isinstance(custom_data, list):
            continue
        if len(custom_data) < 1:
            continue

        for pool_id in pool_paths:
            for i in range(len(pool_paths[pool_id])):
                path_pool_id = util.get_json_value(pool_paths[pool_id][i], 'id')
                if id != path_pool_id:
                    continue

                pool_paths[pool_id][i]['custom_data'] = custom_data

    # inherit custom_data from root pool to the current pool
    for pool_id in inherited_custom_data:
        if pool_id not in pool_paths:
            continue

        for p in pool_paths[pool_id]:
            cd = util.get_json_value(p, 'custom_data')
            if not isinstance(cd, list):
                continue
            if len(cd) < 1:
                continue

            for e in cd:
                objecttype = util.get_json_value(e, 'objecttype')
                if not isinstance(objecttype, str):
                    continue
                if objecttype == '':
                    continue
                if not objecttype in inherited_custom_data[pool_id]:
                    inherited_custom_data[pool_id][objecttype] = {}

                field = util.get_json_value(e, 'field')
                if not isinstance(field, str):
                    continue
                if field == '':
                    continue

                if field.startswith(f'{objecttype}.'):
                    field = field[len(objecttype) + 1 :]

                template = util.get_json_value(e, 'template')
                if not isinstance(template, str):
                    continue
                if template == '':
                    continue

                start_offset = 0
                try:
                    start_offset = int(util.get_json_value(e, 'start_offset'))
                except:
                    start_offset = 0
                if start_offset < 0:
                    start_offset = 0

                only_insert = util.get_json_value(e, 'only_insert')
                if not isinstance(only_insert, bool):
                    only_insert = False

                inherited_custom_data[pool_id][objecttype][field] = template
                inherited_custom_data[pool_id][objecttype][
                    f'{field}:start_offset'
                ] = start_offset
                inherited_custom_data[pool_id][objecttype][
                    f'{field}:only_insert'
                ] = only_insert

    return pool_info, inherited_custom_data, all_pools_found
