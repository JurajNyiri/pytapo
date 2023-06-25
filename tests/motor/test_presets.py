import pytest
from unittest.mock import Mock
from pytapo.error import PresetNotFoundException
from pytapo.motor.presets import PresetInterface


@pytest.fixture
def preset_interface():
    execute_function = Mock()
    return PresetInterface(execute_function)


def test_get_presets(preset_interface):
    preset_interface.executeFunction.return_value = {
        "preset": {"preset": {"name": ["preset1", "preset2"], "id": ["1", "2"]}}
    }
    presets = preset_interface.getPresets()
    assert presets == {"1": "preset1", "2": "preset2"}
    preset_interface.executeFunction.assert_called_once_with(
        "getPresetConfig", {"preset": {"name": ["preset"]}}
    )


def test_save_preset(preset_interface):
    preset_interface.getPresets = Mock()
    preset_interface.savePreset("new_preset")
    preset_interface.executeFunction.assert_called_once_with(
        "addMotorPostion",
        {"preset": {"set_preset": {"name": "new_preset", "save_ptz": "1"}}},
    )
    preset_interface.getPresets.assert_called_once()


def test_delete_preset(preset_interface):
    preset_interface.presets = {"1": "preset1"}
    preset_interface.getPresets = Mock()
    preset_interface.deletePreset("1")
    preset_interface.executeFunction.assert_called_once_with(
        "deletePreset", {"preset": {"remove_preset": {"id": ["1"]}}}
    )
    preset_interface.getPresets.assert_called_once()


def test_delete_preset_not_found(preset_interface):
    preset_interface.presets = {"1": "preset1"}
    with pytest.raises(PresetNotFoundException):
        preset_interface.deletePreset("2")


def test_set_preset(preset_interface):
    preset_interface.presets = {"1": "preset1"}
    result = preset_interface.setPreset("1")
    preset_interface.executeFunction.assert_called_once_with(
        "motorMoveToPreset", {"preset": {"goto_preset": {"id": "1"}}}
    )


def test_set_preset_not_found(preset_interface):
    preset_interface.presets = {"1": "preset1"}
    with pytest.raises(PresetNotFoundException):
        preset_interface.setPreset("2")


def test_is_supporting_presets(preset_interface):
    preset_interface.getPresets = Mock()
    result = preset_interface.isSupportingPresets()
    assert result
    preset_interface.getPresets.assert_called_once()


def test_is_supporting_presets_exception(preset_interface):
    preset_interface.getPresets = Mock(side_effect=Exception())
    result = preset_interface.isSupportingPresets()
    assert not result
    preset_interface.getPresets.assert_called_once()
