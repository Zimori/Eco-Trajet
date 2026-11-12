.PHONY: seed test backend-test frontend-test run osrm-download osrm-data

seed:
	python backend/scripts/seed_data.py

backend-test:
	PYTHONPATH=backend python -m pytest backend/tests

frontend-test:
	npm test -- --runInBand

test: backend-test frontend-test

run:
	docker compose up --build

osrm-download:
	backend/scripts/osrm_prepare.sh download

osrm-data:
	backend/scripts/osrm_prepare.sh build
