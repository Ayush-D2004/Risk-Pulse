import os
import json
import logging
import pandas as pd
import yfinance as yf

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

REGISTRY_PATH = "data/processed/historical_instrument_registry.json"
INPUT_CSV = "data/pipeline_output/canonical_events.csv"
CACHE_DIR = "data/processed/market_cache"
START_DATE = "2016-11-01"
END_DATE = "2019-02-01"

def load_registry():
    with open(REGISTRY_PATH, "r") as f:
        data = json.load(f)
    mapping = {}
    for entry in data.get("registry", []):
        mapping[entry["source_entity_name"]] = entry
    return mapping

def main():
    if not os.path.exists(INPUT_CSV):
        logger.error(f"Input file {INPUT_CSV} not found.")
        return

    df = pd.read_csv(INPUT_CSV)
    registry = load_registry()
    
    # Get all entities in the events
    entities = df["canonical_entity"].dropna().unique()
    
    tickers_to_fetch = set()
    for ent in entities:
        if ent in registry:
            entry = registry[ent]
            if entry.get("resolution_status") in ["USABLE_HISTORICAL_INSTRUMENT", "PROXY_INSTRUMENT"]:
                ticker = entry.get("historical_ticker")
                if ticker:
                    tickers_to_fetch.add(ticker)
                    
    logger.info(f"Identified {len(tickers_to_fetch)} tickers for cache expansion.")
    
    processed = 0
    success = 0
    failed = 0
    total_rows_added = 0
    
    for ticker in tickers_to_fetch:
        processed += 1
        logger.info(f"[{processed}/{len(tickers_to_fetch)}] Processing {ticker}...")
        
        try:
            # Download data via yfinance
            t = yf.Ticker(ticker)
            hist = t.history(start=START_DATE, end=END_DATE)
            
            if hist.empty:
                logger.warning(f"Ticker {ticker} returned empty history (likely delisted or invalid).")
                failed += 1
                continue
                
            hist.index = pd.to_datetime(hist.index, utc=True)
            hist.index.name = "Date"
            
            # Format columns to match existing cache
            cols_to_keep = ["Open", "High", "Low", "Close", "Volume"]
            hist = hist[[c for c in cols_to_keep if c in hist.columns]]
            hist["Price"] = hist["Close"]
            
            # Merge with existing if exists
            cache_path = os.path.join(CACHE_DIR, f"{ticker}.parquet")
            if os.path.exists(cache_path):
                existing_df = pd.read_parquet(cache_path)
                if existing_df.index.tzinfo is None:
                    existing_df.index = existing_df.index.tz_localize("UTC")
                else:
                    existing_df.index = existing_df.index.tz_convert("UTC")
                
                # Combine and drop duplicates
                combined = pd.concat([existing_df, hist])
                combined = combined[~combined.index.duplicated(keep="last")].sort_index()
                
                new_rows = len(combined) - len(existing_df)
                if new_rows > 0:
                    combined.to_parquet(cache_path)
                    total_rows_added += new_rows
                    logger.info(f"Merged {ticker}, added {new_rows} new rows.")
                else:
                    logger.info(f"{ticker} already up to date.")
            else:
                hist.to_parquet(cache_path)
                total_rows_added += len(hist)
                logger.info(f"Created new cache for {ticker}, added {len(hist)} rows.")
                
            success += 1
            
        except Exception as e:
            logger.error(f"Failed to fetch or process {ticker}: {e}")
            failed += 1
            
    logger.info(f"Expansion complete. Processed {processed}, Success: {success}, Failed: {failed}, Total new rows: {total_rows_added}")

if __name__ == "__main__":
    main()
