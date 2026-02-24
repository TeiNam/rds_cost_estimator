"""
문서 파일 텍스트 추출 및 Bedrock 파싱 모듈.

이 모듈은 PDF, DOCX, TXT 파일에서 텍스트를 추출하고
AWS Bedrock(Claude 모델)을 호출하여 인스턴스 사양 정보를 파싱하는
DocumentParser 클래스를 제공합니다.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Literal

from rds_cost_estimator.exceptions import UnsupportedFileFormatError
from rds_cost_estimator.models import ParsedDocumentInfo

if TYPE_CHECKING:
    from rds_cost_estimator.bedrock_client import BedrockClient

# 모듈 레벨 로거 설정
logger = logging.getLogger(__name__)

# 지원하는 파일 형식 목록
SUPPORTED_FORMATS: list[str] = [".pdf", ".docx", ".txt", ".md", ".out"]


class DocumentParser:
    """문서 파일에서 텍스트를 추출하고 Bedrock으로 인스턴스 사양 정보를 파싱하는 클래스.

    단일 파일 또는 디렉토리를 입력받을 수 있습니다.
    디렉토리 입력 시 폴더 내 모든 지원 파일(PDF/DOCX/TXT/MD)의 텍스트를
    합쳐서 Bedrock에 전달합니다.

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
        """파일 또는 디렉토리를 입력받아 텍스트를 추출한 뒤 Bedrock으로 파싱.

        디렉토리 입력 시 폴더 내 모든 지원 파일의 텍스트를 합쳐서
        하나의 컨텍스트로 Bedrock에 전달합니다.
        AWR .out 파일이 있으면 네트워크/Redo 데이터를 직접 파싱하여 보완합니다.

        Args:
            file_path: 파싱할 문서 파일 또는 디렉토리 경로

        Returns:
            Bedrock이 문서에서 추출한 인스턴스 사양 정보

        Raises:
            UnsupportedFileFormatError: 지원하지 않는 파일 형식인 경우
            DocumentParseError: Bedrock API 호출 실패 또는 응답 파싱 실패 시
        """
        logger.info("문서 파싱 시작: %s", file_path)

        # 디렉토리인 경우 폴더 내 모든 지원 파일 텍스트 합치기
        if os.path.isdir(file_path):
            text = self._extract_text_from_directory(file_path)
        else:
            text = self._extract_text(file_path)

        logger.debug("텍스트 추출 완료: %d자", len(text))

        # Bedrock 클라이언트를 통해 인스턴스 사양 정보 파싱
        result = self._bedrock_client.invoke(text)
        logger.info("문서 파싱 완료: %s", file_path)

        # AWR .out 파일에서 네트워크/Redo 데이터 직접 파싱하여 보완
        self._supplement_awr_network_data(file_path, result)

        # migration_recommendation.md에서 타겟 엔진 직접 파싱하여 보완
        self._supplement_target_engine(file_path, result)

        return result

    def _extract_text_from_directory(self, dir_path: str) -> str:
        """디렉토리 내 모든 지원 파일에서 텍스트를 추출하여 합칩니다.

        지원 파일 형식(PDF/DOCX/TXT/MD)만 대상으로 하며,
        파일명 기준 정렬 후 각 파일의 텍스트를 구분자와 함께 결합합니다.

        Args:
            dir_path: 탐색할 디렉토리 경로

        Returns:
            모든 파일의 텍스트를 합친 문자열

        Raises:
            UnsupportedFileFormatError: 디렉토리에 지원 파일이 없는 경우
        """
        logger.info("디렉토리 내 파일 탐색 시작: %s", dir_path)

        # 지원 파일 확장자 필터링
        supported_files: list[str] = []
        for entry in sorted(os.listdir(dir_path)):
            entry_path = os.path.join(dir_path, entry)
            if not os.path.isfile(entry_path):
                continue
            dot_index = entry.rfind(".")
            if dot_index == -1:
                continue
            ext = entry[dot_index:].lower()
            if ext in (".pdf", ".docx", ".txt", ".md", ".out"):
                supported_files.append(entry_path)

        if not supported_files:
            logger.warning("디렉토리에 지원 파일 없음: %s", dir_path)
            raise UnsupportedFileFormatError(dir_path, SUPPORTED_FORMATS)

        logger.info("디렉토리에서 %d개 파일 발견: %s",
                     len(supported_files),
                     [os.path.basename(f) for f in supported_files])

        # 각 파일의 텍스트를 구분자와 함께 결합
        text_parts: list[str] = []
        for fpath in supported_files:
            fname = os.path.basename(fpath)
            logger.debug("파일 텍스트 추출: %s", fname)
            file_text = self._extract_text(fpath)
            text_parts.append(
                f"=== 파일: {fname} ===\n{file_text}"
            )

        combined = "\n\n".join(text_parts)
        logger.info("디렉토리 텍스트 합치기 완료: %d개 파일, 총 %d자",
                     len(supported_files), len(combined))
        return combined

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
        elif ext == ".out":
            # AWR .out 파일은 텍스트 형식으로 처리
            return "txt"
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

    def _supplement_awr_network_data(
        self, file_path: str, parsed: ParsedDocumentInfo
    ) -> None:
        """AWR .out 파일에서 네트워크/Redo 데이터를 직접 파싱하여 보완합니다.

        Bedrock이 AWR .out 파일의 넓은 테이블에서 네트워크 컬럼을 정확히
        추출하지 못하는 경우를 대비하여, 직접 파싱합니다.
        이미 Bedrock이 값을 추출한 경우에는 덮어쓰지 않습니다.

        파싱 대상:
        - SYSSTAT 섹션: network_incoming_mb, network_outgoing_mb
        - MAIN-METRICS 섹션: redo_mb_s, dur_m (스냅샷 기간)
        """
        # Bedrock이 이미 네트워크 데이터를 추출한 경우 스킵
        awr = parsed.awr_metrics
        if (awr.sqlnet_bytes_sent_per_day is not None
                and awr.sqlnet_bytes_received_per_day is not None
                and awr.redo_bytes_per_day is not None):
            return

        # AWR .out 파일 찾기
        out_files = self._find_awr_out_files(file_path)
        if not out_files:
            logger.debug("AWR .out 파일 없음, 네트워크 데이터 보완 스킵")
            return

        for out_file in out_files:
            logger.info("AWR .out 파일 직접 파싱: %s", out_file)
            net_data = self._parse_awr_out_network(out_file)
            if not net_data:
                continue

            # Bedrock이 추출하지 못한 필드만 보완
            if awr.sqlnet_bytes_sent_per_day is None and net_data.get("sent_bytes_per_day"):
                awr.sqlnet_bytes_sent_per_day = net_data["sent_bytes_per_day"]
                logger.info("네트워크 송신 보완: %.0f bytes/일", awr.sqlnet_bytes_sent_per_day)

            if awr.sqlnet_bytes_received_per_day is None and net_data.get("recv_bytes_per_day"):
                awr.sqlnet_bytes_received_per_day = net_data["recv_bytes_per_day"]
                logger.info("네트워크 수신 보완: %.0f bytes/일", awr.sqlnet_bytes_received_per_day)

            if awr.redo_bytes_per_day is None and net_data.get("redo_bytes_per_day"):
                awr.redo_bytes_per_day = net_data["redo_bytes_per_day"]
                logger.info("Redo 생성량 보완: %.0f bytes/일", awr.redo_bytes_per_day)

    def _find_awr_out_files(self, file_path: str) -> list[str]:
        """AWR .out 파일을 찾습니다."""
        if os.path.isfile(file_path) and file_path.endswith(".out"):
            return [file_path]

        if os.path.isdir(file_path):
            out_files = []
            for entry in sorted(os.listdir(file_path)):
                if entry.endswith(".out"):
                    out_files.append(os.path.join(file_path, entry))
            return out_files

        return []

    def _parse_awr_out_network(self, out_file: str) -> dict:
        """AWR .out 파일에서 네트워크/Redo 데이터를 파싱합니다.

        SYSSTAT 섹션에서 network_incoming_mb/network_outgoing_mb를,
        MAIN-METRICS 섹션에서 redo_mb_s와 dur_m을 추출합니다.

        Returns:
            dict with keys: sent_bytes_per_day, recv_bytes_per_day, redo_bytes_per_day
        """
        import re

        try:
            with open(out_file, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            logger.warning("AWR .out 파일 읽기 실패: %s - %s", out_file, e)
            return {}

        result: dict = {}

        # MAIN-METRICS 섹션을 먼저 파싱하여 실제 dur_m 확보
        main_metrics = self._parse_main_metrics_section(content)

        # SYSSTAT 섹션 파싱: network_incoming_mb, network_outgoing_mb
        sysstat_data = self._parse_sysstat_section(content)
        if sysstat_data:
            # SYSSTAT의 값은 스냅샷 기간(보통 60분) 동안의 MB 값
            # MAIN-METRICS에서 실제 dur_m을 가져와 사용
            dur_m = (main_metrics or {}).get("dur_m") or sysstat_data.get("dur_m", 60)
            # 일별로 변환: MB × (1440 / dur_m) × 1024 × 1024
            factor = (1440.0 / dur_m) * 1024 * 1024

            if sysstat_data.get("network_outgoing_mb") is not None:
                result["sent_bytes_per_day"] = sysstat_data["network_outgoing_mb"] * factor

            if sysstat_data.get("network_incoming_mb") is not None:
                result["recv_bytes_per_day"] = sysstat_data["network_incoming_mb"] * factor

        # MAIN-METRICS 섹션에서 redo_mb_s 추출 (이미 위에서 파싱됨)
        if main_metrics and main_metrics.get("redo_mb_s") is not None:
            # redo_mb_s는 초당 MB → 일별 바이트: × 86400 × 1024 × 1024
            result["redo_bytes_per_day"] = (
                main_metrics["redo_mb_s"] * 86400 * 1024 * 1024
            )

        return result

    def _parse_sysstat_section(self, content: str) -> dict:
        """AWR .out의 SYSSTAT 섹션에서 네트워크 데이터를 파싱합니다.

        여러 스냅샷의 평균값을 반환합니다.
        """
        import re

        # SYSSTAT 섹션 추출
        match = re.search(
            r"~~BEGIN-SYSSTAT~~\s*\n(.*?)~~END-SYSSTAT~~",
            content, re.DOTALL
        )
        if not match:
            return {}

        section = match.group(1)
        lines = section.strip().split("\n")

        # 헤더 행 찾기
        header_line = None
        data_start = 0
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("SNAP_ID") or "network_incoming_mb" in stripped:
                header_line = stripped
                data_start = i + 1
                break

        if not header_line:
            return {}

        # 헤더에서 컬럼 인덱스 찾기
        headers = header_line.split()
        col_map = {h: idx for idx, h in enumerate(headers)}

        incoming_idx = col_map.get("network_incoming_mb")
        outgoing_idx = col_map.get("network_outgoing_mb")

        if incoming_idx is None and outgoing_idx is None:
            return {}

        # 구분선 건너뛰기
        for i in range(data_start, len(lines)):
            if lines[i].strip().startswith("---"):
                data_start = i + 1
                break

        # 데이터 행 파싱
        incoming_vals: list[float] = []
        outgoing_vals: list[float] = []

        for i in range(data_start, len(lines)):
            line = lines[i].strip()
            if not line or line.startswith("~~"):
                break
            cols = line.split()
            if len(cols) <= max(incoming_idx or 0, outgoing_idx or 0):
                continue
            try:
                if incoming_idx is not None:
                    incoming_vals.append(float(cols[incoming_idx]))
                if outgoing_idx is not None:
                    outgoing_vals.append(float(cols[outgoing_idx]))
            except (ValueError, IndexError):
                continue

        result: dict = {}
        if incoming_vals:
            result["network_incoming_mb"] = sum(incoming_vals) / len(incoming_vals)
        if outgoing_vals:
            result["network_outgoing_mb"] = sum(outgoing_vals) / len(outgoing_vals)

        # dur_m은 MAIN-METRICS에서 가져오지만, 기본값 60분 사용
        result["dur_m"] = 60

        return result

    def _parse_main_metrics_section(self, content: str) -> dict:
        """AWR .out의 MAIN-METRICS 섹션에서 redo_mb_s와 dur_m을 파싱합니다.

        여러 스냅샷/인스턴스의 평균값을 반환합니다.
        """
        import re

        # MAIN-METRICS 섹션 추출
        match = re.search(
            r"~~BEGIN-MAIN-METRICS~~\s*\n(.*?)~~END-MAIN-METRICS~~",
            content, re.DOTALL
        )
        if not match:
            return {}

        section = match.group(1)
        lines = section.strip().split("\n")

        # 헤더 행 찾기
        header_line = None
        data_start = 0
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("snap") or "redo_mb_s" in stripped:
                header_line = stripped
                data_start = i + 1
                break

        if not header_line:
            return {}

        # 헤더에서 컬럼 인덱스 찾기
        headers = header_line.split()
        col_map = {h: idx for idx, h in enumerate(headers)}

        redo_idx = col_map.get("redo_mb_s")
        dur_idx = col_map.get("dur_m")

        if redo_idx is None:
            return {}

        # 구분선 건너뛰기
        for i in range(data_start, len(lines)):
            if lines[i].strip().startswith("---"):
                data_start = i + 1
                break

        # 데이터 행 파싱
        redo_vals: list[float] = []
        dur_vals: list[float] = []

        for i in range(data_start, len(lines)):
            line = lines[i].strip()
            if not line or line.startswith("~~"):
                break
            cols = line.split()
            if len(cols) <= redo_idx:
                continue
            try:
                redo_vals.append(float(cols[redo_idx]))
                if dur_idx is not None and len(cols) > dur_idx:
                    dur_vals.append(float(cols[dur_idx]))
            except (ValueError, IndexError):
                continue

        result: dict = {}
        if redo_vals:
            result["redo_mb_s"] = sum(redo_vals) / len(redo_vals)
        if dur_vals:
            result["dur_m"] = sum(dur_vals) / len(dur_vals)

        return result

    # 타겟 엔진 키워드 → 엔진 코드 매핑
    _TARGET_ENGINE_MAP: dict[str, str] = {
        "aurora postgresql": "aurora-postgresql",
        "aurora postgres": "aurora-postgresql",
        "aurora mysql": "aurora-mysql",
        "rds for postgresql": "postgresql",
        "rds postgresql": "postgresql",
        "rds for mysql": "mysql",
        "rds mysql": "mysql",
        "rds for sql server": "sqlserver-ee",
        "rds sql server": "sqlserver-ee",
        "rds for oracle": "oracle-ee",
    }

    def _supplement_target_engine(
        self, file_path: str, parsed: "ParsedDocumentInfo"
    ) -> None:
        """migration_recommendation.md에서 '추천 타겟' 필드를 파싱하여 target_engine을 보완합니다.

        Bedrock이 소스 엔진(oracle-ee)을 반환하는 경우가 많으므로,
        migration_recommendation.md의 '추천 타겟' 텍스트에서 타겟 엔진을 직접 추출합니다.
        """
        if parsed.target_engine is not None:
            return

        # migration_recommendation.md 파일 찾기
        rec_file = self._find_migration_recommendation(file_path)
        if not rec_file:
            return

        try:
            with open(rec_file, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            logger.warning("migration_recommendation.md 읽기 실패: %s", e)
            return

        # "**추천 타겟**: Aurora PostgreSQL" 패턴 매칭
        import re
        match = re.search(
            r"\*\*추천\s*타겟\*\*\s*:\s*(.+)",
            content,
        )
        if not match:
            return

        target_text = match.group(1).strip().lower()
        for keyword, engine_code in self._TARGET_ENGINE_MAP.items():
            if keyword in target_text:
                parsed.target_engine = engine_code
                logger.info(
                    "migration_recommendation.md에서 타겟 엔진 추출: %s → %s",
                    match.group(1).strip(), engine_code,
                )
                return

    def _find_migration_recommendation(self, file_path: str) -> str | None:
        """입력 경로에서 migration_recommendation.md 파일을 찾습니다."""
        if os.path.isdir(file_path):
            candidate = os.path.join(file_path, "migration_recommendation.md")
            if os.path.isfile(candidate):
                return candidate
        elif os.path.isfile(file_path):
            # 같은 디렉토리에서 찾기
            parent = os.path.dirname(file_path)
            candidate = os.path.join(parent, "migration_recommendation.md")
            if os.path.isfile(candidate):
                return candidate
        return None

