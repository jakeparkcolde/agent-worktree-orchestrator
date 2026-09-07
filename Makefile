.PHONY: test lint doctor

test:
	bash tests/test_cli.sh
	bash tests/test_project_value.sh
	bash -n bin/awo scripts/*.sh

lint:
	shellcheck bin/awo scripts/*.sh

doctor:
	./bin/awo doctor
