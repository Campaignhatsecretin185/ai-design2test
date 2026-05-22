.PHONY: run test docker-build

run:
	python3 -m ai_test_platform.server

test:
	python3 -m unittest discover -s tests

docker-build:
	docker build -t ai-app-test-platform .

