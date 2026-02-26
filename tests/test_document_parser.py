"""
DocumentParser 단위 테스트 모듈.

SUPPORTED_FORMATS 상수 및 직접 파싱 기능을 검증합니다.
"""

import pytest

from rds_cost_estimator.document_parser import DocumentParser, SUPPORTED_FORMATS


@pytest.fixture
def parser() -> DocumentParser:
    """테스트용 DocumentParser 인스턴스 (Bedrock 클라이언트 불필요)."""
    return DocumentParser()


class TestSupportedFormatsConstant:
    """SUPPORTED_FORMATS 상수 테스트."""

    def test_supported_formats_contains_pdf(self) -> None:
        """SUPPORTED_FORMATS에 .pdf가 포함되는지 확인."""
        assert ".pdf" in SUPPORTED_FORMATS

    def test_supported_formats_contains_docx(self) -> None:
        """SUPPORTED_FORMATS에 .docx가 포함되는지 확인."""
        assert ".docx" in SUPPORTED_FORMATS

    def test_supported_formats_contains_txt(self) -> None:
        """SUPPORTED_FORMATS에 .txt가 포함되는지 확인."""
        assert ".txt" in SUPPORTED_FORMATS

    def test_supported_formats_contains_md(self) -> None:
        """SUPPORTED_FORMATS에 .md가 포함되는지 확인."""
        assert ".md" in SUPPORTED_FORMATS
