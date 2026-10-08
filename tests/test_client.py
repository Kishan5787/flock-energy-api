from app.client import UrjaPortalClient
from app.config import Settings


def test_summary_normalizes_portal_keys():
    result = UrjaPortalClient._summary(
        {
            "meterId": "J100000",
            "serialNo": "SE33962",
            "make": "HPL",
            "phaseType": "single",
            "installStatus": "Installed",
            "dtCode": "DT-001",
        }
    )
    assert result.meter_id == "J100000"
    assert result.serial_number == "SE33962"
    assert result.transformer_code == "DT-001"


def test_detail_parser_extracts_nameplate_and_network():
    html = """
    <main><nav><span>Jaipur Zone 1 (Z-01)</span><span>Circle 1 (C-01)</span>
    <span>Division 1 (D-01)</span><span>Subdivision 1 (SD-01)</span>
    <span>Feeder 1 (F-001)</span><span>Malviya Nagar DT 1 (DT-001)</span></nav>
    <dl><dt>Installation Type</dt><dd>Whole Current</dd></dl></main>
    """
    summary = UrjaPortalClient._summary({"meterId": "J100000", "serialNo": "SE33962"})
    result = UrjaPortalClient._parse_detail(html, summary)
    assert result.installation_type == "Whole Current"
    assert result.network.zone == "Jaipur Zone 1 (Z-01)"
    assert result.network.feeder == "Feeder 1 (F-001)"


def test_settings_read_credentials_from_environment(monkeypatch):
    monkeypatch.setenv("PORTAL_USERNAME", "operator@urja.local")
    monkeypatch.setenv("PORTAL_PASSWORD", "secret")
    settings = Settings()
    assert settings.portal_username == "operator@urja.local"
    assert settings.portal_password.get_secret_value() == "secret"
