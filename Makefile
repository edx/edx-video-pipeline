PEP8_THRESHOLD=51
PYLINT_THRESHOLD=760

production-requirements:
	pip install -r requirements/base.txt

requirements: production-requirements
	pip install -r requirements/test.txt

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

quality: 
	tox -e quality

quality_pep8:
	paver run_pep8 -l ${PEP8_THRESHOLD}

quality_pylint:
	paver run_pylint -l ${PYLINT_THRESHOLD}


upgrade: export CUSTOM_COMPILE_COMMAND=make upgrade
upgrade: ## update the requirements/*.txt files with the latest packages satisfying requirements/*.in
	pip install -qr requirements/pip-tools.txt
	# Make sure to compile files after any other files they include!
	pip-compile --upgrade -o requirements/pip-tools.txt requirements/pip-tools.in
	pip-compile --upgrade -o requirements/base.txt requirements/base.in
	pip-compile --upgrade -o requirements/test.txt requirements/test.in
	pip-compile --upgrade -o requirements/travis.txt requirements/travis.in
	pip-compile --upgrade -o requirements/quality.txt requirements/quality.in
	# Let tox control the Django version for tests
	sed '/^[dD]jango==/d' requirements/test.txt > requirements/test.tmp
	mv requirements/test.tmp requirements/test.txt

