# encoding: utf-8

import fylr_lib_plugin_python3.util as util
import json


def do_search(api_url, access_token, sys_id):
    resp, statuscode = util.post_to_api(
        api_url,
        'search',
        access_token,
        payload=util.dumpjs({
            'search': [
                {
                    'type': 'in',
                    'in': [
                        sys_id
                    ],
                    'fields': [
                        '_system_object_id'
                    ],
                    'bool': 'must'
                }
            ],
            'format': 'long'
        })
    )

    if statuscode == 200:
        try:
            js = json.loads(resp)
            objects = util.get_json_value(js, 'objects')
            if not isinstance(objects, list) or len(objects) < 1:
                return False, {
                    'response': 'no objects in search result'
                }
            return True, objects[0]
        except:
            return False, {
                'response': 'could not parse search response'
            }

    # something went wrong
    error = {
        'url': api_url + '/search',
        'statuscode': statuscode,
    }
    error_resp = None
    try:
        error_resp = json.loads(resp)
    except:
        error_resp = resp
    error['response'] = error_resp

    return False, error
