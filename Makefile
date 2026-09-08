.PHONY: test lint doctor

test:
	python3 -m unittest discover -s tests -p 'test_*.py'
	bash tests/test_cli.sh
	bash tests/test_project_value.sh
	bash -n bin/awo scripts/*.sh

lint:
	shellcheck bin/awo scripts/*.sh

doctor:
	./bin/awo doctor
