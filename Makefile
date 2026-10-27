.PHONY: seed test backend-test frontend-test run

seed:
	python backend/scripts/seed_data.py

backend-test:
	PYTHONPATH=backend python -m pytest backend/tests

frontend-test:
	npm test -- --runInBand

test: backend-test frontend-test

run:
	docker compose up --build
