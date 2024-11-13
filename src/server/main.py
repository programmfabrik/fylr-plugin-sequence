# encoding: utf-8


import sys
import time
import fylr_lib_plugin_python3.util as util
import sequence
import search
import json
import pool
import templates


PLUGIN_NAME = 'fylr-plugin-sequence'


if __name__ == '__main__':

    orig_data = json.loads(sys.stdin.read())

    # get the objects from the input data
    objects = util.get_json_value(orig_data, 'objects')
    if not isinstance(objects, list):
        util.return_empty_objects()
    if len(objects) < 1:
        util.return_empty_objects()

    # get the server url
    api_url = util.get_json_value(orig_data, 'info.api_url')
    if api_url is None:
        util.return_error_response('info.api_url missing!')
    api_url += '/api/v1'

    # get a session token
    access_token = util.get_json_value(orig_data, 'info.api_user_access_token')
    if access_token is None:
        util.return_error_response('info.api_user_access_token missing!')

    # load base config for this plugin
    # directly return the original data if there are any configurations missing
    plugin_config_path = f'info.config.plugin.{PLUGIN_NAME}.config'

    # load ordered list of database languages from the base config (api/v1/config/system)
    database_languages = []
    config_languages = util.get_config_from_api(
        api_url=api_url,
        access_token=access_token,
        path='system/config/languages/database',
    )
    if isinstance(config_languages, list):
        for l in config_languages:
            v = util.get_json_value(l, 'value')
            if v is None:
                continue
            if len(v) < 1:
                continue
            database_languages.append(v)
    if len(database_languages) < 1:
        database_languages.append('en-US')

    # sequence objecttype settings
    sequence_objecttype = util.get_json_value(
        orig_data,
        f'{plugin_config_path}.sequence.objecttype',
    )
    if sequence_objecttype is None or len(sequence_objecttype) < 1:
        util.return_empty_objects()

    sequence_ref_field = util.get_json_value(
        orig_data,
        f'{plugin_config_path}.sequence.ref_field',
    )
    if sequence_ref_field is None or len(sequence_ref_field) < 1:
        util.return_empty_objects()

    sequence_num_field = util.get_json_value(
        orig_data,
        f'{plugin_config_path}.sequence.num_field',
    )

    if sequence_num_field is None or len(sequence_num_field) < 1:
        util.return_empty_objects()

    # objecttypes/fields settings
    ot_settings = util.get_json_value(
        orig_data,
        f'{plugin_config_path}.objecttypes.sequence_settings',
    )

    if not isinstance(ot_settings, list):
        util.return_empty_objects()

    objecttype_fields = {}
    for config_entry in ot_settings:
        if not util.get_json_value(config_entry, 'enabled'):
            continue

        objecttype = util.get_json_value(config_entry, 'update_objecttype')
        if not isinstance(objecttype, str):
            continue
        if len(objecttype) < 1:
            continue

        column = util.get_json_value(config_entry, 'update_column')
        if not isinstance(column, str):
            continue
        if column.startswith(f'{objecttype}.'):
            column = column[len(objecttype) + 1 :]
        if len(column) < 1:
            continue

        obj_field = util.get_json_value(config_entry, 'obj_field')
        is_linked_field = False
        if isinstance(obj_field, str):
            parts = obj_field.split('.')
            if len(parts) > 1 and parts[0] == objecttype:
                obj_field = '.'.join(parts[1:])
                if len(parts) > 2:
                    is_linked_field = True
            else:
                obj_field = None

        no_sequence_if_empty_field = (
            util.get_json_value(
                config_entry,
                'no_sequence_if_empty_field',
            )
            == True
        )

        template = util.get_json_value(config_entry, 'template')
        if not isinstance(template, str):
            continue
        if len(template) < 1:
            continue

        start_offset = util.get_json_value(config_entry, 'start_offset')
        if not isinstance(start_offset, int) or start_offset < 1:
            start_offset = 0

        only_insert = util.get_json_value(config_entry, 'only_insert') == True

        if not objecttype in objecttype_fields:
            objecttype_fields[objecttype] = {}

        objecttype_fields[objecttype][column] = {
            'template': template,
            'start_offset': start_offset,
            'only_insert': only_insert,
            'obj_field': obj_field,
            'no_sequence_if_empty_field': no_sequence_if_empty_field,
            'is_linked_field': is_linked_field,
        }

    # iterate over the objects, collect the pool id(s) to load the pool configuration
    pool_ids = set()
    for i in range(len(objects)):
        obj = objects[i]
        if not isinstance(obj, dict):
            continue

        objecttype = util.get_json_value(obj, '_objecttype')
        if not isinstance(objecttype, str):
            continue

        pool_id = util.get_json_value(obj, f'{objecttype}._pool.pool._id')
        if isinstance(pool_id, int):
            pool_ids.add(pool_id)

    # load pools (and parents)
    # collect template configurations for objecttypes
    pool_info = {}
    pool_customdata = {}
    if len(pool_ids) > 0:
        pool_info, pool_customdata = pool.load_pool_data(
            api_url,
            access_token,
            pool_ids,
        )

    templates_manager = templates.TemplatesManager(
        pool_info,
        api_url,
        access_token,
        sequence_objecttype,
        sequence_ref_field,
        sequence_num_field,
        database_languages,
    )

    updated_objects = []

    # cache: map system object id of linked objects to search result to avoid duplicate searches
    linked_object_cache = {}

    for i in range(len(objects)):
        obj = objects[i]

        if not isinstance(obj, dict):
            continue

        # skip objects that are not configured in the base config and that are not in a pool
        objecttype = util.get_json_value(obj, '_objecttype')
        pool_id = util.get_json_value(obj, f'{objecttype}._pool.pool._id')
        if objecttype not in objecttype_fields and pool_id is None:
            # another objecttype was inserted, nothing to do here
            continue

        version = util.get_json_value(obj, f'{objecttype}._version')

        # iterate over the templates for different fields which are defined in the base configuration
        # check if the fields need to be updated
        obj_changed = False
        column_templates = util.get_json_value(objecttype_fields, objecttype)
        if column_templates is None:
            column_templates = {}

        for column in column_templates:
            oc = column_templates[column]
            template = oc['template']
            start_offset = oc['start_offset']
            only_insert = oc['only_insert']
            obj_field = oc['obj_field']
            no_sequence_if_empty_field = oc['no_sequence_if_empty_field']
            is_linked_field = oc['is_linked_field']

            # skip if the object was updated but the field setting for only_insert is true
            if only_insert and util.get_json_value(obj, f'{objecttype}._version') != 1:
                # object was updated, nothing to do here
                continue

            field_value = util.get_json_value(obj, f'{objecttype}.{column}')
            if field_value not in [None, '']:
                # field is already set, nothing to do here
                continue

            # format new field value based on the sequence and update new obj

            # repeat:
            # 1:    get the next number of the sequence (from an existing object, or 1 if the sequence has not been used yet)
            #   -   get the sequence value:
            #       - if a value from a (linked) field is part of the sequence, get the value of this field and use it in the reference
            #       - else build a generic reference for this objecttype and column
            # 2:    determine the new maximum number of the sequence
            # 3:    try to update the sequence object (protected by object version)
            # 4:    if the sequence was updated, update and return the objects, break loop

            sequence_ref = f'{PLUGIN_NAME}:{objecttype}.{column}'

            obj_field_value = None
            if obj_field is not None:
                if is_linked_field:

                    path_to_linked_field = obj_field.split('.')
                    sys_id = None

                    if path_to_linked_field[0].startswith('_nested:'):
                        # if the linked object is inside a nested table, use the first entry if possible
                        nested = util.get_json_value(
                            obj[objecttype], path_to_linked_field[0]
                        )
                        if isinstance(nested, list) and len(nested) > 0:
                            sys_id = util.get_json_value(
                                nested[0],
                                f'{".".join(path_to_linked_field[1:-1])}._system_object_id',
                            )
                    else:
                        # check if there is a value for the linked field in this object: search for the linked object
                        sys_id = util.get_json_value(
                            obj[objecttype],
                            f'{path_to_linked_field[0]}._system_object_id',
                        )

                    if sys_id is not None:
                        if sys_id in linked_object_cache:
                            obj_field_value = linked_object_cache[sys_id]
                        else:
                            ok, result = search.do_search(api_url, access_token, sys_id)
                            if ok:
                                link_ot = util.get_json_value(result, '_objecttype')
                                obj_field_value = util.get_json_value(
                                    result,
                                    f'{link_ot}.{path_to_linked_field[-1]}',
                                )
                else:
                    # value is not in a linked object, check if it is set in the object
                    obj_field_value = util.get_json_value(obj[objecttype], obj_field)

            if obj_field_value is None:
                # if the obj_field is set, but no value could be found,
                # check if the value should be kept empty or the object should be skipped completly
                if obj_field is not None:
                    if no_sequence_if_empty_field:
                        continue

                    obj_field_value = 'N/A'

            if obj_field_value is not None:
                sequence_ref += f':{obj_field}={obj_field_value}'

            seq = sequence.FylrSequence(
                api_url,
                sequence_ref,
                access_token,
                sequence_objecttype,
                sequence_ref_field,
                sequence_num_field,
                log_in_tmp_file=False,
            )

            do_repeat = True
            repeated = 0
            while do_repeat:
                do_repeat = False

                offset = seq.get_next_number()

                # update the new sequence to check if it has not been changed by another instance
                update_ok, error = seq.update(offset + 1)

                if error is not None:
                    # indicator that something went wrong and the plugin should just return an error message
                    util.return_error_response(
                        util.dumpjs(
                            {
                                'error': 'could not update sequence',
                                'reason': error,
                            }
                        )
                    )

                if not update_ok:
                    # sleep for 1 second and try again to get and update the sequence
                    time.sleep(1)

                    do_repeat = True
                    repeated += 1

                    continue

                # sequence was updated, unique sequence values can be used to update objects
                try:
                    # replace `field` in template with object field value if it is included, else ignore
                    if obj_field_value is not None and '%field%' in template:
                        template = template.replace('%field%', obj_field_value)
                    # perform a replacement of `%d` related formats in template with the new sequence value
                    new_value = template % (start_offset + offset)
                except TypeError as e:
                    util.return_error_response(
                        util.dumpjs(
                            {
                                f'error': f'template "{template}" is invalid to format a sequential string',
                                'reason': str(e),
                            }
                        )
                    )

                obj[objecttype][column] = new_value
                obj_changed = True

        # check if the object is in a pool and if this pool has (inherited) custom data template settings
        if pool_id in pool_customdata:
            settings = util.get_json_value(pool_customdata[pool_id], objecttype)
            if isinstance(settings, dict):
                for field in settings.keys():
                    # skip entries that are not fields but additional info for fields
                    skip = False
                    for suffix in [
                        'start_offset',
                        'only_insert',
                    ]:
                        if field.endswith(f':{suffix}'):
                            skip = True
                            break
                    if skip:
                        continue

                    # if the template should only be applied when the object is inserted, check if the object has version 1
                    if util.get_json_value(settings, f'{field}:only_insert') == True:
                        if version != 1:
                            continue

                    # do not override if the field already has a value
                    field_value = util.get_json_value(obj, f'{objecttype}.{field}')
                    if field_value not in [None, '']:
                        continue

                    new_value = templates_manager.apply(
                        settings,
                        objecttype,
                        field,
                        pool_id,
                    )
                    if new_value is None:
                        continue

                    obj[objecttype][field] = new_value
                    obj_changed = True

        if obj_changed:
            updated_objects.append(obj)

    # everything ok, return only the updated objects, exit program
    util.return_response(
        {
            'objects': updated_objects,
        }
    )
