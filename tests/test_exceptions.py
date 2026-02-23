"""
예외 클래스 단위 테스트 모듈.

각 커스텀 예외 클래스의 인스턴스화, 속성, 상속 관계를 검증합니다.
"""

import pytest

from rds_cost_estimator.exceptions import (
    DocumentParseError,
    InvalidInputError,
    PricingAPIError,
    PricingDataNotFoundError,
    RDSCostEstimatorError,
    UnsupportedFileFormatError,
)


class TestRDSCostEstimatorError:
    """기본 예외 클래스 테스트."""

    def test_instantiation(self) -> None:
        """RDSCostEstimatorError가 올바르게 인스턴스화되는지 확인."""
        err = RDSCostEstimatorError("기본 오류 메시지")
        assert str(err) == "기본 오류 메시지"

    def test_is_exception_subclass(self) -> None:
        """RDSCostEstimatorError가 Exception의 하위 클래스인지 확인."""
        assert issubclass(RDSCostEstimatorError, Exception)

    def test_can_be_raised(self) -> None:
        """RDSCostEstimatorError를 raise할 수 있는지 확인."""
        with pytest.raises(RDSCostEstimatorError):
            raise RDSCostEstimatorError("테스트 오류")


class TestPricingAPIError:
    """PricingAPIError 예외 클래스 테스트."""

    def test_instantiation_without_spec(self) -> None:
        """instance_spec 없이 PricingAPIError가 인스턴스화되는지 확인."""
        err = PricingAPIError("API 호출 실패")
        assert str(err) == "API 호출 실패"
        assert err.instance_spec is None

    def test_instantiation_with_spec(self) -> None:
        """instance_spec과 함께 PricingAPIError가 인스턴스화되는지 확인."""
        # 간단한 객체를 instance_spec으로 사용
        mock_spec = object()
        err = PricingAPIError("API 호출 실패", instance_spec=mock_spec)
        assert err.instance_spec is mock_spec

    def test_instance_spec_attribute_exists(self) -> None:
        """PricingAPIError에 instance_spec 속성이 있는지 확인."""
        err = PricingAPIError("오류")
        assert hasattr(err, "instance_spec")

    def test_is_rds_cost_estimator_error_subclass(self) -> None:
        """PricingAPIError가 RDSCostEstimatorError의 하위 클래스인지 확인."""
        assert issubclass(PricingAPIError, RDSCostEstimatorError)

    def test_can_be_caught_as_base_error(self) -> None:
        """PricingAPIError를 RDSCostEstimatorError로 잡을 수 있는지 확인."""
        with pytest.raises(RDSCostEstimatorError):
            raise PricingAPIError("API 오류")


class TestInvalidInputError:
    """InvalidInputError 예외 클래스 테스트."""

    def test_instantiation(self) -> None:
        """InvalidInputError가 올바르게 인스턴스화되는지 확인."""
        err = InvalidInputError("유효하지 않은 입력값")
        assert str(err) == "유효하지 않은 입력값"

    def test_is_rds_cost_estimator_error_subclass(self) -> None:
        """InvalidInputError가 RDSCostEstimatorError의 하위 클래스인지 확인."""
        assert issubclass(InvalidInputError, RDSCostEstimatorError)

    def test_can_be_raised(self) -> None:
        """InvalidInputError를 raise할 수 있는지 확인."""
        with pytest.raises(InvalidInputError):
            raise InvalidInputError("on_prem_cost는 0보다 커야 합니다")


class TestPricingDataNotFoundError:
    """PricingDataNotFoundError 예외 클래스 테스트."""

    def test_instantiation(self) -> None:
        """PricingDataNotFoundError가 올바르게 인스턴스화되는지 확인."""
        err = PricingDataNotFoundError("가격 데이터 없음")
        assert str(err) == "가격 데이터 없음"

    def test_is_rds_cost_estimator_error_subclass(self) -> None:
        """PricingDataNotFoundError가 RDSCostEstimatorError의 하위 클래스인지 확인."""
        assert issubclass(PricingDataNotFoundError, RDSCostEstimatorError)

    def test_can_be_raised(self) -> None:
        """PricingDataNotFoundError를 raise할 수 있는지 확인."""
        with pytest.raises(PricingDataNotFoundError):
            raise PricingDataNotFoundError("db.r6i.xlarge 가격 없음")


class TestDocumentParseError:
    """DocumentParseError 예외 클래스 테스트."""

    def test_instantiation(self) -> None:
        """DocumentParseError가 올바르게 인스턴스화되는지 확인."""
        err = DocumentParseError("문서 파싱 실패")
        assert str(err) == "문서 파싱 실패"

    def test_is_rds_cost_estimator_error_subclass(self) -> None:
        """DocumentParseError가 RDSCostEstimatorError의 하위 클래스인지 확인."""
        assert issubclass(DocumentParseError, RDSCostEstimatorError)

    def test_can_be_raised(self) -> None:
        """DocumentParseError를 raise할 수 있는지 확인."""
        with pytest.raises(DocumentParseError):
            raise DocumentParseError("Bedrock API 호출 실패")


class TestUnsupportedFileFormatError:
    """UnsupportedFileFormatError 예외 클래스 테스트."""

    def test_instantiation(self) -> None:
        """UnsupportedFileFormatError가 올바르게 인스턴스화되는지 확인."""
        err = UnsupportedFileFormatError(
            "/path/to/file.xlsx",
            [".pdf", ".docx", ".txt"],
        )
        # 메시지에 파일 경로와 지원 형식이 포함되어야 함
        assert "/path/to/file.xlsx" in str(err)
        assert ".pdf" in str(err)

    def test_file_path_attribute(self) -> None:
        """UnsupportedFileFormatError에 file_path 속성이 있는지 확인."""
        err = UnsupportedFileFormatError("/path/to/file.csv", [".pdf", ".docx", ".txt"])
        assert hasattr(err, "file_path")
        assert err.file_path == "/path/to/file.csv"

    def test_supported_formats_attribute(self) -> None:
        """UnsupportedFileFormatError에 supported_formats 속성이 있는지 확인."""
        supported = [".pdf", ".docx", ".txt"]
        err = UnsupportedFileFormatError("/path/to/file.xlsx", supported)
        assert hasattr(err, "supported_formats")
        assert err.supported_formats == supported

    def test_is_rds_cost_estimator_error_subclass(self) -> None:
        """UnsupportedFileFormatError가 RDSCostEstimatorError의 하위 클래스인지 확인."""
        assert issubclass(UnsupportedFileFormatError, RDSCostEstimatorError)

    def test_can_be_caught_as_base_error(self) -> None:
        """UnsupportedFileFormatError를 RDSCostEstimatorError로 잡을 수 있는지 확인."""
        with pytest.raises(RDSCostEstimatorError):
            raise UnsupportedFileFormatError("/file.xlsx", [".pdf"])


class TestAllExceptionsAreSubclasses:
    """모든 예외가 RDSCostEstimatorError의 하위 클래스인지 일괄 확인."""

    def test_all_custom_exceptions_inherit_base(self) -> None:
        """모든 커스텀 예외가 RDSCostEstimatorError를 상속하는지 확인."""
        custom_exceptions = [
            PricingAPIError,
            InvalidInputError,
            PricingDataNotFoundError,
            DocumentParseError,
            UnsupportedFileFormatError,
        ]
        for exc_class in custom_exceptions:
            assert issubclass(exc_class, RDSCostEstimatorError), (
                f"{exc_class.__name__}이 RDSCostEstimatorError를 상속하지 않습니다"
            )
