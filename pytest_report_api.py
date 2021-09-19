#!/usr/bin/env python3
# Copyright(C) 2021 Fridolin Pokorny
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 3 of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program; if not, write to the Free Software Foundation,
# Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

import logging
import os
from typing import Generator
from typing import List
from typing import Optional
from typing import Tuple
from typing import TYPE_CHECKING
from typing import Union
from urllib.parse import urljoin

import pytest
import requests

if TYPE_CHECKING:
    from _pytest.config.argparsing import Parser
    from _pytest.config import Config
    from _pytest.config import ExitCode
    from _pytest.nodes import Item
    from _pytest.runner import CallInfo


# Use logging if users setup their logging handlers.
_LOGGER = logging.getLogger("pytest_report_api")

_DEFAULT_API_URL = "http://localhost:5000"
_REPORT_API_AUTH_TOKEN_DESC = "API authentication token."
_REPORT_API_URL_DESC = "API URL to submit test progress and results."
_REPORT_API_URL_DISABLED_DESC = "Disable reporting tests to API."


def pytest_addoption(parser: "Parser") -> None:
    """Add options and ini configuration entries for this plugin."""
    group = parser.getgroup(
        "report-api",
        "Report results to an API.",
    )
    group.addoption(
        "--report-api-url",
        action="store",
        dest="report_api_url",
        default=None,
        help=_REPORT_API_URL_DESC,
    )
    group.addoption(
        "--report-api-auth-token",
        action="store",
        dest="report_api_auth_token",
        default=None,
        help=_REPORT_API_AUTH_TOKEN_DESC,
    )
    group.addoption(
        "--report-api-disabled",
        action="store_true",
        dest="report_api_disabled",
        help=_REPORT_API_URL_DISABLED_DESC,
    )
    parser.addini("report_api_auth_token", _REPORT_API_AUTH_TOKEN_DESC)
    parser.addini("report_api_url", _REPORT_API_URL_DESC, default=_DEFAULT_API_URL)
    parser.addini("report_api_disabled", _REPORT_API_URL_DESC, type="bool")


def _get_options(config: "Config") -> Tuple[str, Optional[str], bool]:
    """Get configuration options.

    Priority: Options passed to CLI > environment variables > pytest config file
    An exception is "disabled" flag - any level disables the reporting.
    """
    report_api_url = config.getvalue("report_api_url")
    if report_api_url is None:
        report_api_url = (
            os.getenv("PYTEST_REPORT_API_URL", config.getini("report_api_url"))
            or _DEFAULT_API_URL
        )

    report_api_auth_token = config.getvalue("report_api_auth_token")
    if report_api_auth_token is None:
        report_api_auth_token = os.getenv(
            "PYTEST_REPORT_API_AUTH_TOKEN", config.getini("report_api_auth_token")
        )

    report_api_disabled = config.getvalue("report_api_disabled")
    if report_api_disabled is False:
        report_api_disabled = bool(
            int(
                os.getenv(
                    "PYTEST_REPORT_API_DISABLED", config.getini("report_api_disabled")
                )
            )
        )

    return report_api_url, report_api_auth_token, report_api_disabled


def pytest_configure(config: "Config") -> None:
    """Configure the environment."""
    report_api_url, report_api_auth_token, report_api_disabled = _get_options(config)
    config._report_api_url = report_api_url
    config._report_api_auth_token = report_api_auth_token
    config._report_api_disabled = report_api_disabled
    config._report_api_headers = (
        {"Authorization": f"token {report_api_auth_token}"}
        if report_api_auth_token
        else {}
    )


@pytest.hookimpl(tryfirst=True)
def pytest_report_header(config: "Config") -> List[str]:
    """Add info to the pytest header."""
    if not config._report_api_disabled:
        tkn = config._report_api_auth_token
        return [
            f"Tests will be reported to {config._report_api_url!r} (token: {'*' + tkn[:3] if tkn else 'null'})"
        ]
    else:
        return ["Tests will NOT be reported to API"]


@pytest.hookimpl(trylast=True)
def pytest_collection_finish(session: pytest.Session) -> None:
    """Report test session start once all the tests were successfully collected and are ready to be executed."""
    session._run_id = None
    if not session.config._report_api_disabled:
        response = requests.post(
            urljoin(session.config._report_api_url, "runs/"),
            headers=session.config._report_api_headers,
        )
        # Bail if the very first call to the API fails or the response does not conform to the schema.
        # We could also check the status code here.
        response.raise_for_status()
        session._run_id = response.json()["run_id"]


@pytest.hookimpl(tryfirst=True)
def pytest_sessionfinish(
    session: pytest.Session,
    exitstatus: Union[int, "ExitCode"],
) -> None:
    """Report test session end."""
    if session._run_id is not None:
        response = requests.post(
            urljoin(session.config._report_api_url, f"runs/{session._run_id}/finish/"),
            headers=session.config._report_api_headers,
        )
        # Raise if the final finish report was not submitted correctly. We could also check the status code here.
        response.raise_for_status()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(
    item: "Item", call: "CallInfo[None]"
) -> Generator[None, None, None]:
    """Report each test progress and outcome."""
    # Hook only in the setup phase.
    if call.when == "setup" and item.session._run_id is not None:
        config = item.session.config

        response = requests.post(
            urljoin(config._report_api_url, "tests/"),
            json={"name": item.name},
            headers=config._report_api_headers,
        )

        test_id = None
        if response.status_code != 201:
            _LOGGER.error(
                "Invalid response from the report API (%d): %s ",
                response.status_code,
                response.text,
            )
        else:
            test_id = response.json().get("test_id")
            if test_id is None:
                _LOGGER.error(
                    "No test id provided in the report API response for test %r: %s",
                    item.name,
                    response.text,
                )

        outcome = yield
        report = outcome.get_result()

        if test_id is not None:
            response = requests.post(
                urljoin(item.session.config._report_api_url, f"tests/{test_id}/finish"),
                json={"status": report.outcome.upper()},
                headers=config._report_api_headers,
            )
            if response.status_code != 204:
                _LOGGER.error(
                    "The test %r with test_id %r was not properly finished: %s",
                    item.name,
                    test_id,
                    response.text,
                )
    else:
        yield
