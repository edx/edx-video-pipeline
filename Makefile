PEP8_THRESHOLD=46
PYLINT_THRESHOLD=761

production-requirements:
	pip install -r requirements.txt

requirements: production-requirements
	pip install -r test_requirements.txt

migrate:
	python manage.py migrate --noinput

static:
	python manage.py collectstatic --noinput

validate: test quality

test: clean
	coverage run -m pytest --durations=10
	coverage combine
	coverage report

clean:
	coverage erase

quality: quality_pep8 quality_pylint

quality_pep8:
	paver run_pep8 -l ${PEP8_THRESHOLD}

quality_pylint:
	paver run_pylint -l ${PYLINT_THRESHOLD}
