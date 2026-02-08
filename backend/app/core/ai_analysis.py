"""
AI Analysis Service for Optimization Results

Handles:
1. CSV import to temporary DB table
2. Statistics calculation via SQL
3. AI context building
4. Claude API integration
"""

import os
import csv
import uuid
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# API configurations
CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models"
DEFAULT_MODEL = "claude-sonnet-4-20250514"  # Default model for analysis


class AIAnalysisService:
    """Service for AI-powered optimization analysis."""

    def __init__(self, db: AsyncSession, api_key: Optional[str] = None, model: Optional[str] = None, provider: str = "anthropic"):
        self.db = db
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.model = model or DEFAULT_MODEL
        self.provider = provider
        if not self.api_key:
            logger.warning("API key not set. AI analysis will be disabled.")

    async def import_csv_to_db(self, csv_path: str, analysis_id: uuid.UUID) -> int:
        """
        Import CSV file to optimization_analysis table.
        Returns number of rows imported.
        """
        if not Path(csv_path).exists():
            raise FileNotFoundError(f"CSV file not found: {csv_path}")

        rows_imported = 0

        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)

            for row in reader:
                # Extract config columns (prefixed with config_)
                config = {}
                metrics = {}

                for key, value in row.items():
                    if key.startswith('config_'):
                        config[key.replace('config_', '')] = self._parse_value(value)
                    else:
                        metrics[key] = self._parse_value(value)

                # Insert row
                await self.db.execute(text("""
                    INSERT INTO optimization_analysis (
                        analysis_id, rank, symbol, score, total_return, win_rate,
                        total_trades, max_drawdown, profit_factor, sharpe_ratio,
                        avg_pnl, stability_score, acceleration_score, activity_rate,
                        avg_holding_time, max_profit, max_loss, total_days,
                        cycle_count, cycle_avg_pnl, cycle_avg_hold, config
                    ) VALUES (
                        :analysis_id, :rank, :symbol, :score, :total_return, :win_rate,
                        :total_trades, :max_drawdown, :profit_factor, :sharpe_ratio,
                        :avg_pnl, :stability_score, :acceleration_score, :activity_rate,
                        :avg_holding_time, :max_profit, :max_loss, :total_days,
                        :cycle_count, :cycle_avg_pnl, :cycle_avg_hold, :config
                    )
                """), {
                    "analysis_id": str(analysis_id),
                    "rank": metrics.get('rank'),
                    "symbol": metrics.get('symbol'),
                    "score": metrics.get('score'),
                    "total_return": metrics.get('total_return'),
                    "win_rate": metrics.get('win_rate'),
                    "total_trades": metrics.get('total_trades'),
                    "max_drawdown": self._parse_percent(metrics.get('max_drawdown')),
                    "profit_factor": metrics.get('profit_factor'),
                    "sharpe_ratio": metrics.get('sharpe_ratio'),
                    "avg_pnl": metrics.get('avg_pnl'),
                    "stability_score": metrics.get('stability_score'),
                    "acceleration_score": metrics.get('acceleration_score'),
                    "activity_rate": self._parse_percent(metrics.get('activity_rate')),
                    "avg_holding_time": self._parse_time(metrics.get('avg_holding_time')),
                    "max_profit": metrics.get('max_profit'),
                    "max_loss": metrics.get('max_loss'),
                    "total_days": metrics.get('total_days'),
                    "cycle_count": metrics.get('cycle_count'),
                    "cycle_avg_pnl": metrics.get('cycle_avg_pnl'),
                    "cycle_avg_hold": metrics.get('cycle_avg_hold'),
                    "config": json.dumps(config)
                })
                rows_imported += 1

                # Commit every 1000 rows
                if rows_imported % 1000 == 0:
                    await self.db.commit()
                    logger.info(f"Imported {rows_imported} rows...")

        await self.db.commit()
        logger.info(f"Import complete: {rows_imported} rows")
        return rows_imported

    async def calculate_statistics(self, analysis_id: uuid.UUID) -> Dict[str, Any]:
        """Calculate comprehensive statistics from imported data."""

        # Overall statistics
        overall = await self.db.execute(text("""
            SELECT
                COUNT(*) as total_rows,
                COUNT(DISTINCT symbol) as symbol_count,

                -- Return statistics
                MIN(total_return) as return_min,
                MAX(total_return) as return_max,
                AVG(total_return) as return_avg,
                STDDEV(total_return) as return_std,
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY total_return) as return_median,

                -- Win rate statistics
                MIN(win_rate) as winrate_min,
                MAX(win_rate) as winrate_max,
                AVG(win_rate) as winrate_avg,

                -- Stability statistics
                AVG(stability_score) as stability_avg,
                AVG(acceleration_score) as accel_avg,

                -- Drawdown
                MIN(max_drawdown) as dd_min,
                MAX(max_drawdown) as dd_max,
                AVG(max_drawdown) as dd_avg,

                -- Sharpe
                AVG(sharpe_ratio) as sharpe_avg,
                MAX(sharpe_ratio) as sharpe_max,

                -- Cycle metrics
                AVG(cycle_count) as cycle_count_avg,
                AVG(cycle_avg_pnl) as cycle_pnl_avg,
                AVG(cycle_avg_hold) as cycle_hold_avg

            FROM optimization_analysis
            WHERE analysis_id = :aid
        """), {"aid": str(analysis_id)})
        overall_row = overall.fetchone()

        # Per-symbol best performers
        per_symbol = await self.db.execute(text("""
            SELECT DISTINCT ON (symbol)
                symbol,
                total_return,
                win_rate,
                stability_score,
                acceleration_score,
                cycle_count,
                config
            FROM optimization_analysis
            WHERE analysis_id = :aid
            ORDER BY symbol, total_return DESC
        """), {"aid": str(analysis_id)})
        symbol_results = [dict(row._mapping) for row in per_symbol.fetchall()]

        # Parameter distribution for top 10% by return
        param_dist = await self.db.execute(text("""
            SELECT config
            FROM optimization_analysis
            WHERE analysis_id = :aid
            AND total_return >= (
                SELECT PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY total_return)
                FROM optimization_analysis WHERE analysis_id = :aid
            )
        """), {"aid": str(analysis_id)})
        top_configs = [json.loads(row[0]) for row in param_dist.fetchall()]

        # Aggregate parameter frequencies
        param_freq = self._calculate_param_frequencies(top_configs)

        return {
            "overall": {
                "total_rows": overall_row.total_rows,
                "symbol_count": overall_row.symbol_count,
                "return": {
                    "min": round(overall_row.return_min or 0, 2),
                    "max": round(overall_row.return_max or 0, 2),
                    "avg": round(overall_row.return_avg or 0, 2),
                    "std": round(overall_row.return_std or 0, 2),
                    "median": round(overall_row.return_median or 0, 2)
                },
                "win_rate": {
                    "min": round(overall_row.winrate_min or 0, 1),
                    "max": round(overall_row.winrate_max or 0, 1),
                    "avg": round(overall_row.winrate_avg or 0, 1)
                },
                "stability_avg": round(overall_row.stability_avg or 0, 3),
                "acceleration_avg": round(overall_row.accel_avg or 0, 3),
                "drawdown": {
                    "min": round(overall_row.dd_min or 0, 1),
                    "max": round(overall_row.dd_max or 0, 1),
                    "avg": round(overall_row.dd_avg or 0, 1)
                },
                "sharpe": {
                    "avg": round(overall_row.sharpe_avg or 0, 2),
                    "max": round(overall_row.sharpe_max or 0, 2)
                },
                "cycle": {
                    "count_avg": round(overall_row.cycle_count_avg or 0, 1),
                    "pnl_avg": round(overall_row.cycle_pnl_avg or 0, 0),
                    "hold_avg_min": round(overall_row.cycle_hold_avg or 0, 1)
                }
            },
            "per_symbol": symbol_results[:10],  # Top 10 symbols
            "top_param_frequencies": param_freq
        }

    def build_ai_context(
        self,
        strategy_id: str,
        stats: Dict[str, Any],
        user_question: Optional[str] = None
    ) -> str:
        """Build context prompt for Claude API."""

        context = f"""# {strategy_id} 최적화 분석 요청

## 1. 전략 개요
DipMartingaleStrategy는 가격 하락 시 단계별로 물타기 매수하고, 반등 시 트레일링 스탑으로 익절하는 전략입니다.

### 사이클 구조
- [진입] 가격이 trigger_level% 하락 → Level 1 매수
- [추가매수] 추가 하락 시 Level 2, 3... 매수 (lot_size_multiplier 적용)
- [익절] trailing_stop 도달 → 수익 실현
- [손절] max_loss_percent 도달 or cycle_max_hours 초과

## 2. 메트릭 정의

### 수익 지표
- total_return: 총 수익률 (%)
- avg_pnl: 거래당 평균 손익
- max_profit/max_loss: 단일 거래 최대 수익/손실

### 리스크 지표
- max_drawdown: 최대 낙폭 (%)
- sharpe_ratio: 위험조정수익률

### 효율성 지표
- win_rate: 승률 (%)
- profit_factor: 총이익/총손실
- total_trades: 총 거래 횟수
- activity_rate: 거래 활동일 비율 (%)

### 안정성 지표 (매우 중요)
- stability_score: 누적 수익의 선형성 (R², 0-1)
  → 1에 가까울수록 수익이 일정하게 증가
  → 0에 가까우면 들쭉날쭉

- acceleration_score: 최근 성과 / 전체 성과 비율
  → > 1.0: 성과가 점점 좋아짐 (양호)
  → = 1.0: 일정함
  → < 1.0: 성과가 악화됨 (과적합 가능성)

### 사이클 지표
- cycle_count: 완료된 사이클 수
- cycle_avg_pnl: 사이클당 평균 손익
- cycle_avg_hold: 사이클당 평균 보유시간 (분)

## 3. 최적화 결과 통계 ({stats['overall']['total_rows']:,}개 조합, {stats['overall']['symbol_count']}개 심볼)

### 수익률 분포
- 최소: {stats['overall']['return']['min']}%
- 최대: {stats['overall']['return']['max']}%
- 평균: {stats['overall']['return']['avg']}%
- 표준편차: {stats['overall']['return']['std']}%
- 중앙값: {stats['overall']['return']['median']}%

### 승률 분포
- 최소: {stats['overall']['win_rate']['min']}%
- 최대: {stats['overall']['win_rate']['max']}%
- 평균: {stats['overall']['win_rate']['avg']}%

### 안정성 지표
- stability_score 평균: {stats['overall']['stability_avg']}
- acceleration_score 평균: {stats['overall']['acceleration_avg']}

### 드로다운
- 최소: {stats['overall']['drawdown']['min']}%
- 최대: {stats['overall']['drawdown']['max']}%
- 평균: {stats['overall']['drawdown']['avg']}%

### Sharpe Ratio
- 평균: {stats['overall']['sharpe']['avg']}
- 최대: {stats['overall']['sharpe']['max']}

### 사이클 통계
- 평균 사이클 수: {stats['overall']['cycle']['count_avg']}
- 사이클당 평균 손익: {stats['overall']['cycle']['pnl_avg']:,.0f}원
- 사이클당 평균 보유시간: {stats['overall']['cycle']['hold_avg_min']}분

## 4. 상위 10% 파라미터 빈도
{self._format_param_freq(stats.get('top_param_frequencies', {}))}

## 5. 요청사항

당신은 트레이딩 전략 분석 전문가입니다. 위 데이터를 분석하여:

1. **Score 공식 제안**: 위 메트릭들의 가중치를 직접 결정하여 새로운 Score 공식을 제안하세요.
   - 각 가중치의 근거를 설명하세요.
   - 특히 stability_score와 acceleration_score를 어떻게 반영할지 설명하세요.

2. **패턴 분석**: 상위 성과를 내는 파라미터 조합의 공통점을 분석하세요.

3. **주의사항**: acceleration_score < 1.0인 경우 과적합 가능성을 경고하세요.

4. **추천**: 실거래에 적용하기 좋은 안정적인 파라미터 조합을 추천하세요.

{f"추가 질문: {user_question}" if user_question else ""}
"""
        return context

    async def call_claude_api(self, context: str) -> Dict[str, Any]:
        """Call AI API for analysis (supports Claude and Gemini)."""
        if not self.api_key:
            return {"error": "API key not configured"}

        logger.info(f"[AI Analysis] Using model: {self.model} (provider: {self.provider})")

        if self.provider == "google":
            return await self._call_gemini_api(context)
        else:
            return await self._call_anthropic_api(context)

    async def _call_anthropic_api(self, context: str) -> Dict[str, Any]:
        """Call Anthropic Claude API."""
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                CLAUDE_API_URL,
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                },
                json={
                    "model": self.model,
                    "max_tokens": 4096,
                    "messages": [
                        {"role": "user", "content": context}
                    ]
                }
            )

            if response.status_code != 200:
                logger.error(f"Claude API error: {response.status_code} - {response.text}")
                return {"error": f"Claude API error: {response.status_code}"}

            result = response.json()
            return {
                "content": result["content"][0]["text"],
                "model": result["model"],
                "usage": result.get("usage", {})
            }

    async def _call_gemini_api(self, context: str) -> Dict[str, Any]:
        """Call Google Gemini API."""
        url = f"{GEMINI_API_URL}/{self.model}:generateContent?key={self.api_key}"

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                url,
                headers={
                    "content-type": "application/json"
                },
                json={
                    "contents": [
                        {
                            "parts": [
                                {"text": context}
                            ]
                        }
                    ],
                    "generationConfig": {
                        "maxOutputTokens": 8192,
                        "temperature": 0.7
                    }
                }
            )

            if response.status_code != 200:
                logger.error(f"Gemini API error: {response.status_code} - {response.text}")
                return {"error": f"Gemini API error: {response.status_code}"}

            result = response.json()

            # Extract text from Gemini response
            try:
                content = result["candidates"][0]["content"]["parts"][0]["text"]
            except (KeyError, IndexError) as e:
                logger.error(f"Failed to parse Gemini response: {e}")
                return {"error": "Failed to parse Gemini response"}

            # Extract usage metadata if available
            usage = {}
            if "usageMetadata" in result:
                usage = {
                    "input_tokens": result["usageMetadata"].get("promptTokenCount", 0),
                    "output_tokens": result["usageMetadata"].get("candidatesTokenCount", 0)
                }

            return {
                "content": content,
                "model": self.model,
                "usage": usage
            }

    async def cleanup_old_analyses(self, older_than_hours: int = 24):
        """Remove old analysis data to free up space."""
        await self.db.execute(text("""
            DELETE FROM optimization_analysis
            WHERE analysis_id IN (
                SELECT id FROM ai_analysis_sessions
                WHERE created_at < NOW() - INTERVAL ':hours hours'
            )
        """), {"hours": older_than_hours})

        await self.db.execute(text("""
            DELETE FROM ai_analysis_sessions
            WHERE created_at < NOW() - INTERVAL ':hours hours'
        """), {"hours": older_than_hours})

        await self.db.commit()
        logger.info(f"Cleaned up analyses older than {older_than_hours} hours")

    # Helper methods
    def _parse_value(self, value: str) -> Any:
        """Parse string value to appropriate type."""
        if value is None or value == '' or value == '-':
            return None
        try:
            if '.' in str(value):
                return float(value)
            return int(value)
        except (ValueError, TypeError):
            return value

    def _parse_percent(self, value: str) -> Optional[float]:
        """Parse percentage string like '5.2%' to float."""
        if value is None or value == '' or value == '-':
            return None
        try:
            return float(str(value).replace('%', ''))
        except (ValueError, TypeError):
            return None

    def _parse_time(self, value: str) -> Optional[float]:
        """Parse time string like '2h 30m' to minutes."""
        if value is None or value == '' or value == '-':
            return None
        try:
            # Simple parsing - assumes minutes or hours format
            val = str(value).lower()
            if 'h' in val and 'm' in val:
                parts = val.replace('h', ' ').replace('m', '').split()
                return float(parts[0]) * 60 + float(parts[1])
            elif 'h' in val:
                return float(val.replace('h', '').strip()) * 60
            elif 'm' in val:
                return float(val.replace('m', '').strip())
            return float(value)
        except (ValueError, TypeError):
            return None

    def _calculate_param_frequencies(self, configs: List[Dict]) -> Dict[str, Dict]:
        """Calculate parameter value frequencies from top configs."""
        if not configs:
            return {}

        freq = {}
        for config in configs:
            for key, value in config.items():
                if key not in freq:
                    freq[key] = {}
                str_val = str(value)
                freq[key][str_val] = freq[key].get(str_val, 0) + 1

        # Sort by frequency
        for key in freq:
            freq[key] = dict(sorted(freq[key].items(), key=lambda x: -x[1])[:5])

        return freq

    def _format_param_freq(self, freq: Dict) -> str:
        """Format parameter frequencies for context."""
        if not freq:
            return "데이터 없음"

        lines = []
        for param, values in freq.items():
            top_vals = [f"{v}: {c}회" for v, c in list(values.items())[:3]]
            lines.append(f"- {param}: {', '.join(top_vals)}")
        return '\n'.join(lines)
