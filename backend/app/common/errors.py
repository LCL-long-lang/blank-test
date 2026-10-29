"""业务异常定义，每类异常对应一个错误码。"""


class AppError(Exception):
    code = "APP_ERROR"
    status_code = 400

    def __init__(self, message: str = ""):
        super().__init__(message)
        self.message = message or self.code


class NotFoundError(AppError):
    code = "NOT_FOUND"
    status_code = 404


class LLMError(AppError):
    code = "LLM_ERROR"
    status_code = 502


class SQLGuardError(AppError):
    code = "SQL_REJECTED"


class SQLExecError(AppError):
    code = "SQL_FAILED"


class ChartError(AppError):
    code = "CHART_UNSUPPORTED"
