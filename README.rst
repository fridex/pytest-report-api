pytest-report-api
-----------------

A simple pytest plugin which reports progress and results of tests to an API.

This project is a toy project used as a Python coding exercise.

Usage
=====

The plugin is automatically registered to pytest once installed:

.. code-block:: console

  pip install git+https://github.com/fridex/pytest-report-api


Configuration
=============

The tool accepts `standard configuration formats as consumed by pytest <https://docs.pytest.org/en/6.2.x/customize.html#configuration-file-formats>`__.

**Configuration options:**

* ``report_api_url`` - URL to the API service accepting progress and test results
* ``report_api_auth_token`` - Auth token to be used when communicating with API
* ``report_api_disabled`` - a flag to disable this plugin

The plugin accepts options passed to pytest, see ``pytest --help`` for more info.

It is also possible to use environment variables - ``PYTEST_REPORT_API_URL``, ``PYTEST_REPORT_API_AUTH_TOKEN``, ``PYTEST_REPORT_API_DISABLED``

The priority for accepted options:

1. Options passed from the command line
2. Options passed via environment variables
3. Options passed from the configuration file
