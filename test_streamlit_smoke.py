"""UAT smoke test for the deployed Streamlit entry point."""
from pathlib import Path

import firebase_admin
from streamlit.testing.v1 import AppTest

from test_execution_confirmed_contract import _execution_fixture


def test_app_starts_without_firebase_secrets_and_keeps_two_tab_ui():
    app = AppTest.from_file(str(Path(__file__).with_name("streamlit_app.py")))
    app.run(timeout=20)

    assert not app.exception
    assert len(app.title) == 1
    assert len(app.tabs) == 2
    # The educational tab remains usable while the live tab explains that
    # Firebase secrets are absent. These counts protect its existing inputs.
    assert len(app.info) >= 1
    assert len(app.number_input) == 6
    assert len(app.text_input) == 1


def test_live_execution_dashboard_renders_with_mocked_read_only_firebase(
        monkeypatch):
    rows = _execution_fixture()
    chain = str(rows.iloc[0]["chain_key"])
    payloads = {
        "webull_lego_rows": {
            str(row["run_id"]): row.to_dict() for _, row in rows.iterrows()
        },
        "webull_lego_state": {
            chain: {"p0": 100.0, "updated_at": "2026-08-01T15:00:00Z"}
        },
        "webull_lego_order_audit": {},
    }

    class _Reference:
        def __init__(self, path):
            self.path = path

        def get(self):
            return payloads.get(self.path)

    monkeypatch.setattr(firebase_admin, "_apps", {"test": object()})
    monkeypatch.setattr(firebase_admin.db, "reference", _Reference)
    app = AppTest.from_file(str(Path(__file__).with_name("streamlit_app.py")))
    app.secrets.update({
        "FIREBASE_SA_JSON": "{}",
        "FIREBASE_DB_URL": "https://mock.firebaseio.test",
    })

    app.run(timeout=20)

    assert not app.exception
    assert len(app.tabs) == 2
    metric_labels = {item.label for item in app.metric}
    assert {"สถานะตัดสินใจล่าสุด", "DNA step", "Pₙ (USD)",
            "Eₙ สะสม (USD)"}.issubset(metric_labels)
    assert any("Execution cashflow ล่าสุด" in item.value for item in app.caption)
    assert any("execution_confirmed_v1" in item.value for item in app.caption)
    # State pointer, 17-column table, and integrity report all rendered.
    assert len(app.dataframe) >= 3

