# encoding: utf-8


import sys
import fylr_lib_plugin_python3.util as util
import sequence
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
    main_config_path = 'info.config.plugin.' + PLUGIN_NAME + \
        '.config.' + PLUGIN_NAME + '\.insert_sequence\.'

    # load ordered list of database languages
    database_languages = []
    langs = util.get_json_value(orig_data, 'info.config.system.config.languages.database')
    if isinstance(langs, list):
        for l in langs:
            v = util.get_json_value(l, 'value')
            if v is None:
                continue
            if len(v) < 1:
                continue
            database_languages.append(v)
    if len(database_languages) < 1:
        database_languages.append('en-US')

    # sequence objecttype settings
    config_path = main_config_path + 'sequence.'

    sequence_objecttype = util.get_json_value(orig_data, config_path + 'sequence_objecttype')
    if sequence_objecttype is None or len(sequence_objecttype) < 1:
        util.return_empty_objects()
    sequence_ref_field = util.get_json_value(orig_data, config_path + 'sequence_ref_field')
    if sequence_ref_field is None or len(sequence_ref_field) < 1:
        util.return_empty_objects()
    sequence_num_field = util.get_json_value(orig_data, config_path + 'sequence_num_field')
    if sequence_num_field is None or len(sequence_num_field) < 1:
        util.return_empty_objects()

    # objecttypes/fields settings
    ot_settings = util.get_json_value(orig_data, main_config_path + 'objecttypes.objecttype_settings')
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
        if column.startswith(objecttype + '.'):
            column = column[len(objecttype) + 1:]
        if len(column) < 1:
            continue

        template = util.get_json_value(config_entry, 'template')
        if not isinstance(template, str):
            continue
        if len(template) < 1:
            continue

        start_offset = util.get_json_value(config_entry, 'start_offset')
        if start_offset is None:
            start_offset = 0
        elif not isinstance(start_offset, int):
            continue
        if start_offset < 1:
            start_offset = 0

        only_insert = util.get_json_value(config_entry, 'only_insert') == True

        if not objecttype in objecttype_fields:
            objecttype_fields[objecttype] = {}

        objecttype_fields[objecttype][column] = (template, start_offset, only_insert)

    # iterate over the objects, collect the pool id(s) to load the pool configuration
    pool_ids = set()
    for i in range(len(objects)):
        obj = objects[i]
        if not isinstance(obj, dict):
            continue

        objecttype = util.get_json_value(obj, '_objecttype')
        if not isinstance(objecttype, str):
            continue

        pool_id = util.get_json_value(obj, '{0}._pool.pool._id'.format(objecttype))
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
            pool_ids
        )

    templates_manager = templates.TemplatesManager(
        pool_info,
        api_url,
        access_token,
        sequence_objecttype,
        sequence_ref_field,
        sequence_num_field,
        database_languages
    )

    updated_objects = []

    for i in range(len(objects)):
        obj = objects[i]

        if not isinstance(obj, dict):
            continue

        # skip objects that are not configured in the base config and that are not in a pool
        objecttype = util.get_json_value(obj, '_objecttype')
        pool_id = util.get_json_value(obj, '{0}._pool.pool._id'.format(objecttype))
        if objecttype not in objecttype_fields and pool_id is None:
            # another objecttype was inserted, nothing to do here
            continue

        version = util.get_json_value(obj, '{0}._version'.format(objecttype))

        # iterate over the templates for different fields which are defined in the base configuration
        # check if the fields need to be updated
        obj_changed = False
        column_templates = util.get_json_value(objecttype_fields, objecttype)
        if column_templates is None:
            column_templates = {}

        for column in column_templates:
            template = column_templates[column][0]
            start_offset = column_templates[column][1]
            only_insert = column_templates[column][2]

            # skip if the object was updated but the field setting for only_insert is true
            if only_insert and util.get_json_value(obj, objecttype + '._version') != 1:
                # object was updated, nothing to do here
                continue

            field_value = util.get_json_value(obj, '%s.%s' % (objecttype, column))
            if field_value not in [None, '']:
                # field is already set, nothing to do here
                continue

            # format new field value based on the sequence and update new obj
            sequence_offset = sequence.get_next_offset(
                PLUGIN_NAME,
                api_url,
                access_token,
                objecttype,
                column,
                sequence_objecttype,
                sequence_ref_field,
                sequence_num_field
            )
            if sequence_offset is None:
                continue

            # sequence was updated, unique sequence values can be used to update objects
            try:
                new_value = template % (start_offset + sequence_offset)
            except TypeError as e:
                util.return_error_response(util.dumpjs({
                    'error': 'template "' + template + '" is invalid to format a sequential string',
                    'reason': str(e)
                }))

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
                        if field.endswith(':{0}'.format(suffix)):
                            skip = True
                            break
                    if skip:
                        continue

                    # if the template should only be applied when the object is inserted, check if the object has version 1
                    if util.get_json_value(settings, '{0}:only_insert'.format(field)) == True:
                        if version != 1:
                            continue

                    # do not override if the field already has a value
                    field_value = util.get_json_value(obj, '{0}.{1}'.format(objecttype, field))
                    if field_value not in [None, '']:
                        continue

                    new_value = templates_manager.apply(
                        settings,
                        objecttype,
                        field,
                        pool_id
                    )
                    if new_value is None:
                        continue

                    obj[objecttype][field] = new_value
                    obj_changed = True

        if obj_changed:
            updated_objects.append(obj)

    # everything ok, return only the updated objects, exit program
    util.return_response({
        'objects': updated_objects
    })
