# File: tests/test_login.py

import pytest
from pytapo import Tapo

@pytest.fixture
def tapo_cam():
    return Tapo('YourHost', 'YourUser', 'YourPass')

def test_login(tapo_cam):
    assert tapo_cam.is_logged_in() == True
