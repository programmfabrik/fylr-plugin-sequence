# encoding: utf-8


import sys
import time
import fylr_lib_plugin_python3.util as util
import sequence as sequence
import json

# todo: load multiple entries from baseconfig
# OBJECTTYPE = 'cs_image'
# NAME_FIELD = 'name'

PLUGIN_NAME = 'fylr-sequence-plugin'
NAME_PREFIX = 'HU'


@util.handle_exceptions
def main():

    orig_data = json.loads(sys.stdin.read())

    # get the server url
    api_url = util.get_json_value(orig_data, 'info.api_url')
    if api_url is None:
        util.return_error_response('info.api_url missing!')
    api_url += '/api/v1'

    # get a session token
    access_token = util.get_json_value(
        orig_data, 'info.api_user_access_token')
    if access_token is None:
        util.return_error_response('info.api_user_access_token missing!')

    # load base config for this plugin
    main_config_path = 'info.config.plugin.' + PLUGIN_NAME + \
        '.config.' + PLUGIN_NAME + '\.insert_sequence\.'

    util.write_tmp_file(
        'fylr_sequence_plugin.json',
        new_file=True,
        lines=[
            util.dumpjs(util.get_json_value(
                orig_data, 'info.config.plugin.' + PLUGIN_NAME))
        ]
    )

    # objecttypes/fields settings
    ot_settings = util.get_json_value(
        orig_data, main_config_path + 'objecttypes.objecttype_settings')
    if not isinstance(ot_settings, list):
        util.return_error_response(
            'no list of objecttype/field settings are defined in the base config')

    objecttype_fields = {}
    for config_entry in ot_settings:
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
        if not isinstance(start_offset, int):
            continue
        if start_offset < 1:
            start_offset = 0

        only_insert = util.get_json_value(config_entry, 'only_insert') == True

        if not objecttype in objecttype_fields:
            objecttype_fields[objecttype] = {}

        objecttype_fields[objecttype][column] = (
            template, start_offset, only_insert)

    util.write_tmp_file(
        'fylr_sequence_plugin.json',
        lines=[
            'ot_fields:',
            util.dumpjs(objecttype_fields)
        ]
    )

    if objecttype_fields == {}:
        util.return_response(orig_data)

    # sequence objecttype settings
    config_path = main_config_path + 'sequence.'

    sequence_objecttype = util.get_json_value(
        orig_data, config_path + 'objecttype')
    if sequence_objecttype is None:
        util.return_error_response(
            'no sequence objecttype is defined in the base config')
    sequence_ref_field = util.get_json_value(
        orig_data, config_path + 'ref_field')
    if sequence_ref_field is None:
        util.return_error_response(
            'no sequence reference field is defined in the base config')
    sequence_num_field = util.get_json_value(
        orig_data, config_path + 'num_field')
    if sequence_num_field is None:
        util.return_error_response(
            'no sequence number field is defined in the base config')

    # iterate over objects and check if the name must be set
    objects = util.get_json_value(orig_data, 'objects')
    if not isinstance(objects, list):
        util.return_response(orig_data)

    any_changes = False

    returned_objects = []

    for i in range(len(objects)):
        obj = objects[i]

        if not isinstance(obj, dict):
            continue

        objecttype = util.get_json_value(obj, '_objecttype')
        if objecttype not in objecttype_fields:
            # another objecttype was inserted, nothing to do here
            returned_objects.append(obj)
            continue

        # iterate over the templates for different fields, check if the fields need to be updated

        new_obj = obj
        for update_column in objecttype_fields[objecttype]:
            template = objecttype_fields[objecttype][update_column][0]
            start_offset = objecttype_fields[objecttype][update_column][1]
            only_insert = objecttype_fields[objecttype][update_column][2]

            util.write_tmp_file(
                'fylr_sequence_plugin.json',
                lines=[
                    'objecttype:',
                    objecttype,
                    'update_column:',
                    update_column,
                    'template:',
                    template,
                    'only_insert:',
                    only_insert,
                ]
            )

            # skip if the object was updated but the field setting for only_insert is true
            if only_insert and util.get_json_value(obj, objecttype + '._version') != 1:
                # object was updated, nothing to do here
                returned_objects.append(obj)
                continue

            field_value = util.get_json_value(
                new_obj, '%s.%s' % (objecttype, update_column))
            if field_value not in [None, '']:
                # field is already set, nothing to do here
                continue

            # format new field value based on the sequence and update new obj

            # repeat:
            # 1:    get the next number of the sequence (from an existing object, or 1 if the sequence has not been used yet)
            # 2:    determine the new maximum number of the sequence
            # 3:    try to update the sequence object (protected by object version)
            # 4:    if the sequence was updated, update and return the objects, break loop

            seq = sequence.FylrSequence(
                api_url,
                '{0}:{1}.{2}'.format(PLUGIN_NAME, objecttype, update_column),
                access_token,
                sequence_objecttype,
                sequence_ref_field,
                sequence_num_field,
                log_in_tmp_file=True)  # xxx

            util.write_tmp_file(
                'fylr_sequence_plugin.json',
                lines=[
                    'FylrSequence:',
                    str(seq),
                ]
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
                    util.return_error_response(util.dumpjs({
                        'error': 'could not update sequence',
                        'reason': error
                    }))

                if not update_ok:
                    # sleep for 1 second and try again to get and update the sequence
                    time.sleep(1)

                    do_repeat = True
                    repeated += 1

                    continue

                # sequence was updated, unique sequence values can be used to update objects
                try:
                    new_value = template % (start_offset + offset)
                except TypeError as e:
                    util.return_error_response(util.dumpjs({
                        'error': 'template "' + template + '" is invalid to format a sequential string',
                        'reason': str(e)
                    }))

                new_obj[objecttype][update_column] = new_value

        obj = new_obj
        returned_objects.append(obj)

    # everything ok, update and return the objects, exit program

    response = orig_data
    if any_changes:
        response['objects'] = returned_objects

    util.return_response(response)


if __name__ == '__main__':
    main()
