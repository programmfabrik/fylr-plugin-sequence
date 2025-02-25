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

    if pool_id is None:
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

    @util.handle_exceptions
    def get_next_number(self) -> int:
        path = f'db/{self.sequence_objecttype}/{self.mask}/list'
        api_resp, statuscode = self.get_from_api(path)

        if statuscode != 200:
            raise Exception(f'invalid response: {statuscode} - {api_resp}')

        if len(api_resp) < 1:
            raise Exception('invalid response: expected non-empty body')

        objects = json.loads(api_resp)
        if not isinstance(objects, list):
            raise Exception(f'invalid response: expected array - {api_resp}')

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
            if n is None or n < 1:
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

    @util.handle_exceptions
    def update(self, new_number: int):

        if new_number <= self.current_number:
            return False, {
                'current_number': self.current_number,
                'new_number': new_number,
            }

        new_obj = {
            '_objecttype': self.sequence_objecttype,
            '_mask': self.mask if self.mask is not None else '_all_fields',
            self.sequence_objecttype: {
                '_id': self.obj_id,
                '_version': 1 if self.obj_id is None else self.version + 1,
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
            return True, None

        elif statuscode == 400:
            # some api error, maybe wrong version
            # => caller should repeat the process, and get the new current sequence number
            return False, None

        if statuscode != 200:
            raise Exception(f'invalid response: {statuscode} - {resp}')

    @util.handle_exceptions
    def get_sequence_objecttype_mask(self):
        resp, statuscode = self.get_from_api('mask/CURRENT')

        if statuscode != 200:
            raise Exception(
                f'could not get /api/v1/mask/CURRENT: statuscode {statuscode}, response: {resp}'
            )

        content = json.loads(resp)
        masks = util.get_json_value(content, 'masks')
        if not isinstance(masks, list):
            raise Exception(
                f'could not get masks from /api/v1/mask/CURRENT: response: {resp}'
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

        raise Exception(
            f'could not find standard mask for objecttype {self.sequence_objecttype} from /api/v1/mask/CURRENT'
        )
