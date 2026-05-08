"""
Centralized Error Logger for Live Trading Operations.
Logs errors to both console (via Python logging) and database for permanent storage.
"""
import logging
import traceback
from typing import Optional, Dict, Any
from datetime import datetime
from ..db.session import SessionLocal, db_scope
from ..models.live_trading import TradingErrorLog, ErrorType, ErrorSeverity

logger = logging.getLogger(__name__)


class TradingErrorLogger:
    """
    Singleton error logger that saves trading errors to database.
    Usage:
        from ..services.error_logger import error_logger
        error_logger.log_error(
            error_type=ErrorType.ORDER_FAILED,
            message="Order placement failed",
            session_id="xxx",
            symbol="005930",
            exception=e,
            context={"order_qty": 10, "price": 50000}
        )
    """
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = TradingErrorLogger()
        return cls._instance

    def log_error(
        self,
        error_type: ErrorType,
        message: str,
        session_id: Optional[str] = None,
        symbol: Optional[str] = None,
        severity: ErrorSeverity = ErrorSeverity.ERROR,
        exception: Optional[Exception] = None,
        context: Optional[Dict[str, Any]] = None,
        source_file: Optional[str] = None,
        source_function: Optional[str] = None,
    ) -> Optional[str]:
        """
        Log an error to both console and database.

        Args:
            error_type: Type of error (from ErrorType enum)
            message: Human-readable error message
            session_id: Related trading session ID
            symbol: Related stock symbol
            severity: Error severity level
            exception: The exception object (if any)
            context: Additional context data (dict)
            source_file: Source file where error occurred
            source_function: Function where error occurred

        Returns:
            The error log ID if saved successfully, None otherwise
        """
        # 1. Always log to console
        log_msg = f"[{error_type.value}] {message}"
        if session_id:
            log_msg += f" (session={session_id})"
        if symbol:
            log_msg += f" (symbol={symbol})"

        if severity == ErrorSeverity.CRITICAL:
            logger.critical(log_msg, exc_info=exception is not None)
        elif severity == ErrorSeverity.ERROR:
            logger.error(log_msg, exc_info=exception is not None)
        elif severity == ErrorSeverity.WARNING:
            logger.warning(log_msg)
        else:
            logger.info(log_msg)

        # 2. Save to database
        try:
            with db_scope() as db:
                stack_trace = None
                if exception:
                    stack_trace = ''.join(traceback.format_exception(
                        type(exception), exception, exception.__traceback__
                    ))

                error_log = TradingErrorLog(
                    session_id=session_id,
                    symbol=symbol,
                    error_type=error_type.value,
                    severity=severity.value,
                    error_message=message,
                    stack_trace=stack_trace,
                    context_data=context,
                    source_file=source_file,
                    source_function=source_function,
                    created_at=datetime.utcnow()
                )

                db.add(error_log)
                db.commit()
                db.refresh(error_log)

                return error_log.id

        except Exception as db_err:
            # If we can't log to DB, at least log the failure
            logger.error(f"Failed to save error to database: {db_err}")
            return None

    def log_order_error(
        self,
        message: str,
        session_id: str,
        symbol: str,
        exception: Optional[Exception] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """Convenience method for order-related errors."""
        return self.log_error(
            error_type=ErrorType.ORDER_FAILED,
            message=message,
            session_id=session_id,
            symbol=symbol,
            severity=ErrorSeverity.ERROR,
            exception=exception,
            context=context,
            source_function="order_execution"
        )

    def log_api_error(
        self,
        message: str,
        session_id: Optional[str] = None,
        symbol: Optional[str] = None,
        exception: Optional[Exception] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """Convenience method for API-related errors."""
        return self.log_error(
            error_type=ErrorType.API_ERROR,
            message=message,
            session_id=session_id,
            symbol=symbol,
            severity=ErrorSeverity.ERROR,
            exception=exception,
            context=context,
            source_function="api_call"
        )

    def log_strategy_error(
        self,
        message: str,
        session_id: str,
        symbol: str,
        exception: Optional[Exception] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """Convenience method for strategy execution errors."""
        return self.log_error(
            error_type=ErrorType.STRATEGY_ERROR,
            message=message,
            session_id=session_id,
            symbol=symbol,
            severity=ErrorSeverity.ERROR,
            exception=exception,
            context=context,
            source_function="strategy_execution"
        )

    def log_websocket_error(
        self,
        message: str,
        exception: Optional[Exception] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """Convenience method for WebSocket errors."""
        return self.log_error(
            error_type=ErrorType.WEBSOCKET_ERROR,
            message=message,
            severity=ErrorSeverity.WARNING,
            exception=exception,
            context=context,
            source_function="websocket"
        )

    def log_critical(
        self,
        error_type: ErrorType,
        message: str,
        session_id: Optional[str] = None,
        symbol: Optional[str] = None,
        exception: Optional[Exception] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """Log a critical error that requires immediate attention."""
        return self.log_error(
            error_type=error_type,
            message=message,
            session_id=session_id,
            symbol=symbol,
            severity=ErrorSeverity.CRITICAL,
            exception=exception,
            context=context
        )

    def get_recent_errors(
        self,
        session_id: Optional[str] = None,
        error_type: Optional[ErrorType] = None,
        severity: Optional[ErrorSeverity] = None,
        limit: int = 50
    ) -> list:
        """
        Retrieve recent errors from database.

        Args:
            session_id: Filter by session
            error_type: Filter by error type
            severity: Filter by severity
            limit: Maximum number of errors to return

        Returns:
            List of error log records
        """
        try:
            with db_scope() as db:
                query = db.query(TradingErrorLog)

                if session_id:
                    query = query.filter(TradingErrorLog.session_id == session_id)
                if error_type:
                    query = query.filter(TradingErrorLog.error_type == error_type.value)
                if severity:
                    query = query.filter(TradingErrorLog.severity == severity.value)

                errors = query.order_by(TradingErrorLog.created_at.desc()).limit(limit).all()

                return [{
                    "id": e.id,
                    "session_id": e.session_id,
                    "symbol": e.symbol,
                    "error_type": e.error_type,
                    "severity": e.severity,
                    "error_message": e.error_message,
                    "context_data": e.context_data,
                    "source_function": e.source_function,
                    "is_resolved": e.is_resolved,
                    "created_at": e.created_at.isoformat() if e.created_at else None,
                } for e in errors]

        except Exception as e:
            logger.error(f"Failed to fetch errors: {e}")
            return []

    def get_error_stats(self, hours: int = 24) -> Dict[str, Any]:
        """Get error statistics for the last N hours."""
        from datetime import timedelta

        try:
            with db_scope() as db:
                cutoff = datetime.utcnow() - timedelta(hours=hours)

                errors = db.query(TradingErrorLog).filter(
                    TradingErrorLog.created_at >= cutoff
                ).all()

                stats = {
                    "total": len(errors),
                    "by_type": {},
                    "by_severity": {},
                    "unresolved": 0
                }

                for e in errors:
                    # By type
                    stats["by_type"][e.error_type] = stats["by_type"].get(e.error_type, 0) + 1
                    # By severity
                    stats["by_severity"][e.severity] = stats["by_severity"].get(e.severity, 0) + 1
                    # Unresolved count
                    if not e.is_resolved:
                        stats["unresolved"] += 1

                return stats

        except Exception as e:
            logger.error(f"Failed to get error stats: {e}")
            return {"total": 0, "by_type": {}, "by_severity": {}, "unresolved": 0}


# Global singleton instance
error_logger = TradingErrorLogger.get_instance()
