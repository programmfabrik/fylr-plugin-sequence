class ez5.SequencePluginPool extends ez5.PoolPlugin


	getTabs: (tabs) ->
		tabs.push
			name: "sequence-plugin-pool"
			text: $$("sequence-plugin-pool|text")
			content: =>
				# xxx
				tb = new CUI.Table
					data: @_pool.data.pool
					name: "custom_data"
					columns: [
						name: $$("sequence-plugin-pool.value_template")
					,
						name: $$("sequence-plugin-pool.object_type")
					,
						name: $$("sequence-plugin-pool.value_template|text")
					,
				]

				return tb

		return tabs



	getSaveData: (save_data) ->
		# todo
		return

Pool.plugins.registerPlugin(ez5.SequencePluginPool)
