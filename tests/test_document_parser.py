"""
DocumentParser 단위 테스트 모듈.

_detect_format 메서드의 파일 형식 감지 및 비지원 형식 예외 발생을 검증합니다.
"""

import pytest
from unittest.mock import MagicMock

from rds_cost_estimator.document_parser import DocumentParser, SUPPORTED_FORMATS
from rds_cost_estimator.exceptions import UnsupportedFileFormatError
from rds_cost_estimator.models import ParsedDocumentInfo


@pytest.fixture
def mock_bedrock_client() -> MagicMock:
    """테스트용 가짜 BedrockClient 인스턴스."""
    client = MagicMock()
    # invoke 메서드가 기본 ParsedDocumentInfo를 반환하도록 설정
    client.invoke.return_value = ParsedDocumentInfo(
        current_instance="db.r6i.xlarge",
        engine="oracle-ee",
    )
    return client


@pytest.fixture
def parser(mock_bedrock_client: MagicMock) -> DocumentParser:
    """테스트용 DocumentParser 인스턴스."""
    return DocumentParser(bedrock_client=mock_bedrock_client)


class TestDetectFormatSupportedExtensions:
    """_detect_format: 지원하는 확장자 정상 감지 테스트."""

    def test_detect_pdf_lowercase(self, parser: DocumentParser) -> None:
        """.pdf 확장자를 'pdf'로 감지하는지 확인."""
        result = parser._detect_format("/path/to/document.pdf")
        assert result == "pdf"

    def test_detect_docx_lowercase(self, parser: DocumentParser) -> None:
        """.docx 확장자를 'docx'로 감지하는지 확인."""
        result = parser._detect_format("/path/to/document.docx")
        assert result == "docx"

    def test_detect_txt_lowercase(self, parser: DocumentParser) -> None:
        """.txt 확장자를 'txt'로 감지하는지 확인."""
        result = parser._detect_format("/path/to/document.txt")
        assert result == "txt"

    def test_detect_pdf_uppercase(self, parser: DocumentParser) -> None:
        """대문자 .PDF 확장자도 'pdf'로 감지하는지 확인."""
        result = parser._detect_format("/path/to/document.PDF")
        assert result == "pdf"

    def test_detect_docx_uppercase(self, parser: DocumentParser) -> None:
        """대문자 .DOCX 확장자도 'docx'로 감지하는지 확인."""
        result = parser._detect_format("/path/to/document.DOCX")
        assert result == "docx"

    def test_detect_txt_uppercase(self, parser: DocumentParser) -> None:
        """대문자 .TXT 확장자도 'txt'로 감지하는지 확인."""
        result = parser._detect_format("/path/to/document.TXT")
        assert result == "txt"

    def test_detect_pdf_mixed_case(self, parser: DocumentParser) -> None:
        """혼합 대소문자 .Pdf 확장자도 'pdf'로 감지하는지 확인."""
        result = parser._detect_format("/path/to/document.Pdf")
        assert result == "pdf"

    def test_detect_with_complex_path(self, parser: DocumentParser) -> None:
        """복잡한 경로에서도 확장자를 올바르게 감지하는지 확인."""
        result = parser._detect_format("/home/user/documents/migration.plan.pdf")
        assert result == "pdf"


class TestDetectFormatUnsupportedExtensions:
    """_detect_format: 비지원 확장자에서 UnsupportedFileFormatError 발생 테스트."""

    def test_xlsx_raises_error(self, parser: DocumentParser) -> None:
        """.xlsx 확장자에서 UnsupportedFileFormatError가 발생하는지 확인."""
        with pytest.raises(UnsupportedFileFormatError):
            parser._detect_format("/path/to/file.xlsx")

    def test_csv_raises_error(self, parser: DocumentParser) -> None:
        """.csv 확장자에서 UnsupportedFileFormatError가 발생하는지 확인."""
        with pytest.raises(UnsupportedFileFormatError):
            parser._detect_format("/path/to/file.csv")

    def test_pptx_raises_error(self, parser: DocumentParser) -> None:
        """.pptx 확장자에서 UnsupportedFileFormatError가 발생하는지 확인."""
        with pytest.raises(UnsupportedFileFormatError):
            parser._detect_format("/path/to/file.pptx")

    def test_no_extension_raises_error(self, parser: DocumentParser) -> None:
        """확장자가 없는 파일에서 UnsupportedFileFormatError가 발생하는지 확인."""
        with pytest.raises(UnsupportedFileFormatError):
            parser._detect_format("/path/to/file_without_extension")

    def test_error_contains_file_path(self, parser: DocumentParser) -> None:
        """예외 객체에 file_path 속성이 올바르게 설정되는지 확인."""
        file_path = "/path/to/file.xlsx"
        with pytest.raises(UnsupportedFileFormatError) as exc_info:
            parser._detect_format(file_path)
        assert exc_info.value.file_path == file_path

    def test_error_contains_supported_formats(self, parser: DocumentParser) -> None:
        """예외 객체에 supported_formats 속성이 올바르게 설정되는지 확인."""
        with pytest.raises(UnsupportedFileFormatError) as exc_info:
            parser._detect_format("/path/to/file.xlsx")
        # 지원 형식 목록이 포함되어야 함
        assert ".pdf" in exc_info.value.supported_formats
        assert ".docx" in exc_info.value.supported_formats
        assert ".txt" in exc_info.value.supported_formats

    def test_json_raises_error(self, parser: DocumentParser) -> None:
        """.json 확장자에서 UnsupportedFileFormatError가 발생하는지 확인."""
        with pytest.raises(UnsupportedFileFormatError):
            parser._detect_format("/path/to/file.json")

    def test_html_raises_error(self, parser: DocumentParser) -> None:
        """.html 확장자에서 UnsupportedFileFormatError가 발생하는지 확인."""
        with pytest.raises(UnsupportedFileFormatError):
            parser._detect_format("/path/to/file.html")


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
