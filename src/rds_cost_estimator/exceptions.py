"""
커스텀 예외 클래스 계층 정의 모듈.

예외 계층 구조:
    Exception
    └── RDSCostEstimatorError
        ├── PricingAPIError
        ├── InvalidInputError
        ├── PricingDataNotFoundError
        ├── DocumentParseError
        └── UnsupportedFileFormatError
"""

from __future__ import annotations


class RDSCostEstimatorError(Exception):
    """RDS Cost Estimator의 기본 예외 클래스.

    모든 커스텀 예외는 이 클래스를 상속합니다.
    """

    pass


class PricingAPIError(RDSCostEstimatorError):
    """AWS Pricing API 호출 실패 시 발생하는 예외.

    네트워크 오류, 권한 오류 등 API 호출 자체가 실패한 경우에 사용합니다.

    Args:
        message: 오류 설명 메시지.
        instance_spec: 오류가 발생한 인스턴스 사양 (선택 사항).
    """

    def __init__(self, message: str, instance_spec: object | None = None) -> None:
        super().__init__(message)
        # 오류가 발생한 인스턴스 사양 정보 보존 (디버깅 용도)
        self.instance_spec = instance_spec


class InvalidInputError(RDSCostEstimatorError):
    """사용자 입력값이 유효하지 않을 때 발생하는 예외.

    예: on_prem_cost <= 0 처럼 비즈니스 규칙에 위반되는 입력값.
    """

    pass


class PricingDataNotFoundError(RDSCostEstimatorError):
    """특정 인스턴스 유형의 가격 데이터가 없을 때 발생하는 예외.

    해당 인스턴스 항목은 N/A로 처리되며, 나머지 조회는 계속 진행됩니다.
    """

    pass


class DocumentParseError(RDSCostEstimatorError):
    """Bedrock API 호출 실패 또는 응답 파싱 실패 시 발생하는 예외.

    AWS Bedrock Runtime InvokeModel 호출이 실패하거나,
    응답 JSON을 ParsedDocumentInfo 모델로 변환하는 데 실패한 경우에 사용합니다.
    """

    pass


class UnsupportedFileFormatError(RDSCostEstimatorError):
    """지원하지 않는 파일 형식이 입력되었을 때 발생하는 예외.

    DocumentParser가 .pdf, .docx, .txt 이외의 확장자를 감지한 경우에 사용합니다.

    Args:
        file_path: 지원하지 않는 파일의 경로.
        supported_formats: 지원하는 파일 형식 목록 (예: [".pdf", ".docx", ".txt"]).
    """

    def __init__(self, file_path: str, supported_formats: list[str]) -> None:
        # 사용자에게 지원 형식을 안내하는 메시지 생성
        supported_str = ", ".join(supported_formats)
        message = (
            f"지원하지 않는 파일 형식입니다: '{file_path}'. "
            f"지원 형식: {supported_str}"
        )
        super().__init__(message)
        # 오류 발생 파일 경로 및 지원 형식 정보 보존
        self.file_path = file_path
        self.supported_formats = supported_formats
