import os
import pytest
import json
from pytapo import Tapo

user = os.environ.get("PYTAPO_USER")
password = os.environ.get("PYTAPO_PASSWORD")
invalidPassword = "{password}_invalid".format(password=password)
host = os.environ.get("PYTAPO_IP")


def test_refreshStok_success():
    tapo = Tapo(host, user, password)
    result = tapo.refreshStok()
    assert isinstance(result, str)


def test_refreshStok_failure():
    with pytest.raises(Exception) as err:
        tapo = Tapo(host, user, invalidPassword)
        tapo.refreshStok()
    assert "Invalid authentication data." in str(err.value)


def test_getHostURL():
    tapo = Tapo(host, user, password)
    hostURL = tapo.getHostURL()
    assert "https://{host}/stok=".format(host=host) in hostURL
    assert "/ds" in hostURL


def test_ensureAuthenticated():
    tapo = Tapo(host, user, password)
    result = tapo.ensureAuthenticated()
    assert result is True


def test_responseIsOK_success():
    tapo = Tapo(host, user, password)

    class AttributeDict(dict):
        status_code = 200
        text = '{"error_code":0}'

        def json(self):
            return json.loads(self.text)

    result = tapo.responseIsOK(AttributeDict())
    assert result is True


def test_responseIsOK_failure():
    tapo = Tapo(host, user, password)

    class AttributeDict(dict):
        status_code = 200
        text = '{"error_code":404}'

        def json(self):
            return json.loads(self.text)

    result = tapo.responseIsOK(AttributeDict())
    assert result is False

    class AttributeDict(dict):
        status_code = 200
        text = "not json"

        def json(self):
            return json.loads(self.text)

    with pytest.raises(Exception) as err:
        result = tapo.responseIsOK(AttributeDict())

    assert "Unexpected response from Tapo Camera: " in str(err.value)

    class AttributeDict(dict):
        status_code = 404
        text = "not json"

        def json(self):
            return json.loads(self.text)

    with pytest.raises(Exception) as err:
        tapo.responseIsOK(AttributeDict())

    assert "Error communicating with Tapo Camera. Status code: 404" == str(err.value)


def test_performRequest_failure():
    tapo = Tapo(host, user, password)
    with pytest.raises(Exception) as err:
        tapo.performRequest({"invalidData": "test123"})
    assert (
        'Error: -40210 Response:{"result": {"responses": []}, "error_code": -40210}'
        == str(err.value)
    )


def test_performRequest_invalidStok():
    tapo = Tapo(host, user, password)
    tapo.stok = "invalidStok"
    result = tapo.getOsd()
    assert "OSD" in result
    assert result["error_code"] == 0


def test_getOsd():
    tapo = Tapo(host, user, password)
    result = tapo.getOsd()
    assert "OSD" in result
    assert result["error_code"] == 0
