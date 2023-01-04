# encoding: utf-8

import fylr_lib_plugin_python3.util as util
import sequence

PLUGIN_NAME = 'fylr-plugin-sequence'


class TemplatesManager(object):

    pool_value_mappings = {
        'id': 'pool._id',
        'reference': 'pool.reference',
        'shortname': 'pool.shortname',
        'level': '_level',
        'name:l10n': 'pool.name',
        'parent.id': 'pool._id_parent',
        'parent.reference': 'parent:pool.reference',
        'parent.shortname': 'parent:pool.shortname',
        'parent.level': 'parent:_level',
        'parent.name:l10n': 'parent:pool.name',
    }

    def __init__(self, pool_info, api_url, access_token, sequence_objecttype, sequence_ref_field, sequence_num_field, database_languages) -> None:

        self.api_url = api_url
        self.access_token = access_token
        self.sequence_objecttype = sequence_objecttype
        self.sequence_ref_field = sequence_ref_field
        self.sequence_num_field = sequence_num_field
        self.database_languages = database_languages

        self.__init_mappings(pool_info)

    def __init_mappings(self, pool_info):
        self.pool_mappings = {}
        for pool_id in pool_info.keys():
            self.pool_mappings[pool_id] = {}

            for k in self.pool_value_mappings.keys():
                p = self.pool_value_mappings[k]
                k = 'pool.{0}'.format(k)

                p_id = pool_id
                if p.startswith('parent:'):
                    parent_id = util.get_json_value(pool_info[pool_id], 'pool._id_parent')
                    if parent_id not in pool_info:
                        continue
                    p_id = parent_id
                    p = p[len('parent:'):]

                if k.endswith(':l10n'):
                    l10n = util.get_json_value(pool_info[p_id], p)
                    if not isinstance(l10n, dict):
                        continue
                    sub_k = k[:-len(':l10n')]

                    for lang in l10n.keys():

                        v = l10n[lang]
                        if v is None:
                            continue
                        v = str(v).strip()
                        if len(v) < 1:
                            continue

                        self.pool_mappings[pool_id]['{0}:{1}'.format(sub_k, lang)] = v

                    for lang in self.database_languages:
                        if not lang in l10n:
                            continue

                        v = l10n[lang]
                        if v is None:
                            continue
                        v = str(v).strip()
                        if len(v) < 1:
                            continue

                        self.pool_mappings[pool_id][sub_k] = v
                        break

                    continue

                v = util.get_json_value(pool_info[p_id], p)
                if v is None:
                    continue
                v = str(v).strip()
                if len(v) < 1:
                    continue
                self.pool_mappings[pool_id][k] = v

    def apply(self, settings, objecttype, field, pool_id):
        if pool_id not in self.pool_mappings:
            return None

        template = util.get_json_value(settings, field)
        for k in self.pool_mappings[pool_id]:
            template = template.replace('%{0}%'.format(k), self.pool_mappings[pool_id][k])

        if '%n%' not in template:
            return template

        # check if there is an offset defined
        start_offset = util.get_json_value(settings, '{0}:start_offset'.format(field))
        if not isinstance(start_offset, int):
            start_offset = 0
        if start_offset < 0:
            start_offset = 0

        # special case: no value from pools but sequential number
        # get a new number from the sequence
        sequence_offset = sequence.get_next_offset(
            PLUGIN_NAME,
            self.api_url,
            self.access_token,
            objecttype,
            field,
            self.sequence_objecttype,
            self.sequence_ref_field,
            self.sequence_num_field
        )
        if sequence_offset is not None:
            template = template.replace('%n%', str(start_offset + sequence_offset))

        return template
