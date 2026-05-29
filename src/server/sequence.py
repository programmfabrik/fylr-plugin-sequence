# encoding: utf-8

import fylr_lib_plugin_python3.util as util
import json
import time


def get_next_offset(
    plugin_name,
    api_url,
    access_token,
    objecttype,
    column,
    sequence_objecttype,
    sequence_ref_field,
    sequence_num_field,
    pool_id=None,
    log_in_tmp_file=False,
):

    # repeat:
    # 1:    get the next number of the sequence (from an existing object, or 1 if the sequence has not been used yet)
    # 2:    determine the new maximum number of the sequence
    # 3:    try to update the sequence object (protected by object version)
    # 4:    if the sequence was updated, update and return the objects, break loop

    if not pool_id:
        sequence_ref = f'{plugin_name}:{objecttype}.{column}'
    else:
        sequence_ref = f'{plugin_name}:poolid={pool_id}:{objecttype}.{column}'

    seq = FylrSequence(
        api_url,
        sequence_ref,
        access_token,
        sequence_objecttype,
        sequence_ref_field,
        sequence_num_field,
        log_in_tmp_file=log_in_tmp_file,
    )

    do_repeat = True
    repeated = 0
    max_repeat = 3

    while do_repeat:
        do_repeat = False

        offset = seq.get_next_number()

        # update the new sequence to check if it has not been changed by another instance
        update_ok = seq.update(offset + 1)

        if not update_ok:
            # sleep for 1 second and try again to get and update the sequence
            time.sleep(1)

            repeated += 1

            if repeated >= max_repeat:
                break

            do_repeat = True
            continue

        return offset

    return None


class FylrSequence(object):

    def __init__(
        self,
        api_url,
        ref,
        access_token,
        sequence_objecttype,
        sequence_ref_field,
        sequence_num_field,
        log_in_tmp_file=False,
    ) -> None:
        self.api_url = api_url
        while self.api_url.endswith('/'):
            self.api_url = self.api_url[:-1]
        self.ref = ref
        self.access_token = access_token
        self.log_in_tmp_file = log_in_tmp_file

        self.current_number = 1
        self.version = 1
        self.obj_id = None

        self.sequence_objecttype = sequence_objecttype

        # get the standard mask for the sequence objecttype (necessary since _all_fields can only be used by root)
        self.mask = self.get_sequence_objecttype_mask()

        if sequence_ref_field.startswith(f'{sequence_objecttype}.'):
            sequence_ref_field = sequence_ref_field[len(sequence_objecttype) + 1 :]
        self.sequence_ref_field = sequence_ref_field

        if sequence_num_field.startswith(f'{sequence_objecttype}.'):
            sequence_num_field = sequence_num_field[len(sequence_objecttype) + 1 :]
        self.sequence_num_field = sequence_num_field

    def __str__(self) -> str:
        return f'{self.ref}: {self.current_number}'

    def get_from_api(self, path):
        resp, statuscode = util.get_from_api(
            self.api_url,
            path,
            self.access_token,
            log_in_tmp_file=self.log_in_tmp_file,
        )
        return resp, statuscode

    def post_to_api(self, path, payload=None):
        resp, statuscode = util.post_to_api(
            self.api_url,
            path,
            self.access_token,
            payload=payload,
            log_in_tmp_file=self.log_in_tmp_file,
        )
        return resp, statuscode

    def get_next_number(self) -> int:
        global PLUGIN_NAME

        path = f'db/{self.sequence_objecttype}/{self.mask}/list'
        api_resp, statuscode = self.get_from_api(path)

        hint = 'sequence: get next number'

        if statuscode != 200:
            # if it is an api error return it to fylr
            util.return_if_api_error(api_resp, hint)

            util.return_error_response_with_parameters(
                error_code=f'error.{PLUGIN_NAME}',
                error_msg=f'{hint}: unexpected response',
                parameters={
                    'response': api_resp,
                    'statuscode': statuscode,
                },
            )

        objects = []
        try:
            objects = json.loads(api_resp)
        except:
            objects = None
        if not isinstance(objects, list):
            util.return_error_response_with_parameters(
                error_code=f'error.{PLUGIN_NAME}',
                error_msg=f'{hint}: unexpected response: expected array',
                parameters={
                    'response': api_resp,
                },
            )

        sequence_exists = False
        for obj in objects:

            # ignore all sequence objects that have been deleted
            # CAUTION: deleting sequence objects can cause unique constraint violations if old numbers of the sequence are reused
            if '_latest_version_deleted_at' in obj:
                continue

            # ignore all sequence objects that have a different reference
            if (
                util.get_json_value(
                    obj,
                    f'{self.sequence_objecttype}.{self.sequence_ref_field}',
                )
                != self.ref
            ):
                continue

            sequence_exists = True

            # get the last used number of the sequence
            n = util.get_json_value(
                obj,
                f'{self.sequence_objecttype}.{self.sequence_num_field}',
            )
            if not n:
                n = 1

            # update offset, object id and version
            self.current_number = n
            self.obj_id = util.get_json_value(
                obj,
                f'{self.sequence_objecttype}._id',
            )
            self.version = util.get_json_value(
                obj,
                f'{self.sequence_objecttype}._version',
            )

            break

        if not sequence_exists:
            self.current_number = 1

        # return the next free number of the sequence
        return self.current_number

    def update(self, new_number: int) -> bool:
        global PLUGIN_NAME

        if new_number <= self.current_number:
            # no update, caller should repeat
            return False

        new_obj = {
            '_objecttype': self.sequence_objecttype,
            '_mask': self.mask if self.mask else '_all_fields',
            self.sequence_objecttype: {
                '_id': self.obj_id,
                '_version': 1 if not self.obj_id else self.version + 1,
                self.sequence_num_field: new_number,
                self.sequence_ref_field: self.ref,
            },
        }

        resp, statuscode = self.post_to_api(
            f'db/{self.sequence_objecttype}',
            util.dumpjs([new_obj]),
        )

        # determine if the caller should try to repeat a failed update or give up

        if statuscode == 200:
            # everything ok
            self.version += 1
            return True

        elif statuscode == 400:
            # some api error, maybe wrong version
            # => caller should repeat the process, and get the new current sequence number
            return False

        else:
            # not an (expected) api error, some other response
            util.return_error_response_with_parameters(
                error_code=f'error.{PLUGIN_NAME}',
                error_msg=f'update sequence: unexpected response',
                parameters={
                    'response': resp,
                    'statuscode': statuscode,
                },
            )

    def get_sequence_objecttype_mask(self):
        global PLUGIN_NAME

        resp, statuscode = self.get_from_api('mask/CURRENT')

        hint = 'get info about sequence objecttype from get /api/v1/mask/CURRENT'

        if statuscode != 200:
            util.return_if_api_error(resp, hint)

            # not an api error, some other response
            util.return_error_response_with_parameters(
                error_code=f'error.{PLUGIN_NAME}',
                error_msg=f'{hint}: unexpected response',
                parameters={
                    'response': resp,
                    'statuscode': statuscode,
                },
            )

        content = json.loads(resp)
        masks = util.get_json_value(content, 'masks')
        if not isinstance(masks, list):
            util.return_error_response_with_parameters(
                error_code=f'error.{PLUGIN_NAME}',
                error_msg=f'{hint}: unexpected response (expect "masks" as array)',
                parameters={
                    'response': resp,
                    'statuscode': statuscode,
                },
            )

        for mask in masks:
            table_name = util.get_json_value(mask, 'table_name_hint')
            if table_name != self.sequence_objecttype:
                continue

            is_preferred = util.get_json_value(mask, 'is_preferred')
            if not isinstance(is_preferred, bool) or not is_preferred:
                continue

            mask_name = util.get_json_value(mask, 'name')
            if not isinstance(mask_name, str) or len(mask_name) < 1:
                continue

            return mask_name

        util.return_error_response_with_parameters(
            error_code=f'error.{PLUGIN_NAME}',
            error_msg=f'{hint}: unexpected response (could not find standard mask for objecttype "{self.sequence_objecttype}")',
            parameters={
                'response': resp,
                'statuscode': statuscode,
            },
        )
