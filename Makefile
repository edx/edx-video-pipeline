PACKAGES = VEDA VEDA_OS01 control frontend youtube_callback scripts

validate: test ## Run tests and quality checks

test: clean
	 nosetests --with-coverage --cover-inclusive --cover-branches \
		--cover-html --cover-html-dir=build/coverage/html/ \
		--cover-xml --cover-xml-file=build/coverage/coverage.xml --verbosity=2 \
		$(foreach package,$(PACKAGES),--cover-package=$(package)) \
		$(PACKAGES)

clean:
	coverage erase

quality:
	pep8 --config=.pep8 $(PACKAGES) *.py
	pylint --rcfile=pylintrc $(PACKAGES) *.py
