PACKAGES = VEDA VEDA_OS01 control frontend youtube_callback scripts

requirements:
	pip install -r requirements.txt
	pip install -r test_requirements.txt

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
