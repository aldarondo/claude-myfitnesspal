"""
Unit tests for mfp_server.py.

Playwright and browser calls are fully mocked — no browser is launched
and no MFP session is required.
"""

import json
import datetime
from unittest.mock import MagicMock

import pytest

import mfp_server


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_response(
    ok: bool = True,
    status: int = 200,
    content_type: str = "application/json",
    text: str = '{"ok": true}',
    json_data: dict | None = None,
):
    """Return a mock Playwright APIResponse."""
    resp = MagicMock()
    resp.ok = ok
    resp.status = status
    resp.headers = {"content-type": content_type}
    resp.text.return_value = text
    if json_data is not None:
        resp.json.return_value = json_data
    elif "application/json" in content_type:
        resp.json.return_value = json.loads(text)
    else:
        resp.json.side_effect = ValueError("not JSON")
    return resp


# ---------------------------------------------------------------------------
# _get_bearer_token
# ---------------------------------------------------------------------------

class TestGetBearerToken:
    def test_returns_access_token_on_success(self, mocker):
        ctx = MagicMock()
        ctx.request.get.return_value = _make_response(
            ok=True,
            content_type="application/json",
            text='{"access_token": "abc123"}',
            json_data={"access_token": "abc123"},
        )
        token = mfp_server._get_bearer_token(ctx)
        assert token == "abc123"

    def test_raises_on_non_ok_response(self, mocker):
        ctx = MagicMock()
        ctx.request.get.return_value = _make_response(ok=False, status=401)
        with pytest.raises(RuntimeError, match="MFP auth failed"):
            mfp_server._get_bearer_token(ctx)

    def test_raises_on_non_json_content_type(self, mocker):
        ctx = MagicMock()
        ctx.request.get.return_value = _make_response(
            ok=True, content_type="text/html", text="<html></html>"
        )
        with pytest.raises(RuntimeError, match="non-JSON"):
            mfp_server._get_bearer_token(ctx)


# ---------------------------------------------------------------------------
# Fixtures shared by tool tests
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _patch_browser(mocker):
    """Prevent _init_browser from launching Chromium."""
    mocker.patch("mfp_server._init_browser")
    mocker.patch("mfp_server._browser", MagicMock())


@pytest.fixture()
def mock_ctx(mocker):
    """Patch _get_context to return a fresh MagicMock BrowserContext."""
    ctx = MagicMock()
    mocker.patch("mfp_server._get_context", return_value=ctx)
    return ctx


@pytest.fixture()
def mock_token(mocker):
    """Patch _get_bearer_token to return a stable fake token."""
    mocker.patch("mfp_server._get_bearer_token", return_value="test-token")


# ---------------------------------------------------------------------------
# get_diary
# ---------------------------------------------------------------------------

class TestGetDiary:
    def test_returns_response_text_on_success(self, mock_ctx, mock_token):
        body = '{"diary": "data"}'
        mock_ctx.request.get.return_value = _make_response(
            ok=True, content_type="application/json", text=body
        )
        result = mfp_server.get_diary("2024-01-15")
        assert result == body

    def test_falls_back_to_next_data_scrape_on_non_json(self, mock_ctx, mock_token):
        # API returns non-JSON
        mock_ctx.request.get.return_value = _make_response(
            ok=True, content_type="text/html", text="<html></html>"
        )
        next_data = {"props": {"pageProps": {"meals": []}}}
        page = MagicMock()
        page.evaluate.return_value = next_data
        mock_ctx.new_page.return_value = page

        result = mfp_server.get_diary("2024-01-15")
        parsed = json.loads(result)
        assert parsed == {"meals": []}

    def test_returns_error_json_on_exception(self, mock_ctx, mock_token):
        mock_ctx.request.get.side_effect = Exception("network error")
        result = mfp_server.get_diary("2024-01-15")
        parsed = json.loads(result)
        assert "error" in parsed
        assert "network error" in parsed["error"]


# ---------------------------------------------------------------------------
# get_measurements
# ---------------------------------------------------------------------------

class TestGetMeasurements:
    def test_passes_correct_params(self, mock_ctx, mock_token):
        body = '{"measurements": []}'
        mock_ctx.request.get.return_value = _make_response(
            ok=True, content_type="application/json", text=body
        )
        mfp_server.get_measurements("Waist", "2024-01-01", "2024-01-31")
        call_kwargs = mock_ctx.request.get.call_args
        params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params") or call_kwargs[0][1]
        assert params["name"] == "Waist"
        assert params["from"] == "2024-01-01"
        assert params["to"] == "2024-01-31"

    def test_returns_response_text_on_success(self, mock_ctx, mock_token):
        body = '{"measurements": [{"date": "2024-01-01", "value": 185}]}'
        mock_ctx.request.get.return_value = _make_response(
            ok=True, content_type="application/json", text=body
        )
        result = mfp_server.get_measurements("Weight")
        assert result == body

    def test_falls_back_to_page_scrape_on_non_json(self, mock_ctx, mock_token):
        mock_ctx.request.get.return_value = _make_response(
            ok=True, content_type="text/html", text="<html></html>"
        )
        next_data = {"measurements": {"Weight": []}}
        page = MagicMock()
        page.evaluate.return_value = next_data
        mock_ctx.new_page.return_value = page

        result = mfp_server.get_measurements("Weight")
        parsed = json.loads(result)
        assert parsed == next_data


# ---------------------------------------------------------------------------
# search_foods
# ---------------------------------------------------------------------------

class TestSearchFoods:
    def test_calls_right_url_with_query_param(self, mock_ctx, mock_token):
        body = '{"items": []}'
        mock_ctx.request.get.return_value = _make_response(
            ok=True, content_type="application/json", text=body
        )
        mfp_server.search_foods("chicken breast")
        call_args = mock_ctx.request.get.call_args
        url = call_args[0][0] if call_args[0] else call_args.args[0]
        params = call_args.kwargs.get("params") or call_args[1].get("params", {})
        assert "nutrition" in url
        assert params.get("q") == "chicken breast"

    def test_returns_response_text_on_success(self, mock_ctx, mock_token):
        body = '{"items": [{"name": "Chicken Breast"}]}'
        mock_ctx.request.get.return_value = _make_response(
            ok=True, content_type="application/json", text=body
        )
        result = mfp_server.search_foods("chicken breast")
        assert result == body

    def test_returns_error_json_on_exception(self, mock_ctx, mock_token):
        mock_ctx.request.get.side_effect = Exception("timeout")
        result = mfp_server.search_foods("chicken breast")
        parsed = json.loads(result)
        assert "error" in parsed
        assert "timeout" in parsed["error"]


# ---------------------------------------------------------------------------
# get_weekly_summary
# ---------------------------------------------------------------------------

class TestGetWeeklySummary:
    def test_calls_nutrition_api_with_correct_date_range(self, mock_ctx, mock_token):
        body = '{"days": []}'
        mock_ctx.request.get.return_value = _make_response(
            ok=True, content_type="application/json", text=body
        )
        mfp_server.get_weekly_summary("2024-01-01")
        call_args = mock_ctx.request.get.call_args
        params = call_args.kwargs.get("params") or call_args[1].get("params", {})
        assert params["from"] == "2024-01-01"
        assert params["to"] == "2024-01-07"  # start + 6 days

    def test_returns_response_text_on_success(self, mock_ctx, mock_token):
        body = '{"nutrition": "weekly"}'
        mock_ctx.request.get.return_value = _make_response(
            ok=True, content_type="application/json", text=body
        )
        result = mfp_server.get_weekly_summary("2024-01-01")
        assert result == body


# ---------------------------------------------------------------------------
# log_measurement
# ---------------------------------------------------------------------------

class TestGetWeeklySummaryFallback:
    def test_falls_back_to_individual_day_fetches_on_non_json(self, mock_ctx, mock_token):
        # API returns non-JSON (e.g. HTML), so server should fetch each of 7 days
        mock_ctx.request.get.return_value = _make_response(
            ok=True, content_type="text/html", text="<html></html>"
        )
        next_data = {"props": {"pageProps": {"meals": []}}}
        page = MagicMock()
        page.evaluate.return_value = next_data
        mock_ctx.new_page.return_value = page

        result = mfp_server.get_weekly_summary("2024-01-01")
        parsed = json.loads(result)

        assert "days" in parsed
        assert len(parsed["days"]) == 7
        assert parsed["days"][0]["date"] == "2024-01-01"
        assert parsed["days"][6]["date"] == "2024-01-07"

    def test_returns_error_json_on_exception(self, mock_ctx, mock_token):
        mock_ctx.request.get.side_effect = Exception("network failure")
        result = mfp_server.get_weekly_summary("2024-01-01")
        parsed = json.loads(result)
        assert "error" in parsed
        assert "network failure" in parsed["error"]


class TestSessionStatus:
    def test_returns_valid_when_token_fetch_succeeds(self, mock_ctx, mocker):
        mocker.patch("mfp_server._get_bearer_token", return_value="test-token")
        result = mfp_server.session_status()
        parsed = json.loads(result)
        assert parsed["status"] == "valid"

    def test_returns_expired_on_runtime_error(self, mock_ctx, mocker):
        mocker.patch(
            "mfp_server._get_bearer_token",
            side_effect=RuntimeError("MFP auth failed (HTTP 401). Run login.py to re-authenticate."),
        )
        result = mfp_server.session_status()
        parsed = json.loads(result)
        assert parsed["status"] == "expired"
        assert "instructions" in parsed
        assert "login.py" in parsed["instructions"]

    def test_returns_unknown_on_unexpected_error(self, mock_ctx, mocker):
        mocker.patch(
            "mfp_server._get_bearer_token",
            side_effect=ConnectionError("socket timeout"),
        )
        result = mfp_server.session_status()
        parsed = json.loads(result)
        assert parsed["status"] == "unknown"
        assert "instructions" in parsed


class TestLogMeasurement:
    def test_posts_to_right_url_with_correct_payload(self, mock_ctx, mock_token):
        mock_ctx.request.post.return_value = _make_response(ok=True)
        mfp_server.log_measurement(185.5, "Weight", "2024-01-15")
        call_args = mock_ctx.request.post.call_args
        url = call_args[0][0] if call_args[0] else call_args.args[0]
        assert "/api/measurements" in url
        data_str = call_args.kwargs.get("data") or call_args[1].get("data")
        data = json.loads(data_str)
        assert data["measurement"]["value"] == 185.5
        assert data["measurement"]["unit"] == "Weight"
        assert data["measurement"]["date"] == "2024-01-15"

    def test_returns_success_json_with_status_ok(self, mock_ctx, mock_token):
        mock_ctx.request.post.return_value = _make_response(ok=True)
        result = mfp_server.log_measurement(185.5, "Weight", "2024-01-15")
        parsed = json.loads(result)
        assert parsed["status"] == "ok"
        assert parsed["value"] == 185.5

    def test_returns_error_json_when_response_not_ok(self, mock_ctx, mock_token):
        mock_ctx.request.post.return_value = _make_response(
            ok=False, status=422, content_type="text/plain", text="Unprocessable"
        )
        result = mfp_server.log_measurement(185.5, "Weight", "2024-01-15")
        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert parsed["http_status"] == 422


# ---------------------------------------------------------------------------
# log_food_entry
# ---------------------------------------------------------------------------

# Minimal search result that search_foods would return
_SEARCH_BODY = json.dumps({
    "items": [{
        "id": "98765",
        "description": "Chicken Breast",
        "servings": [{"unit": "oz"}],
        "nutritional_contents": {"energy": {"value": 165}},
    }]
})


class TestLogFoodEntry:
    def _patch_search(self, mocker, body=_SEARCH_BODY):
        mocker.patch("mfp_server.search_foods", return_value=body)

    def test_posts_correct_payload_to_nutrition_endpoint(self, mock_ctx, mock_token, mocker):
        self._patch_search(mocker)
        mock_ctx.request.post.return_value = _make_response(ok=True)
        mfp_server.log_food_entry("Chicken Breast", meal="Dinner", quantity=4.0, unit="oz", date="2024-01-15")
        call_args = mock_ctx.request.post.call_args
        url = call_args[0][0] if call_args[0] else call_args.args[0]
        assert "/api/nutrition" in url
        data = json.loads(call_args.kwargs.get("data") or call_args[1].get("data"))
        entry = data["food_entries"][0]
        assert entry["food_id"] == "98765"
        assert entry["meal_entry_name"] == "Dinner"
        assert entry["quantity"] == 4.0
        assert entry["unit_name"] == "oz"
        assert entry["date"] == "2024-01-15"

    def test_returns_success_json_with_food_and_calories(self, mock_ctx, mock_token, mocker):
        self._patch_search(mocker)
        mock_ctx.request.post.return_value = _make_response(ok=True)
        result = mfp_server.log_food_entry("Chicken Breast", date="2024-01-15")
        parsed = json.loads(result)
        assert parsed["status"] == "ok"
        assert parsed["food"] == "Chicken Breast"
        assert parsed["calories"] == 165
        assert parsed["meal"] == "Lunch"

    def test_defaults_unit_from_search_result(self, mock_ctx, mock_token, mocker):
        self._patch_search(mocker)
        mock_ctx.request.post.return_value = _make_response(ok=True)
        result = mfp_server.log_food_entry("Chicken Breast", date="2024-01-15")
        parsed = json.loads(result)
        assert parsed["unit"] == "oz"

    def test_returns_error_when_no_foods_found(self, mock_ctx, mock_token, mocker):
        mocker.patch("mfp_server.search_foods", return_value=json.dumps({"items": []}))
        result = mfp_server.log_food_entry("xyzzy unknown food", date="2024-01-15")
        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert "No foods found" in parsed["detail"]

    def test_returns_error_when_search_fails(self, mock_ctx, mock_token, mocker):
        mocker.patch("mfp_server.search_foods", return_value=json.dumps({"error": "Search failed: HTTP 500"}))
        result = mfp_server.log_food_entry("Chicken Breast", date="2024-01-15")
        parsed = json.loads(result)
        assert parsed["status"] == "error"

    def test_falls_back_to_page_nav_on_api_failure(self, mock_ctx, mock_token, mocker):
        self._patch_search(mocker)
        # API POST fails
        mock_ctx.request.post.return_value = _make_response(
            ok=False, status=403, content_type="text/plain", text="Forbidden"
        )
        # Page fallback returns ok
        page = MagicMock()
        page.evaluate.return_value = {"ok": True, "status": 200, "body": "{}"}
        mock_ctx.new_page.return_value = page

        result = mfp_server.log_food_entry("Chicken Breast", date="2024-01-15")
        parsed = json.loads(result)
        assert parsed["status"] == "ok"
        assert parsed.get("method") == "page_fallback"

    def test_returns_error_when_both_api_and_fallback_fail(self, mock_ctx, mock_token, mocker):
        self._patch_search(mocker)
        mock_ctx.request.post.return_value = _make_response(
            ok=False, status=403, content_type="text/plain", text="Forbidden"
        )
        page = MagicMock()
        page.evaluate.return_value = {"ok": False, "status": 403, "body": "Forbidden"}
        mock_ctx.new_page.return_value = page

        result = mfp_server.log_food_entry("Chicken Breast", date="2024-01-15")
        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert "api_status" in parsed

    def test_returns_error_on_exception(self, mock_ctx, mock_token, mocker):
        self._patch_search(mocker)
        mock_ctx.request.post.side_effect = Exception("connection refused")
        result = mfp_server.log_food_entry("Chicken Breast", date="2024-01-15")
        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert "connection refused" in parsed["detail"]
