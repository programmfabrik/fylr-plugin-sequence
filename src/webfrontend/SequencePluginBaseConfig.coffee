class SequencePluginBaseConfig extends BaseConfigPlugin
    getFieldDefFromParm: (baseConfig, fieldName, def) ->

        getMask = (idTable) ->
            if CUI.util.isString(idTable)
                return false
            return Mask.getMaskByMaskName("_all_fields", idTable)

        filterTextField = (field) ->
            return field instanceof TextColumn and
                field not instanceof NestedTable and
                field not instanceof NumberColumn and
                field not instanceof LocaTextColumn and
                not field.isTopLevelField() and
                not field.insideNested()

        filterNumberField = (field) =>
            return field instanceof NumberColumn and
                not field.isTopLevelField() and
                not field.insideNested()

        switch def.plugin_type

            when "update_objecttype"
                field = new ez5.ObjecttypeSelector
                    form: label: $$("server.config.parameter.system.fylr-sequence-plugin.insert_sequence.objecttypes.objecttype_settings.update_objecttype.label")
                    name: fieldName
                    show_name: true
                    store_value: "fullname"
                    filter: (objecttype) ->
                        mask = getMask(objecttype.table.id())
                        if not mask
                            return false

                        objecttype.addMask(mask)

                        hasTextField = objecttype.getFields().some((field) -> field instanceof TextColumn)

                        return hasTextField

            when "update_column"
                field = new ez5.FieldSelector
                    form: label: $$("server.config.parameter.system.fylr-sequence-plugin.insert_sequence.objecttypes.objecttype_settings.update_column.label")
                    name: fieldName
                    objecttype_data_key: "update_objecttype"
                    store_value: "fullname"
                    show_name: true
                    filter: filterTextField

            when "sequence_objecttype"
                field = new ez5.ObjecttypeSelector
                    form: label: $$("server.config.name.system.fylr-sequence-plugin.insert_sequence.sequence.sequence_objecttype.label")
                    name: fieldName
                    show_name: true
                    store_value: "fullname"
                    filter: (objecttype) ->
                        mask = getMask(objecttype.table.id())
                        if not mask
                            return false

                        objecttype.addMask(mask)

                        hasRefField = objecttype.getFields().some((field) -> field instanceof TextColumn)
                        hasNumField = objecttype.getFields().some((field) -> field instanceof NumberColumn)

                        return hasRefField and hasNumField

            when "sequence_ref_field"
                field = new ez5.FieldSelector
                    form: label: $$("server.config.name.system.fylr-sequence-plugin.insert_sequence.sequence.sequence_ref_field.label")
                    name: fieldName
                    objecttype_data_key: "sequence_objecttype"
                    store_value: "fullname"
                    show_name: true
                    filter: filterTextField

            when "sequence_num_field"
                field = new ez5.FieldSelector
                    form: label: $$("server.config.name.system.fylr-sequence-plugin.insert_sequence.sequence.sequence_num_field.label")
                    name: fieldName
                    objecttype_data_key: "sequence_objecttype"
                    store_value: "fullname"
                    show_name: true
                    filter: filterNumberField

        return field

ez5.session_ready =>
    BaseConfig.registerPlugin(new SequencePluginBaseConfig())