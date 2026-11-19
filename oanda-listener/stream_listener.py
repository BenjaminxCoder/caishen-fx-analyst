### 
# import os: loads Python's built-in Operating System module
# import json: loads Python's built-in JSON (JavaScript Object Notation) module.
# import requests: loads the popular third-party Requests library into your script;
#   enabling your code to send HTTP requests and interact with websites or APIs. 
# from dotenv import load_dotenv: Let's us keep our API keys or Tokens safe from leaking.
###
import os
import json
import requests
import psycopg
from dotenv import load_dotenv

# 1. Load environment variables from your local .env file
load_dotenv()

API_TOKEN = os.getenv("OANDA_API_TOKEN")
ACCOUNT_ID = os.getenv("OANDA_ACCOUNT_ID")
STREAM_URL = os.getenv("OANDA_STREAM_URL")
DB_URL = os.getenv("DATABASE_URL")

url = f"{STREAM_URL}/v3/accounts/{ACCOUNT_ID}/transactions/stream"
headers = {
    "Authorization": f"Bearer {API_TOKEN}",
    "Content-Type": "application/json",
}

def save_opened_trade(event):
    """Inserts a newly opened OANDA trade into PostgreSQL and flags missing pre-trade plans."""
    trade_opened = event.get("tradeOpened")
    if not trade_opened:
        return  # Skip closing fills for now; we will handle tradesClosed on Day 2!

    oanda_trade_id = trade_opened["tradeID"]
    instrument = event["instrument"]
    units = event["units"]
    entry_price = event["price"]
    half_spread = event.get("halfSpreadCost", "0")
    opened_at = event["time"]

    # Using 'with' ensures the DB connection closes and commits atomically
    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO trades (oanda_trade_id, instrument, units, entry_price, half_spread_cost, opened_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (oanda_trade_id) DO NOTHING
                RETURNING id;
                """,
                (oanda_trade_id, instrument, units, entry_price, half_spread, opened_at),
            )
            row = cur.fetchone()

            # If a brand-new trade row was inserted (not a duplicate), check Rule 2 (Pre-Trade Plan)
            if row:
                new_trade_id = row[0]
                cur.execute(
                    """
                    INSERT INTO rule_violations (trade_id, violation_type, severity, ai_debrief)
                    VALUES (%s, 'NO_PRE_TRADE_PLAN', 'WARNING', 'Trade opened without a logged pre-trade thesis.');
                    """,
                    (new_trade_id,),
                )
                print(f"[DB SAVED] Trade #{new_trade_id} (OANDA ID {oanda_trade_id}) logged + Rule 2 warning recorded.")

def save_closed_trades(event):
    # Safe retieve the list of closed trades from the OANDA event dict Using .get(..., []) pervents a KeyError crash.
    closed_trades = event.get("tradesClosed", [])

    # Exit the function immediately if the list is empty; Guard clause pattern-avoids.
    if not closed_trades:
        return

    exit_price = event["price"]
    closed_at = event["time"]
    close_reason = event.get("reason", "UNKNOWN")

    # Open an atomic self-closing PostgreSQL db Connection
    # The 'with' context manager guarantees the transaction commits if all updates succeed, or rolls back if an error occurs.
    with psycopg.connect(DB_URL) as conn:
        # Open a database cursor to execute parameterized SQL statements; Cursors isolate query execution and prevent SQL injection by safely binding %s placeholders.
        with conn.cursor() as cur:
            # Loop through every closed trade dict inside tradesClosed list; A single closing order can close mulitple open trades.
            for closed_item in closed_trades:
                # Extract the original OANDA trade ID and the realized profit/loss for this specific ticket.
                oanda_trade_id = closed_item["tradeID"]
                realized_pl = closed_item["realizedPL"]

                # Update the existing open trade record with its closing metrics; The WHERE clause ensures we only modify this exact trade ticket rather than overwriting the entire ledger.
                cur.execute(
                    """
                    UPDATE trades
                    SET exit_price = %s,
                        realized_pl = %s,
                        close_reason = %s,
                        closed_at = %s
                    WHERE oanda_trade_id = %s
                    RETURNING id, instrument;
                    """,
                    (exit_price, realized_pl, close_reason, closed_at, oanda_trade_id),
                )

                # Fetch the returned database primary key (id) and currency pair if a row matched.
                updated_row = cur.fetchone()

                if updated_row:
                    db_id, instrument = updated_row
                    print(f"[DB CLOSED] Trade #{db_id} ({instrument} | OANDA ID {oanda_trade_id}) closed | P/L: {realized_pl} | Reason: {close_reason}")
                else:
                    # Log a warning if PostgreSQL updated 0 rows; Handles the edge case where a trade was opened while our Python listener was offline.
                    print(f"[DB WARN] Received close for OANDA ID {oanda_trade_id}, but no matching open trade exists in Postgres.")

def start_stream():
    print(f"Connecting to OANDA stream for {ACCOUNT_ID}...")

    # timeout=(10, 30) means: wait up to 10s to connect and 30s between incoming data chuncks
    with requests.get(url, headers=headers, stream=True, timeout=(10, 30)) as response:
        response.raise_for_status()
        print("Stream active! Waiting for heartbeats and trades (Ctrl+C to exit)...\n")

        for raw_line in response.iter_lines():
            if raw_line:
                event = json.loads(raw_line.decode("utf-8"))
                event_type = event.get("type")

                if event_type == "HEARTBEAT":
                    print(f"[HEARTBEAT] {event.get('time')}")
                elif event_type == "ORDER_FILL":
                 print(f"\n>>> ORDER_FILL DETECTED <<<")
                 save_opened_trade(event)
                 save_closed_trades(event)
                else:
                    print(f"\n>>> TRANSACTION EVENT: {event_type} <<<")
                    print(json.dumps(event, indent=2))

if __name__ == "__main__":
    try:
        start_stream()
    except KeyboardInterrupt:
        print("\nStream Stopped cleanly.")