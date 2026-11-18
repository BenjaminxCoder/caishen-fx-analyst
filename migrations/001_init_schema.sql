-- 001_init_schema.sql: Core Caishen FX Analyst Ledger & Governance Schema

-- 1. Governance & Probation State Machine (Enforces Rule 3: 10% Drawdown Lockout)
CREATE TABLE IF NOT EXISTS account_states (
    id SERIAL PRIMARY KEY,
    oanda_account_id VARCHAR(50) UNIQUE NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'ACTIVE'
        CHECK (status IN ('ACTIVE', 'SUSPENDED', 'PAPER_REVIEW_PENDING', 'PROBATION')),
    weekly_starting_balance NUMERIC(12, 4) NOT NULL,
    current_balance NUMERIC(12, 4) NOT NULL,
    suspended_until TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2. Mandatory Pre-Trade Plan (Enforces Rule 2: Reason, Plan, Minimum Exit)
CREATE TABLE IF NOT EXISTS trade_plans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    instrument VARCHAR(15) NOT NULL,
    direction VARCHAR(10) NOT NULL CHECK (direction IN ('LONG', 'SHORT')),
    thesis TEXT NOT NULL,
    planned_stop_loss NUMERIC(12, 5) NOT NULL,
    planned_take_profit NUMERIC(12, 5),
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING'
        CHECK (status IN ('PENDING', 'EXECUTED', 'EXPIRED')),
    created_at TIMESTAMPZ NOT NULL DEFAULT NOW()
);

-- 3. Immutable Fintech Trade Ledger
CREATE TABLE IF NOT EXISTS trades (
    id SERIAL PRIMARY KEY,
    oanda_trade_id VARCHAR(50) UNIQUE NOT NULL,
    plan_id UUID REFERENCES trade_plans(id) ON DELETE SET NULL,
    instrument VARCHAR(15) NOT NULL,
    units NUMERIC(12, 2) NOT NULL,
    entry_price NUMERIC(12, 5) NOT NULL,
    exit_price NUMERIC(12, 5),
    half_spread_cost NUMERIC(10, 4),
    realized_pl NUMERIC(12, 4),
    close_reason VARCHAR(40),
    opened_at TIMESTAMPTZ NOT NULL,
    closed_at TIMESTAMPTZ
);

-- 4. Accountability & AI Debrief Log
CREATE TABLE IF NOT EXISTS rule_violations (
    id SERIAL PRIMARY KEY,
    trade_id INT REFERENCES trades(id) ON DELETE CASCADE,
    violation_type VARCHAR(40) NOT NULL
        CHECK (violation_type IN (
            'NO_PRE_TRADE_PLAN',
            'MISSING_STOP_LOSS',
            'REVENGE_TRADING',
            'FRIDAY_MARKET_CLOSE',
            'WEEKLY_DRAWDOWN_10PCT'
        )),
    severity VARCHAR(15) NOT NULL CHECK (severity IN ('WARNING', 'LOCKOUT')),
    ai_debrief TEXT,
    user_reflection TEXT,
    resolved BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);