PLUGIN_NAME = fylr-sequence-plugin

L10N_FILES = l10n/$(PLUGIN_NAME).csv
L10N_GOOGLE_KEY = 1xHXOhEdya6h2zX0Gw6Dm_J5UUWtsgLPCeeTkBui3IZ0
L10N_GOOGLE_GID = 0


INSTALL_FILES = \
	$(WEB)/l10n/cultures.json \
	$(WEB)/l10n/de-DE.json \
	$(WEB)/l10n/en-US.json \
	src/server/insert_sequence.py \
	src/server/sequence.py \
	$(JS) \
	manifest.yml


COFFEE_FILES = src/webfrontend/SequencePluginBaseConfig.coffee


all: google_csv build

include easydb-library/tools/base-plugins.make

build: code $(L10N) buildinfojson

code: $(JS)

clean: clean-base
	rm -f src/server/*.pyc

wipe: wipe-base


apitest-dep:
	go install github.com/programmfabrik/apitest@latest

apitest: apitest-dep
	# Use APITEST to configure the apitest binary to use for the apitests
	# This defaults to "apitest" in your PATH
	#
	# Use APITEST_PARAMS to configure a different server connection
	# export APITEST_PARAMS="--server http://root:admin@localhost:8080/api/v1"

	echo "-d apitest" | xargs $(APITEST) $(APITEST_PARAMS)
