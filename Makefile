PACKAGES = VEDA VEDA_OS01 control frontend youtube_callback scripts

production-requirements:
	pip install -r requirements.txt

requirements: production-requirements
	pip install -r test_requirements.txt

migrate:
	python manage.py migrate --noinput

static:
	python manage.py collectstatic --noinput

validate: test ## Run tests and quality checks

test: clean
	coverage run -m pytest --durations=10
	coverage combine
	coverage report

clean:
	coverage erase

quality:
	pep8 --config=.pep8 $(PACKAGES) *.py
	pylint --rcfile=pylintrc $(PACKAGES) *.py
