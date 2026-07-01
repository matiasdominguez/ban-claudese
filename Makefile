.PHONY: test install

test:
	python3 tests/test_lint.py
	bash tests/test_install.sh

install:
	./install.sh
