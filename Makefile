.PHONY: test dev dev-real smoke deploy

test:
	PYTHONPATH=src python3 -m unittest discover -s tests -v

dev:
	python3 scripts/dev_server.py --mock

dev-real:
	python3 scripts/dev_server.py

smoke:
	python3 scripts/http_smoke_test.py --base-url http://127.0.0.1:8000

deploy: test
	git push origin master
