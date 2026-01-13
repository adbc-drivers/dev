# Copyright (c) 2025 ADBC Drivers Contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import pytest

from adbc_drivers_dev.workflow import Params


def test_params_default() -> None:
    params = Params({})
    assert params.driver == "(unknown)"
    assert params.environment is None
    assert params.private is False
    assert params.lang == {}
    assert params.secrets == {
        "all": {},
        "build:release": {},
        "test": {},
        "validate": {},
    }
    assert params.permissions == {}
    assert params.aws == {}
    assert params.gcloud is False
    assert params.validation == {"extra_dependencies": {}}

    assert params.to_dict() == {
        "driver": "(unknown)",
        "environment": None,
        "private": False,
        "lang": {},
        "secrets": {
            "all": {},
            "build:release": {},
            "test": {},
            "validate": {},
        },
        "permissions": {},
        "aws": {},
        "gcloud": False,
        "validation": {"extra_dependencies": {}},
    }

    assert params == Params({})


def test_params_custom() -> None:
    params = Params({"driver": "postgresql"})
    assert params.driver == "postgresql"
    assert params.to_dict()["driver"] == "postgresql"
    assert params == params
    assert params != Params({})

    params = Params({"environment": "ci-env"})
    assert params.environment == "ci-env"
    assert params.to_dict()["environment"] == "ci-env"
    assert params == params
    assert params != Params({})

    params = Params({"private": True})
    assert params.private is True
    assert params.to_dict()["private"] is True
    assert params == params
    assert params != Params({})

    params = Params({"lang": {"python": True, "java": False}})
    assert params.lang == {"python": True, "java": False}
    assert params.to_dict()["lang"] == {"python": True, "java": False}
    assert params == params
    assert params != Params({})


def test_params_secrets() -> None:
    params = Params(
        {
            "secrets": {
                "foo": "bar",
                "spam": {"secret": "eggs"},
                "fizz": {"secret": "buzz", "contexts": ["test", "validate"]},
            }
        }
    )
    assert params.secrets == {
        "all": {"foo": "bar", "spam": "eggs", "fizz": "buzz"},
        "build:release": {"foo": "bar", "spam": "eggs"},
        "test": {"foo": "bar", "spam": "eggs", "fizz": "buzz"},
        "validate": {"foo": "bar", "spam": "eggs", "fizz": "buzz"},
    }
    assert params.to_dict()["secrets"] == {
        "all": {"foo": "bar", "spam": "eggs", "fizz": "buzz"},
        "build:release": {"foo": "bar", "spam": "eggs"},
        "test": {"foo": "bar", "spam": "eggs", "fizz": "buzz"},
        "validate": {"foo": "bar", "spam": "eggs", "fizz": "buzz"},
    }


def test_params_aws() -> None:
    params = Params({"aws": {"region": "us-west-2"}})
    assert params.aws == {"region": "us-west-2"}
    assert params.permissions == {"id_token": True}
    assert params.to_dict()["permissions"] == {"id_token": True}
    assert params.secrets == {
        "all": {
            "AWS_ROLE": "AWS_ROLE",
            "AWS_ROLE_SESSION_NAME": "AWS_ROLE_SESSION_NAME",
        },
        "build:release": {},
        "test": {},
        "validate": {},
    }
    assert params.to_dict()["secrets"] == {
        "all": {
            "AWS_ROLE": "AWS_ROLE",
            "AWS_ROLE_SESSION_NAME": "AWS_ROLE_SESSION_NAME",
        },
        "build:release": {},
        "test": {},
        "validate": {},
    }


def test_params_gcloud() -> None:
    params = Params({"gcloud": True})
    assert params.gcloud is True
    assert params.permissions == {"id_token": True}
    assert params.to_dict()["permissions"] == {"id_token": True}
    assert params.secrets == {
        "all": {
            "GCLOUD_SERVICE_ACCOUNT": "GCLOUD_SERVICE_ACCOUNT",
            "GCLOUD_WORKLOAD_IDENTITY_PROVIDER": "GCLOUD_WORKLOAD_IDENTITY_PROVIDER",
        },
        "build:release": {},
        "test": {},
        "validate": {},
    }
    assert params.to_dict()["secrets"] == {
        "all": {
            "GCLOUD_SERVICE_ACCOUNT": "GCLOUD_SERVICE_ACCOUNT",
            "GCLOUD_WORKLOAD_IDENTITY_PROVIDER": "GCLOUD_WORKLOAD_IDENTITY_PROVIDER",
        },
        "build:release": {},
        "test": {},
        "validate": {},
    }


def test_params_invalid() -> None:
    with pytest.raises(TypeError):
        Params({"private": ""})

    with pytest.raises(TypeError):
        Params({"environment": 2})

    with pytest.raises(ValueError):
        Params({"environment": ""})

    with pytest.raises(ValueError):
        Params(
            {
                "secrets": {
                    "fizz": {
                        "secret": "buzz",
                        "contexts": ["test", "validate"],
                        "foo": "bar",
                    },
                }
            }
        )

    with pytest.raises(KeyError):
        Params(
            {
                "secrets": {
                    "fizz": {"secret": "buzz", "contexts": ["asdf"], "foo": "bar"},
                }
            }
        )


def test_params_unknown() -> None:
    with pytest.raises(ValueError):
        Params({"unknown_key": "value"})

    with pytest.raises(KeyError):
        Params({"aws": {"foo": "bar"}})

    with pytest.raises(ValueError):
        Params({"aws": {"region": "foo", "foo": "bar"}})
