# encoding: utf-8

import fylr_lib_plugin_python3.util as util
import json
import random
import time

PLUGIN_NAME = 'fylr-plugin-sequence'

# rows per request when scanning for the sequence object. `db/<ot>/<mask>/list`
# answers at most 1000 rows, so the scan must page: on an instance whose
# sequence objecttype holds more rows than one page, the plugin would otherwise
# never see its own sequence, restart it at 1 and collide with the unique key on
# the reference field on every save (#78720)
LIST_PAGE_SIZE = 1000

# how often a *rejected* sequence update is repeated, and how long the plugin
# waits between the attempts. Only a conflict with a concurrent save is
# repeated (see classify_update_error), so this budget is spent on contention
# alone: n editors saving at the same moment serialize on the one sequence
# object, and every loser has to read and write it again. The wait grows and
# carries jitter so the losers do not collide again in lockstep - with a fixed
# delay only one of them gets through per round and the last one runs out of
# attempts (the parallel apitest saves 5 objects at once).
MAX_UPDATE_ATTEMPTS = 10
RETRY_DELAY_SECONDS = 0.25
RETRY_DELAY_MAX_SECONDS = 2.0

# what to do with an update that fylr rejected
UPDATE_ERROR_RETRY = 'retry'  # another save was faster: read the sequence again
UPDATE_ERROR_VERIFY = 'verify'  # the sequence exists although the plugin did not see it
UPDATE_ERROR_FAIL = 'fail'  # every attempt is rejected the same way


def retry_delay(attempt: int) -> float:
    # exponential back-off with full jitter over the last step
    delay = min(
        RETRY_DELAY_MAX_SECONDS,
        RETRY_DELAY_SECONDS * (2 ** (attempt - 1)),
    )
    return delay / 2 + random.random() * delay / 2


def classify_update_error(response: str, ref: str, ref_field: str) -> str:
    # decides what to do with a sequence update that fylr rejected.
    #
    # Another save that reached the sequence object first is the reason that
    # goes away by itself. fylr reports it as VersionMismatch (the version the
    # plugin read is no longer the current one) or, when both saves got past
    # that check, as a unique key violation on the object table: `object_u1` is
    # UNIQUE(system_object_id, version), so the loser writes a version of the
    # sequence object that the winner has just written.
    #
    # A unique key violation on the *reference* field means that the sequence
    # object exists although the plugin did not find it, which has two causes
    # that look exactly alike in the response: another save inserted the
    # sequence object a moment ago (goes away, the next read finds it), or the
    # object is hidden from this user (#78720, never goes away). Only reading
    # the sequence again tells them apart, so this is answered with VERIFY and
    # next_offset() decides after the next read.
    #
    # Everything else - a missing right, an invalid mask, ... - is answered the
    # same way on every attempt and must be returned to the user.
    try:
        response_js = json.loads(response)
    except:
        return UPDATE_ERROR_FAIL

    if not isinstance(response_js, dict):
        return UPDATE_ERROR_FAIL

    if response_js.get('realm') != 'api':
        return UPDATE_ERROR_FAIL

    code = response_js.get('code')

    if code == 'VersionMismatch':
        return UPDATE_ERROR_RETRY

    if code == 'DatabaseLockError':
        # sqlite answers a write during another write transaction with this
        return UPDATE_ERROR_RETRY

    if code == 'DatabaseUniqueKeyViolation':
        name = util.get_json_value(response_js, 'parameters.name')
        # the unique keys of the object table are named object_u1 ... object_u6
        if isinstance(name, str) and name.startswith('object_u'):
            return UPDATE_ERROR_RETRY

    if code == 'UniqueKeyViolation':
        if (
            util.get_json_value(response_js, 'parameters.column') == ref_field
            and util.get_json_value(response_js, 'parameters.value') == ref
        ):
            return UPDATE_ERROR_VERIFY

    return UPDATE_ERROR_FAIL


def get_next_offset(
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

    if not pool_id:
        sequence_ref = f'{PLUGIN_NAME}:{objecttype}.{column}'
    else:
        sequence_ref = f'{PLUGIN_NAME}:poolid={pool_id}:{objecttype}.{column}'

    seq = FylrSequence(
        api_url,
        sequence_ref,
        access_token,
        sequence_objecttype,
        sequence_ref_field,
        sequence_num_field,
        log_in_tmp_file=log_in_tmp_file,
    )

    return seq.next_offset()


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

        # response of the last update that fylr rejected. next_offset() hands
        # it back, so a permanent problem (a missing right, a unique key
        # violation on the reference, ...) becomes visible instead of being
        # repeated until the server kills the callback (#78720)
        self.last_error_response = None
        self.last_error_statuscode = 0

        # what to do with that rejection, see classify_update_error
        self.last_error_reason = UPDATE_ERROR_FAIL

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

    def next_offset(self):
        # repeat:
        # 1:    get the next number of the sequence (from an existing object, or 1 if the sequence has not been used yet)
        # 2:    determine the new maximum number of the sequence
        # 3:    try to update the sequence object (protected by object version)
        # 4:    if the sequence was updated, return the number to use

        attempt = 0
        insert_rejected = False

        while True:
            offset = self.get_next_number()

            if insert_rejected and self.obj_id is None:
                # inserting the sequence object was rejected because its
                # reference exists, and reading the sequence again still does
                # not find it: it is hidden from this user, who can create
                # sequence objects but not read them (#78720). Repeating this
                # is rejected in the same way forever
                self.fail_with_last_error(
                    f'sequence "{self.ref}": update failed', attempt
                )

            insert_rejected = False

            # update the new sequence to check if it has not been changed by another instance
            if self.update(offset + 1):
                return offset

            attempt += 1

            if self.last_error_reason == UPDATE_ERROR_FAIL:
                # repeating would be rejected for the same reason again, so
                # return the reason to the user right away (#78720)
                self.fail_with_last_error(
                    f'sequence "{self.ref}": update failed', attempt
                )

            if attempt >= MAX_UPDATE_ATTEMPTS:
                # the sequence stays contended: give up rather than keep the
                # save pending until fylr kills the callback (#78720)
                self.fail_with_last_error(
                    f'sequence "{self.ref}": update failed', attempt
                )

            # the sequence object exists although this attempt did not see it:
            # the next read has to decide whether it is now visible
            insert_rejected = self.last_error_reason == UPDATE_ERROR_VERIFY

            # wait, then read the sequence again and update it from its new number
            time.sleep(retry_delay(attempt))

    def get_next_number(self) -> int:
        hint = 'sequence: get next number'

        sequence_exists = False
        offset = 0

        while True:
            api_resp, statuscode = self.get_from_api(
                f'db/{self.sequence_objecttype}/{self.mask}/list'
                f'?limit={LIST_PAGE_SIZE}&offset={offset}'
            )

            if statuscode != 200:
                # if it is an api error return it to fylr
                util.return_if_api_error(api_resp, hint)

                util.return_error_response_with_parameters(
                    error_code=f'{PLUGIN_NAME}.error.unexpected_fylr_response',
                    error_msg=f'{hint}: unexpected response from fylr',
                    parameters={
                        'response': api_resp,
                        'statuscode': statuscode,
                        'hint': hint,
                    },
                )

            objects = []
            try:
                objects = json.loads(api_resp)
            except:
                objects = None
            if not isinstance(objects, list):
                util.return_error_response_with_parameters(
                    error_code=f'{PLUGIN_NAME}.error.unexpected_fylr_response',
                    error_msg=f'{hint}: unexpected response from fylr',
                    parameters={
                        'response': api_resp,
                        'hint': hint,
                    },
                )

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

            if sequence_exists:
                break

            if len(objects) < LIST_PAGE_SIZE:
                # last page: this sequence does not exist yet
                break

            offset += LIST_PAGE_SIZE

        if not sequence_exists:
            self.current_number = 1

        # return the next free number of the sequence
        return self.current_number

    def update(self, new_number: int) -> bool:
        hint = 'update sequence'

        self.last_error_response = None
        self.last_error_statuscode = 0
        self.last_error_reason = UPDATE_ERROR_FAIL

        if new_number <= self.current_number:
            # no update, caller should repeat
            self.last_error_reason = UPDATE_ERROR_RETRY
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
            # => the caller repeats the process and gets the new current sequence
            # number, but only if another save caused this.
            # keep the response: when repeating does not help, the caller returns it
            self.last_error_response = resp
            self.last_error_statuscode = statuscode
            self.last_error_reason = classify_update_error(
                resp,
                self.ref,
                self.sequence_ref_field,
            )
            return False

        else:
            # check if it is another api error, if then return
            util.return_if_api_error(resp, hint)

            # not an (expected) api error, some other response
            util.return_error_response_with_parameters(
                error_code=f'{PLUGIN_NAME}.error.unexpected_fylr_response',
                error_msg=f'{hint}: unexpected response from fylr',
                parameters={
                    'response': resp,
                    'statuscode': statuscode,
                    'hint': hint,
                },
            )

    def fail_with_last_error(self, hint: str, attempts: int):
        # called when a caller has used up its repeats: return the response of
        # the last rejected update, so the actual reason reaches the user.
        # Without this the callers repeat forever and the save request only ends
        # when fylr kills the plugin callback (#78720)
        if self.last_error_response is not None:
            # a fylr api error (missing right, unique key violation, ...) is
            # passed through as it is
            util.return_if_api_error(self.last_error_response, hint)

        util.return_error_response_with_parameters(
            error_code=f'{PLUGIN_NAME}.error.unexpected_fylr_response',
            error_msg=f'{hint}: sequence "{self.ref}" could not be updated in {attempts} attempts',
            parameters={
                'response': self.last_error_response,
                'statuscode': self.last_error_statuscode,
                'sequence': self.ref,
                'attempts': attempts,
                'hint': hint,
            },
        )

    def get_sequence_objecttype_mask(self):
        resp, statuscode = self.get_from_api('mask/CURRENT')

        hint = 'get info about sequence objecttype from get /api/v1/mask/CURRENT'

        if statuscode != 200:
            util.return_if_api_error(resp, hint)

            # not an api error, some other response
            util.return_error_response_with_parameters(
                error_code=f'{PLUGIN_NAME}.error.unexpected_fylr_response',
                error_msg=f'{hint}: unexpected response from fylr',
                parameters={
                    'response': resp,
                    'statuscode': statuscode,
                    'hint': hint,
                },
            )

        content = json.loads(resp)
        masks = util.get_json_value(content, 'masks')
        if not isinstance(masks, list):
            util.return_error_response_with_parameters(
                error_code=f'{PLUGIN_NAME}.error.no_standard_mask_for_ot',
                error_msg=f'could not find standard mask for objecttype {self.sequence_objecttype})',
                parameters={
                    'response': resp,
                    'statuscode': statuscode,
                    'sequence_objecttype': self.sequence_objecttype,
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
            error_code=f'{PLUGIN_NAME}.error.no_standard_mask_for_ot',
            error_msg=f'could not find standard mask for objecttype {self.sequence_objecttype})',
            parameters={
                'response': resp,
                'statuscode': statuscode,
                'sequence_objecttype': self.sequence_objecttype,
            },
        )
