"""FlexibleEnum : one value out for the device, several values in for the user"""

import json
import pickle

import pytest

from syndesi import FlexibleEnum


class VoltageRange(FlexibleEnum):
    _200mV = "200MV", 0.2, "200mV", "0.2V"
    _2V = "R1", 2, "2V"
    _1000V = "R4", 1000, "1000V", "1kV"
    AUTO = "AUTO"


class Resistance(FlexibleEnum):
    MILLI = "RM", "2mΩ"
    MEGA = "RG", "2MΩ"


class Function(FlexibleEnum, case_sensitive=True):
    VOLTAGE = "VOLT", "Voltage"


@pytest.mark.parametrize(
    "value, member",
    [
        # Text, without spaces and case
        ("200mV", VoltageRange._200mV),
        ("200 mv", VoltageRange._200mV),
        ("0.2 V", VoltageRange._200mV),
        ("2v", VoltageRange._2V),
        ("1KV", VoltageRange._1000V),
        ("auto", VoltageRange.AUTO),
        # The value out and the name
        ("R1", VoltageRange._2V),
        ("r1", VoltageRange._2V),
        ("_2V", VoltageRange._2V),
        # Numbers, and numeric text such as a device reply
        (0.2, VoltageRange._200mV),
        ("0.2", VoltageRange._200mV),
        ("+2.000000E-01", VoltageRange._200mV),
        (2, VoltageRange._2V),
        (1e3, VoltageRange._1000V),
        # A member is itself
        (VoltageRange._2V, VoltageRange._2V),
    ],
)
def test_lookup(value, member):
    assert VoltageRange(value) is member


def test_micro_sign_and_greek_mu_are_the_same():
    class Current(FlexibleEnum):
        _2uA = "2E-6", "2µA"  # micro sign, U+00B5

    assert Current("2μA") is Current._2uA  # greek mu


def test_value_out():
    member = VoltageRange("2 V")
    assert member == "R1"
    assert f"RANGE {member}" == "RANGE R1"
    assert isinstance(member, str)
    assert json.dumps(member) == '"R1"'
    assert pickle.loads(pickle.dumps(member)) is member


def test_label():
    assert VoltageRange._200mV.label == "200mV"
    assert VoltageRange.AUTO.label == "AUTO"


def test_unknown_lists_the_labels():
    with pytest.raises(ValueError, match=r"15 is not a VoltageRange, use one of : 200mV, 2V"):
        VoltageRange(15)
    with pytest.raises(ValueError, match="is not a VoltageRange"):
        VoltageRange("2 A")
    with pytest.raises(ValueError):
        VoltageRange(True)


def test_case_decides_when_it_matters():
    assert Resistance("2mΩ") is Resistance.MILLI
    assert Resistance("2 MΩ") is Resistance.MEGA
    # Ω and ω : both members, without the case
    with pytest.raises(ValueError, match="could be 2mΩ or 2MΩ .* write it with its case"):
        Resistance("2mω")


def test_case_sensitive():
    assert Function("VOLT") is Function.VOLTAGE
    assert Function("Voltage") is Function.VOLTAGE
    with pytest.raises(ValueError):
        Function("volt")


def test_value_accepted_twice_is_a_typo():
    with pytest.raises(TypeError, match="2.0 is accepted by both A and B"):

        class Typo(FlexibleEnum):  # pylint: disable=unused-variable
            A = "R1", 2
            B = "R2", 2.0


def test_value_out_is_text():
    with pytest.raises(TypeError, match="the value out must be text, not 2"):

        class Numbers(FlexibleEnum):  # pylint: disable=unused-variable
            A = 2, "2V"
