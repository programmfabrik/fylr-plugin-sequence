class SequencePluginPoolNode extends ListViewEditTreeNode

	constructor: (@opts={}) ->
		@opts.fields = @getFieldDefs()
		super(@opts)

	getFieldDefs: ->
		[
			type: CUI.Input
			placeholder: "Template"
			name: "template"
		,
			type: CUI.Input
			placeholder: "Offset"
			name: "start_offset"
			checkInput: (value) ->
				if value.match(/^[0-9]*$/)
					return true
				return false
		,
			type: CUI.DataFieldProxy
			name: "objecttype"
			element: (df) =>
				data = df.getData()
				field = new ez5.ObjecttypeSelector
					data: data
					name: "objecttype"
					show_name: true
					store_value: "fullname"
					filter: (objecttype) ->
						if not objecttype.poolLink()
							return false

						mask = Mask.getMaskByMaskName("_all_fields", objecttype.table.id())
						if not mask
							return false

						objecttype.addMask(mask)

						hasStringField = objecttype.getFields().some((field) -> field instanceof TextColumn)

						return hasStringField
				return field.start()
		,
			type: CUI.DataFieldProxy
			name: "field"
			element: (df) =>
				data = df.getData()
				fieldSelector = new ez5.FieldSelector
					objecttype_data_key: "objecttype"
					store_value: "name"
					name: "field"
					data: data
					show_name: true
					filter: (field) ->
						return field instanceof TextColumn and not field.isSystemField()

				return fieldSelector.start()
		,
			type: CUI.Checkbox
			placeholder: "Only Insert"
			name: "only_insert"
		]



