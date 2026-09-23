from runtime.config.settings import get_settings


def test_settings_defaults():
    s = get_settings()
    assert s.env == "dev"
    assert s.sqlite_path == "./sec_investigator.db"
    assert s.plus_model_name  # provider-specific model name is set
