# encoding: utf-8


import sys
import time
import fylr_lib_plugin_python3.util as util
import sequence
import search
import json


PLUGIN_NAME = 'fylr-plugin-sequence'
NA = '[N/A]'


@util.handle_exceptions
def main():

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
    main_config_path = 'info.config.plugin.' + PLUGIN_NAME + '.config.' + PLUGIN_NAME + '\.insert_sequence\.'

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

        objecttype_fields[objecttype][column] = {
            'template': template,
            'start_offset': start_offset,
            'only_insert': only_insert,
            'obj_field': obj_field,
            'is_linked_field': is_linked_field,
        }

    if objecttype_fields == {}:
        util.return_empty_objects()

    # iterate over objects and check if the name must be set
    if not isinstance(objects, list):
        util.return_empty_objects()

    updated_objects = []

    # cache: map system object id of linked objects to search result to avoid duplicate searches
    linked_object_cache = {}


    for i in range(len(objects)):
        obj = objects[i]

        if not isinstance(obj, dict):
            continue

        objecttype = util.get_json_value(obj, '_objecttype')
        if objecttype not in objecttype_fields:
            # another objecttype was inserted, nothing to do here
            continue

        # iterate over the templates for different fields, check if the fields need to be updated

        obj_changed = False
        for column in objecttype_fields[objecttype]:
            template = objecttype_fields[objecttype][column]['template']
            start_offset = objecttype_fields[objecttype][column]['start_offset']
            only_insert = objecttype_fields[objecttype][column]['only_insert']
            obj_field = objecttype_fields[objecttype][column]['obj_field']
            is_linked_field = objecttype_fields[objecttype][column]['is_linked_field']

            # skip if the object was updated but the field setting for only_insert is true
            if only_insert and util.get_json_value(obj, objecttype + '._version') != 1:
                # object was updated, nothing to do here
                continue

            field_value = util.get_json_value(obj, '%s.%s' % (objecttype, column))
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


            sequence_ref = '{0}:{1}.{2}'.format(
                PLUGIN_NAME,
                objecttype,
                column
            )

            object_field_value = NA
            if obj_field is not None:
                if is_linked_field:
                    # check if there is a value for the linked field in this object: search for the linked object
                    sys_id = util.get_json_value(obj[objecttype], obj_field.split('.')[0] + '._system_object_id')
                    if sys_id in linked_object_cache:
                        object_field_value = linked_object_cache[sys_id]
                    else:
                        ok, result = search.do_search(api_url, access_token, sys_id)
                        if ok:
                            object_field_value = util.get_json_value(result, obj_field)
                        else:
                            util.return_error_response(util.dumpjs(result))
                else:
                    # value is not in a linked object, check if it is set in the object
                    object_field_value = util.get_json_value(obj[objecttype], obj_field)

            if object_field_value is not None:
                sequence_ref += ':{0}={1}'.format(obj_field, object_field_value)

            seq = sequence.FylrSequence(
                api_url,
                sequence_ref,
                access_token,
                sequence_objecttype,
                sequence_ref_field,
                sequence_num_field,
                log_in_tmp_file=False)


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
                    # replace `field` in template with object field value if it is included, else ignore
                    template = template.replace('%field%', object_field_value)
                    # perform a replacement of `%d` related formats in template with the new sequence value
                    new_value = template % (start_offset + offset)
                except TypeError as e:
                    util.return_error_response(util.dumpjs({
                        'error': 'template "' + template + '" is invalid to format a sequential string',
                        'reason': str(e)
                    }))

                obj[objecttype][column] = new_value
                obj_changed = True

        if obj_changed:
            updated_objects.append(obj)

    # everything ok, return only the updated objects, exit program
    util.return_response({
        'objects': updated_objects
    })


if __name__ == '__main__':
    main()