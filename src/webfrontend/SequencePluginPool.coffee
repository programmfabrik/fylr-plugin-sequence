class ez5.SequencePluginPool extends ez5.PoolPlugin

	initOpts: ->
		super()
		@data = @opts.pool?._pool?.pool?.custom_data?.sequence_plugin or []

		return

	getTabs: (tabs) ->
		tabs.push
			name: "sequence-plugin-pool"
			text: "Sequence"
			content: =>
				@getTabContent()

		return tabs

	getTabContent: ->
		@tree = new ListViewEditTree
			fixedRows: 1
			class: 'cui-lv--has-datafields'
			cols: ["maximize","auto","auto","auto","auto"]
			rowMove: false
			selectableRows: true
			fields: [
				th_label: "sequence-plugin-pool.template"
			,
				th_label: "sequence-plugin-pool.start_offset"
			,
				th_label: "sequence-plugin-pool.objecttype"
			,
				th_label: "sequence-plugin-pool.field"
			,
				th_label: "sequence-plugin-pool.only_insert"
			]
			footer_left: [
				icon: "plus"
				loca_key: "tag.form.list.plus"
				group: "plus-minus"
				onClick: =>
					@addSequenceNode()
			,
				icon: "minus"
				loca_key: "tag.form.list.minus"
				ui: "tag.form.remove.button"
				group: "plus-minus"
				onClick: =>
					@removeSequenceNode()
			]

		@tree.render()
		@__sequenceNodes = []

		#If we have loaded sequences from db then we load them into the listview.
		if @data.length > 0
			for sequenceData in @data
				sequence = new SequencePluginPoolNode(data: sequenceData)
				@__sequenceNodes.push(sequence)

		@tree.load_data(@__sequenceNodes)

		return @tree

	addSequenceNode: ->
		sequenceData = {}
		@data.push(sequenceData)
		sequence = new SequencePluginPoolNode(data: sequenceData)
		@tree.addNode(sequence)
		CUI.Events.trigger
			type: "data-changed"
			node: @tree

	removeSequenceNode: ->
		selectedNode = @tree.getSelectedNode()
		if not selectedNode
			return

		selectedNode.remove(false, false)
		updatedData = []
		for node in @tree.nodes
			updatedData.push(node.getData())
		@data = updatedData

		CUI.Events.trigger
			type: "data-changed"
			node: @tree

	getSaveData: (save_data) ->
		if not @__canSave()
			throw new InvalidSaveDataException()

		_data = CUI.util.copyObject(@data, true)
		save_data.pool.custom_data =
			sequence_plugin : _data
		return save_data

	# Return false if any of the sequence has an empty property.
	__canSave: ->
		for sequence in @data
			if CUI.util.isEmpty(sequence.template) or CUI.util.isEmpty(sequence.objecttype) or CUI.util.isEmpty(sequence.field)
				return false
		return true

Pool.plugins.registerPlugin(ez5.SequencePluginPool)
