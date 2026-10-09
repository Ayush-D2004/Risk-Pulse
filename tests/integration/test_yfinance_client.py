import pytest
from unittest.mock import patch, MagicMock
import pandas as pd
from datetime import datetime
import pytz
from src.market.yfinance_client import MarketDataService

@pytest.mark.asyncio
async def test_fetch_historical_window_success():
    # Mock yfinance Ticker and history
    with patch("src.market.yfinance_client.yf.Ticker") as mock_ticker:
        # Create a series covering 2 hours with 15min intervals
        dates = pd.date_range("2026-10-09 10:00:00", periods=9, freq="15min", tz="UTC")
        # 10:00, 10:15, 10:30, 10:45, 11:00, 11:15, 11:30, 11:45, 12:00
        df = pd.DataFrame({
            "Open": [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0],
            "High": [101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 110.0],
            "Low": [98.0, 100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0],
            "Close": [100.0, 101.0, 102.5, 103.0, 104.0, 105.0, 106.5, 107.0, 108.0],
            "Volume": [1000] * 9
        }, index=dates)
        
        mock_ticker.return_value.history.return_value = df
        
        # Event at 10:30 UTC
        result = await MarketDataService.fetch_historical_window(
            ticker="AAPL",
            event_dt_str="2026-10-09T10:30:00",
            tz_name="UTC",
            window_hours=2
        )
        
        assert result["status"] == "success"
        assert result["ticker"] == "AAPL"
        assert result["timezone"] == "UTC"
        assert len(result["points"]) == 9
        
        metrics = result["metrics"]
        assert metrics["first_price"] == 100.0
        assert metrics["last_price"] == 108.0
        assert metrics["abs_change"] == 8.0
        assert metrics["change_pct"] == 8.0
        assert metrics["high_price"] == 110.0
        assert metrics["low_price"] == 98.0
        assert metrics["max_range"] == 12.0
        
        # Event price at 10:30 should be 102.5
        assert metrics["event_price"] == 102.5
        assert "10:30:00" in metrics["event_obs_time"]
        
        # 1h later is 11:30: close is 106.5
        assert metrics["post_event_price"] == 106.5
        assert "11:30:00" in metrics["post_event_time"]
        # Post event change % = ((106.5 - 102.5) / 102.5) * 100
        expected_post_pct = ((106.5 - 102.5) / 102.5) * 100
        assert abs(metrics["post_event_change_pct"] - expected_post_pct) < 1e-4

@pytest.mark.asyncio
async def test_fetch_historical_window_empty():
    with patch("src.market.yfinance_client.yf.Ticker") as mock_ticker:
        mock_ticker.return_value.history.return_value = pd.DataFrame()
        
        result = await MarketDataService.fetch_historical_window(
            ticker="UNKNOWN",
            event_dt_str="2026-10-09T10:15:00",
            tz_name="UTC",
            window_hours=4
        )
        
        assert result["status"] == "unavailable"
        assert result["ticker"] == "UNKNOWN"

@pytest.mark.asyncio
async def test_fetch_historical_window_error():
    with patch("src.market.yfinance_client.yf.Ticker") as mock_ticker:
        mock_ticker.return_value.history.side_effect = Exception("API Error")
        
        result = await MarketDataService.fetch_historical_window(
            ticker="AAPL",
            event_dt_str="2026-10-09T10:15:00",
            tz_name="UTC",
            window_hours=4
        )
        
        assert result["status"] == "error"
        assert result["reason"] == "API Error"

def test_chart_coordinate_calculation():
    # Deterministic test verifying continuous time-axis event placement
    # Points from 10:00 to 12:00 (120 minutes)
    t_start = pd.to_datetime("2026-10-09T10:00:00Z").timestamp()
    t_end = pd.to_datetime("2026-10-09T12:00:00Z").timestamp()
    time_range = t_end - t_start # 7200 seconds
    width = 600
    
    # Event at 11:00 (halfway, 3600 seconds)
    t_event_mid = pd.to_datetime("2026-10-09T11:00:00Z").timestamp()
    x_mid = ((t_event_mid - t_start) / time_range) * width
    assert x_mid == 300.0
    
    # Event at 10:30 (25% mark)
    t_event_quarter = pd.to_datetime("2026-10-09T10:30:00Z").timestamp()
    x_quarter = ((t_event_quarter - t_start) / time_range) * width
    assert x_quarter == 150.0
    
    # Event before window (out of bounds left)
    t_event_before = pd.to_datetime("2026-10-09T09:30:00Z").timestamp()
    x_before = ((t_event_before - t_start) / time_range) * width
    assert x_before < 0
    
    # Event after window (out of bounds right)
    t_event_after = pd.to_datetime("2026-10-09T12:30:00Z").timestamp()
    x_after = ((t_event_after - t_start) / time_range) * width
    assert x_after > width
