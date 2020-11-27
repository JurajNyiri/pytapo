import os
import pytest
from pytapo import Tapo

user = os.environ.get("PYTAPO_USER")
password = os.environ.get("PYTAPO_PASSWORD")
host = os.environ.get("PYTAPO_IP")


def test_authentication_success():
    tapo = Tapo(host, user, password)
    result = tapo.refreshStok()
    assert isinstance(result, str)


def test_authentication_failure():
    with pytest.raises(Exception) as err:
        tapo = Tapo(host, user, password + "_not_valid")
        tapo.refreshStok()
    assert "Invalid authentication data." in str(err.value)
