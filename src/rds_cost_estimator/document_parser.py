"""
문서 파일 텍스트 추출 및 Bedrock 파싱 모듈.

이 모듈은 PDF, DOCX, TXT 파일에서 텍스트를 추출하고
AWS Bedrock(Claude 모델)을 호출하여 인스턴스 사양 정보를 파싱하는
DocumentParser 클래스를 제공합니다.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Literal

from rds_cost_estimator.exceptions import UnsupportedFileFormatError
from rds_cost_estimator.models import ParsedDocumentInfo

if TYPE_CHECKING:
    from rds_cost_estimator.bedrock_client import BedrockClient

# 모듈 레벨 로거 설정
logger = logging.getLogger(__name__)

# 지원하는 파일 형식 목록
SUPPORTED_FORMATS: list[str] = [".pdf", ".docx", ".txt", ".md"]


class DocumentParser:
    """문서 파일에서 텍스트를 추출하고 Bedrock으로 인스턴스 사양 정보를 파싱하는 클래스.

    PDF, DOCX, TXT 파일 형식을 지원하며, 각 형식에 맞는 라이브러리를 사용하여
    텍스트를 추출한 뒤 AWS Bedrock Claude 모델에 전달하여 구조화된 정보를 반환합니다.

    Attributes:
        _bedrock_client: Bedrock API 호출을 담당하는 클라이언트 인스턴스
    """

    def __init__(self, bedrock_client: "BedrockClient") -> None:
        """DocumentParser 초기화.

        Args:
            bedrock_client: AWS Bedrock Runtime 클라이언트 인스턴스
        """
        # Bedrock 클라이언트 저장
        self._bedrock_client = bedrock_client

    def parse(self, file_path: str) -> ParsedDocumentInfo:
        """파일 형식을 감지하고 텍스트를 추출한 뒤 Bedrock으로 파싱.

        파일 경로를 받아 형식을 감지하고, 해당 형식에 맞는 방법으로 텍스트를 추출한 뒤
        Bedrock Claude 모델을 호출하여 인스턴스 사양 정보를 파싱합니다.

        Args:
            file_path: 파싱할 문서 파일 경로 (PDF, DOCX, TXT 지원)

        Returns:
            Bedrock이 문서에서 추출한 인스턴스 사양 정보

        Raises:
            UnsupportedFileFormatError: 지원하지 않는 파일 형식인 경우
            DocumentParseError: Bedrock API 호출 실패 또는 응답 파싱 실패 시
        """
        logger.info("문서 파싱 시작: %s", file_path)

        # 파일에서 텍스트 추출
        text = self._extract_text(file_path)
        logger.debug("텍스트 추출 완료: %d자", len(text))

        # Bedrock 클라이언트를 통해 인스턴스 사양 정보 파싱
        result = self._bedrock_client.invoke(text)
        logger.info("문서 파싱 완료: %s", file_path)

        return result

    def _extract_text(self, file_path: str) -> str:
        """파일 형식별 텍스트 추출.

        파일 형식을 감지하여 적절한 라이브러리로 텍스트를 추출합니다:
        - PDF: pypdf.PdfReader로 페이지별 텍스트 추출 후 결합
        - DOCX: docx.Document로 단락(paragraph) 텍스트 추출 후 결합
        - TXT: 내장 open()으로 UTF-8 직접 읽기

        Args:
            file_path: 텍스트를 추출할 파일 경로

        Returns:
            추출된 텍스트 문자열

        Raises:
            UnsupportedFileFormatError: 지원하지 않는 파일 형식인 경우
        """
        # 파일 형식 감지
        fmt = self._detect_format(file_path)

        if fmt == "pdf":
            # PDF: pypdf 라이브러리로 페이지별 텍스트 추출
            return self._extract_text_from_pdf(file_path)
        elif fmt == "docx":
            # DOCX: python-docx 라이브러리로 단락 텍스트 추출
            return self._extract_text_from_docx(file_path)
        elif fmt == "md":
            # MD: 내장 open()으로 UTF-8 직접 읽기 (TXT와 동일)
            return self._extract_text_from_txt(file_path)
        else:
            # TXT: 내장 open()으로 UTF-8 직접 읽기
            return self._extract_text_from_txt(file_path)

    def _detect_format(self, file_path: str) -> Literal["pdf", "docx", "txt", "md"]:
        """파일 확장자로 형식 감지.

        파일 경로에서 확장자를 추출하여 지원하는 형식인지 확인합니다.
        확장자는 소문자로 변환하여 비교합니다.

        Args:
            file_path: 형식을 감지할 파일 경로

        Returns:
            감지된 파일 형식 ("pdf", "docx", "txt" 중 하나)

        Raises:
            UnsupportedFileFormatError: 지원하지 않는 파일 형식인 경우
        """
        # 파일 경로에서 확장자 추출 (소문자 변환)
        # 예: "/path/to/file.PDF" → ".pdf"
        dot_index = file_path.rfind(".")
        if dot_index == -1:
            # 확장자가 없는 경우
            ext = ""
        else:
            ext = file_path[dot_index:].lower()

        # 지원하는 형식 매핑
        if ext == ".pdf":
            return "pdf"
        elif ext == ".docx":
            return "docx"
        elif ext == ".txt":
            return "txt"
        elif ext == ".md":
            return "md"
        else:
            # 지원하지 않는 형식이면 예외 발생
            logger.warning("지원하지 않는 파일 형식: %s (확장자: %s)", file_path, ext)
            raise UnsupportedFileFormatError(file_path, SUPPORTED_FORMATS)

    def _extract_text_from_pdf(self, file_path: str) -> str:
        """PDF 파일에서 텍스트 추출.

        pypdf.PdfReader를 사용하여 각 페이지의 텍스트를 추출하고
        줄바꿈으로 결합합니다.

        Args:
            file_path: PDF 파일 경로

        Returns:
            추출된 텍스트 (페이지별 텍스트를 "\n"으로 결합)
        """
        import pypdf  # PDF 텍스트 추출 라이브러리

        logger.debug("PDF 텍스트 추출 시작: %s", file_path)

        # PdfReader로 PDF 파일 열기
        reader = pypdf.PdfReader(file_path)

        # 각 페이지에서 텍스트 추출
        page_texts: list[str] = []
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                page_texts.append(page_text)

        # 페이지별 텍스트를 줄바꿈으로 결합
        result = "\n".join(page_texts)
        logger.debug("PDF 텍스트 추출 완료: %d페이지, %d자", len(reader.pages), len(result))

        return result

    def _extract_text_from_docx(self, file_path: str) -> str:
        """DOCX 파일에서 텍스트 추출.

        python-docx 라이브러리를 사용하여 각 단락(paragraph)의 텍스트를 추출하고
        줄바꿈으로 결합합니다.

        Args:
            file_path: DOCX 파일 경로

        Returns:
            추출된 텍스트 (단락별 텍스트를 "\n"으로 결합)
        """
        import docx  # python-docx 라이브러리 (Word 문서 처리)

        logger.debug("DOCX 텍스트 추출 시작: %s", file_path)

        # Document 객체로 DOCX 파일 열기
        document = docx.Document(file_path)

        # 각 단락에서 텍스트 추출
        paragraph_texts: list[str] = [
            paragraph.text for paragraph in document.paragraphs
        ]

        # 단락별 텍스트를 줄바꿈으로 결합
        result = "\n".join(paragraph_texts)
        logger.debug(
            "DOCX 텍스트 추출 완료: %d단락, %d자",
            len(document.paragraphs),
            len(result),
        )

        return result

    def _extract_text_from_txt(self, file_path: str) -> str:
        """TXT 파일에서 텍스트 추출.

        내장 open() 함수를 사용하여 UTF-8 인코딩으로 파일을 직접 읽습니다.

        Args:
            file_path: TXT 파일 경로

        Returns:
            파일 전체 내용 문자열
        """
        logger.debug("TXT 텍스트 추출 시작: %s", file_path)

        # UTF-8 인코딩으로 텍스트 파일 직접 읽기
        with open(file_path, "r", encoding="utf-8") as f:
            result = f.read()

        logger.debug("TXT 텍스트 추출 완료: %d자", len(result))

        return result
