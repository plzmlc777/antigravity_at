"""KR investor-flow features (ka10059, daily).

The investor_flow_daily table holds per-symbol daily net buy/sell amounts
broken down by 13 investor classes:
    individual / foreign / institutional / fin_inv / insurance / trust /
    etc_fin / bank / pension / private_fund / govt / corp / natfor

This is the KR equivalent of crypto microstructure positioning data — it tells
us WHO is buying or selling, day by day. Foreign + institutional flows are
generally considered "smart money"; individual is the contra-indicator.

Why it might add OOS-stable alpha:
  - HFT / momentum strategies don't see this data (it's reported with 1-day lag)
  - Persistent flow patterns reveal positioning that takes weeks to unwind
  - "Smart money" net buy / individual net sell is a structural signal

Output features (per daily eval bar, anchored to that day's close):
  flow_foreign_net          — today's net buy by foreigners (signed)
  flow_inst_net             — institutional total
  flow_individual_net       — retail (often contra)
  flow_smart_minus_dumb     — (foreign + institutional) - individual  (z-scored)
  flow_foreign_5d_cum       — 5-day rolling sum (medium-term positioning)
  flow_foreign_20d_cum      — 20-day rolling sum
  flow_foreign_zscore       — vs trailing 60-day distribution
  flow_inst_zscore
  flow_smart_5d_cum
  flow_smart_zscore
  flow_pension_5d_cum       — pension net buying (very-long-term smart money)
  flow_natfor_share         — natfor / total trading value
  flow_pct_of_value         — abs(foreign+inst+individual) / acc_trade_value

All look-ahead safe: each feature at day t uses data published AT/BEFORE day t.
"""
from __future__ import annotations

import logging
from typing import Iterable

import numpy as np
import pandas as pd
from sqlalchemy import text

from app.db.session import SessionLocal, db_scope

logger = logging.getLogger(__name__)


def fetch_investor_flow(symbol: str) -> pd.DataFrame:
    """Pull all rows for `symbol` from investor_flow_daily, indexed by date."""
    with db_scope() as db:
        sql = text("""
            SELECT date, close_price, acc_trade_value,
                   individual_net, foreign_net, institutional_net,
                   fin_inv_net, insurance_net, trust_net, etc_fin_net,
                   bank_net, pension_net, private_fund_net, govt_net,
                   corp_net, natfor_net
            FROM investor_flow_daily
            WHERE symbol = :sym
            ORDER BY date ASC
        """)
        rows = db.execute(sql, {"sym": symbol}).fetchall()
    if not rows:
        return pd.DataFrame()
    cols = ["date", "close_price", "acc_trade_value",
            "individual_net", "foreign_net", "institutional_net",
            "fin_inv_net", "insurance_net", "trust_net", "etc_fin_net",
            "bank_net", "pension_net", "private_fund_net", "govt_net",
            "corp_net", "natfor_net"]
    df = pd.DataFrame(rows, columns=cols)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    for c in df.columns:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def build_flow_features(flow_df: pd.DataFrame) -> pd.DataFrame:
    """Engineer features from raw investor flow data."""
    if flow_df.empty:
        return pd.DataFrame()
    f = pd.DataFrame(index=flow_df.index)

    # raw signed nets (in 백만원)
    f["flow_foreign_net"] = flow_df["foreign_net"]
    f["flow_inst_net"] = flow_df["institutional_net"]
    f["flow_individual_net"] = flow_df["individual_net"]
    f["flow_pension_net"] = flow_df["pension_net"]
    f["flow_natfor_net"] = flow_df["natfor_net"]

    # smart minus dumb
    smart = flow_df["foreign_net"] + flow_df["institutional_net"]
    f["flow_smart_minus_dumb"] = smart - flow_df["individual_net"]

    # rolling cumulative (multi-day positioning)
    for col, alias in [
        ("foreign_net", "flow_foreign"),
        ("institutional_net", "flow_inst"),
        ("pension_net", "flow_pension"),
    ]:
        f[f"{alias}_5d_cum"] = flow_df[col].rolling(5, min_periods=1).sum()
        f[f"{alias}_20d_cum"] = flow_df[col].rolling(20, min_periods=5).sum()
        # z-score vs trailing 60-day distribution
        roll_mean = flow_df[col].rolling(60, min_periods=20).mean()
        roll_std = flow_df[col].rolling(60, min_periods=20).std(ddof=0)
        f[f"{alias}_zscore_60d"] = (flow_df[col] - roll_mean) / roll_std.replace(0, np.nan)

    # smart_minus_dumb cumulative + zscore
    f["flow_smart_5d_cum"] = smart.rolling(5, min_periods=1).sum()
    f["flow_smart_20d_cum"] = smart.rolling(20, min_periods=5).sum()
    f["flow_smart_zscore_60d"] = (smart - smart.rolling(60, min_periods=20).mean()) / smart.rolling(60, min_periods=20).std(ddof=0).replace(0, np.nan)

    # natfor share (foreign net flow as % of total trading value)
    tot_val = flow_df["acc_trade_value"].replace(0, np.nan)
    f["flow_natfor_share"] = flow_df["natfor_net"] / tot_val
    f["flow_smart_share"] = smart / tot_val
    f["flow_individual_share"] = flow_df["individual_net"] / tot_val

    # day-over-day flow changes (acceleration)
    f["flow_foreign_change"] = flow_df["foreign_net"].diff()
    f["flow_inst_change"] = flow_df["institutional_net"].diff()
    f["flow_smart_change"] = smart.diff()

    # flow consistency (signed bars in last 5 days)
    f["flow_foreign_sign_5d"] = np.sign(flow_df["foreign_net"]).rolling(5, min_periods=1).sum()
    f["flow_smart_sign_5d"] = np.sign(smart).rolling(5, min_periods=1).sum()

    return f


def attach_flow_to_features(
    feat: pd.DataFrame,
    flow_df: pd.DataFrame,
) -> pd.DataFrame:
    """Forward-fill flow features onto the feature matrix index (eval frequency)."""
    flow_feats = build_flow_features(flow_df)
    if flow_feats.empty:
        return feat
    # Flow data is daily, anchored at trading day close.
    # If feat is also daily, direct reindex with method='ffill'.
    feat_idx_normalized = pd.to_datetime(feat.index).normalize()
    flow_idx_normalized = pd.to_datetime(flow_feats.index).normalize()
    flow_feats.index = flow_idx_normalized
    flow_feats = flow_feats[~flow_feats.index.duplicated(keep="last")]
    mapped = flow_feats.reindex(feat_idx_normalized, method="ffill")
    mapped.index = feat.index
    return pd.concat([feat, mapped], axis=1)
