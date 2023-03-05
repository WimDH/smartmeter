import pytest
from smartmeter.utils import parse_cli, convert_from_human_readable, autoformat


@pytest.mark.parametrize(
    "cli_data, cfg_result, test_result, fake_result",
    [
        (
            ["-c", "tests/testdata/sample_config.ini"],
            "tests/testdata/sample_config.ini",
            False,
            None,
        ),
        (
            ["-c", "tests/testdata/sample_config.ini", "-f", "/home/test/blah.txt"],
            "tests/testdata/sample_config.ini",
            False,
            "/home/test/blah.txt",
        ),
    ],
)
def test_parse_cli(cli_data, cfg_result, test_result, fake_result) -> None:
    """Test the parsing of the CLI options."""
    options = parse_cli(cli_args=cli_data)

    assert options.configfile == cfg_result
    assert options.fake_serial == fake_result


@pytest.mark.parametrize(
    "in_value, out_value",
    [
        (1000, 1000),
        ("1010", 1010),
        ("10k", 10240),
        ("10M", 10485760),
        ("10G", 10737418240),
    ],
)
def test_convert_from_human_readable(in_value, out_value) -> None:
    """Test the conversion of ex. 10k to 10240."""
    assert convert_from_human_readable(in_value) == out_value


def test_convert_from_human_readable_fail() -> None:
    """Test when the conversion fails."""
    with pytest.raises(ValueError):
        assert convert_from_human_readable("10m")


@pytest.mark.parametrize(
    "in_value, out_value",
    [
        (1000, 1000),
        ("aaa", "aaa"),
        ("1010", 1010),
        ("10.12", 10.12),
    ],
)
def test_autoformat(in_value, out_value) -> None:
    """Test the autoformat function."""
    assert autoformat(in_value) == out_value
