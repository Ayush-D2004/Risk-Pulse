import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import asyncio
from typing import Dict, Any, List
import pytz

class MarketDataService:
    @staticmethod
    async def fetch_historical_window(
        ticker: str, 
        event_dt_str: str, 
        tz_name: str = "UTC", 
        window_hours: int = 4
    ) -> Dict[str, Any]:
        """
        Fetches historical price data around a specific event timestamp.
        Returns a dictionary suitable for JSON serialization and charting.
        """
        def _fetch_sync():
            try:
                # Parse event time and localize
                event_dt = pd.to_datetime(event_dt_str)
                if event_dt.tzinfo is None:
                    event_tz = pytz.timezone(tz_name)
                    event_dt = event_tz.localize(event_dt)
                else:
                    event_dt = event_dt.astimezone(pytz.timezone(tz_name))
                
                # Determine bounds
                start_dt = event_dt - timedelta(hours=window_hours)
                end_dt = event_dt + timedelta(hours=window_hours)
                
                # yfinance history requires string dates or datetime objects. 
                # For intraday, it supports start/end as datetime.
                # Max intraday range is 60 days, if event is older we must use daily "1d".
                now = datetime.now(pytz.utc)
                is_old = (now - event_dt).days > 55
                
                interval = "1d" if is_old else "15m"
                if is_old:
                    # Expand bounds for daily to get some surrounding days
                    start_dt = event_dt - timedelta(days=5)
                    end_dt = event_dt + timedelta(days=5)
                
                t = yf.Ticker(ticker)
                # yf can hang or fail, timeout is not strictly configurable directly in yf.history but it uses requests.
                hist = t.history(start=start_dt, end=end_dt, interval=interval)
                
                if hist.empty:
                    return {
                        "status": "unavailable", 
                        "reason": "No data returned for the requested window",
                        "ticker": ticker,
                        "event_timestamp": event_dt.isoformat()
                    }
                    
                # Convert to charting format
                points = []
                for idx, row in hist.iterrows():
                    # idx is a timezone-aware pandas Timestamp
                    points.append({
                        "timestamp": idx.isoformat(),
                        "open": float(row["Open"]),
                        "high": float(row["High"]),
                        "low": float(row["Low"]),
                        "close": float(row["Close"]),
                        "volume": float(row["Volume"])
                    })
                    
                first_price = points[0]["close"]
                last_price = points[-1]["close"]
                change_pct = ((last_price - first_price) / first_price) * 100 if first_price != 0 else 0
                abs_change = last_price - first_price
                
                high_price = max(p["high"] for p in points)
                low_price = min(p["low"] for p in points)
                max_range = high_price - low_price
                
                # Find event observation (nearest or immediately before)
                # Find the index of the last point <= event_dt
                event_idx = -1
                for i, p in enumerate(points):
                    if pd.to_datetime(p["timestamp"]) <= event_dt:
                        event_idx = i
                    else:
                        break
                
                event_price = None
                event_obs_time = None
                post_event_price = None
                post_event_time = None
                post_event_change_pct = None
                
                if event_idx >= 0:
                    event_price = points[event_idx]["close"]
                    event_obs_time = points[event_idx]["timestamp"]
                    
                    # One hour after the event observation, if available
                    one_hr_later = pd.to_datetime(event_obs_time) + pd.Timedelta(hours=1)
                    post_idx = -1
                    for i in range(event_idx, len(points)):
                        if pd.to_datetime(points[i]["timestamp"]) >= one_hr_later:
                            post_idx = i
                            break
                            
                    if post_idx != -1:
                        post_event_price = points[post_idx]["close"]
                        post_event_time = points[post_idx]["timestamp"]
                        post_event_change_pct = ((post_event_price - event_price) / event_price) * 100 if event_price != 0 else 0

                return {
                    "status": "success",
                    "ticker": ticker,
                    "event_timestamp": event_dt.isoformat(),
                    "timezone": tz_name,
                    "interval": interval,
                    "points": points,
                    "metrics": {
                        "first_price": first_price,
                        "last_price": last_price,
                        "change_pct": change_pct,
                        "abs_change": abs_change,
                        "high_price": high_price,
                        "low_price": low_price,
                        "max_range": max_range,
                        "event_price": event_price,
                        "event_obs_time": event_obs_time,
                        "post_event_price": post_event_price,
                        "post_event_time": post_event_time,
                        "post_event_change_pct": post_event_change_pct
                    }
                }
            except Exception as e:
                return {
                    "status": "error",
                    "reason": str(e),
                    "ticker": ticker
                }

        # Run in thread with timeout to avoid blocking the event loop or hanging forever
        try:
            return await asyncio.wait_for(asyncio.to_thread(_fetch_sync), timeout=10.0)
        except asyncio.TimeoutError:
            return {
                "status": "error",
                "reason": "Provider request timed out",
                "ticker": ticker
            }
