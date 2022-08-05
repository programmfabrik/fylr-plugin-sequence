# encoding: utf-8

import fylr_lib_plugin_python3.util as util
import json


class FylrSequence(object):

    def __init__(self, api_url, ref, access_token, sequence_objecttype, sequence_ref_field, sequence_num_field, log_in_tmp_file=False) -> None:
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

        if sequence_ref_field.startswith(sequence_objecttype + '.'):
            sequence_ref_field = sequence_ref_field[len(
                sequence_objecttype) + 1:]
        self.sequence_ref_field = sequence_ref_field

        if sequence_num_field.startswith(sequence_objecttype + '.'):
            sequence_num_field = sequence_num_field[len(
                sequence_objecttype) + 1:]
        self.sequence_num_field = sequence_num_field

    def __str__(self) -> str:
        return '%s: %d'.format(self.ref, self.current_number)

    @util.handle_exceptions
    def get_from_api(self, path):
        return util.get_from_api(self.api_url, path, self.access_token, log_in_tmp_file=self.log_in_tmp_file)

    @util.handle_exceptions
    def post_to_api(self, path, payload=None):
        return util.post_to_api(self.api_url, path, self.access_token, payload=payload, log_in_tmp_file=self.log_in_tmp_file)

    @util.handle_exceptions
    def get_next_number(self) -> int:
        path = 'db/' + self.sequence_objecttype + '/_all_fields/list'
        api_resp, statuscode = self.get_from_api(path)

        if statuscode != 200:
            raise Exception('invalid response: ' +
                            str(statuscode) + ' - ' + api_resp)

        if len(api_resp) < 1:
            raise Exception('invalid response: expected non-empty body')

        objects = json.loads(api_resp)
        if not isinstance(objects, list):
            raise Exception('invalid response: expected array - ' + api_resp)

        sequence_exists = False
        for obj in objects:

            # ignore all sequence objects that have been deleted
            # CAUTION: deleting sequence objects can cause unique constraint violations if old numbers of the sequence are reused
            if '_latest_version_deleted_at' in obj:
                continue

            # ignore all sequence objects that have a different reference
            if util.get_json_value(obj, self.sequence_objecttype + '.' + self.sequence_ref_field) != self.ref:
                continue

            sequence_exists = True

            # get the last used number of the sequence
            n = util.get_json_value(
                obj, self.sequence_objecttype + '.' + self.sequence_num_field)
            if n is None or n < 1:
                n = 1

            # update offset, object id and version
            self.current_number = n
            self.obj_id = util.get_json_value(
                obj, self.sequence_objecttype + '._id')
            self.version = util.get_json_value(
                obj, self.sequence_objecttype + '._version')

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
            '_mask': '_all_fields',
            self.sequence_objecttype: {
                '_id': self.obj_id,
                '_version': 1 if self.obj_id is None else self.version + 1,
                self.sequence_num_field: new_number,
                self.sequence_ref_field: self.ref
            }
        }

        resp, statuscode = util.post_to_api(
            self.api_url,
            'db/' + self.sequence_objecttype,
            self.access_token,
            util.dumpjs([new_obj])
        )

        # determine if the caller should try to repeate a failed update or give up

        if statuscode == 200:
            # everything ok
            self.version += 1
            return True, None

        elif statuscode >= 400 and statuscode < 500:
            # some api error, maybe wrong version
            # => caller should repeat the process, and get the new current sequence number
            return False, None

        else:
            # something went wrong, caller should not try to repeat updating the sequence
            error = {
                'url': self.api_url + '/db/' + self.sequence_objecttype,
                'statuscode': statuscode,
            }
            error_resp = None
            try:
                error_resp = json.loads(resp)
            except:
                error_resp = resp
            error['response'] = error_resp

            return False, error
