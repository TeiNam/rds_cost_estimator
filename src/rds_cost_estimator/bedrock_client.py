"""
AWS Bedrock Runtime 클라이언트 모듈.

이 모듈은 AWS Bedrock Claude 모델을 호출하여 문서에서
인스턴스 사양 정보와 AWR 메트릭을 추출하는 BedrockClient 클래스를 제공합니다.
"""

from __future__ import annotations

import json
import logging
import re

import boto3

from rds_cost_estimator.exceptions import DocumentParseError
from rds_cost_estimator.models import (
    AWRMetrics,
    ParsedDocumentInfo,
    SGAAnalysis,
    StorageGrowth,
)

# 모듈 레벨 로거 설정
logger = logging.getLogger(__name__)


class BedrockClient:
    """AWS Bedrock Runtime 클라이언트."""

    def __init__(self, session: boto3.Session, model_id: str) -> None:
        self._client = session.client("bedrock-runtime")
        self._model_id = model_id

    def invoke(self, document_text: str) -> ParsedDocumentInfo:
        """Bedrock Claude 모델을 호출하여 문서에서 정보를 추출."""
        prompt = self._build_prompt(document_text)

        request_body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 4096,
            "messages": [
                {"role": "user", "content": prompt}
            ],
        }

        logger.debug("Bedrock 모델 호출 시작: model_id=%s", self._model_id)

        try:
            response = self._client.invoke_model(
                modelId=self._model_id,
                body=json.dumps(request_body),
                contentType="application/json",
                accept="application/json",
            )
        except Exception as e:
            logger.error("Bedrock API 호출 실패: %s", e)
            raise DocumentParseError(f"Bedrock API 호출 실패: {e}") from e

        try:
            response_body = json.loads(response["body"].read())
        except Exception as e:
            logger.error("Bedrock 응답 body 파싱 실패: %s", e)
            raise DocumentParseError(f"Bedrock 응답 body 파싱 실패: {e}") from e

        logger.debug("Bedrock 모델 호출 성공, 응답 파싱 시작")
        return self._parse_response(response_body)

    def _build_prompt(self, document_text: str) -> str:
        """템플릿 v2에 필요한 모든 필드를 추출하는 프롬프트 생성."""
        prompt = (
            "다음 문서에서 서버/인스턴스 사양 정보와 AWR 성능 메트릭을 추출하여 "
            "아래 JSON 형식으로만 응답하세요.\n"
            "찾을 수 없는 필드는 null로 표시하세요.\n\n"
            "문서에는 두 가지 타입의 권장 인스턴스가 있을 수 있습니다:\n"
            "1. recommended_instance_by_size: 현재 서버의 CPU/메모리 사양과 비슷한 크기의 RDS 인스턴스\n"
            "2. recommended_instance_by_sga: Oracle SGA 메모리 기준으로 산정한 RDS 인스턴스\n\n"
            "인스턴스 유형은 'db.' 접두사를 포함한 전체 이름으로 추출하세요.\n\n"
            "AWR 메트릭에서 다음 항목을 추출하세요:\n"
            "- CPU 사용률 % (평균/피크) - os_cpu 또는 퍼센트로 표시된 값\n"
            "- CPU/s (평균/피크) - 초당 CPU 사용량 절대값 (cpu_per_s). "
            "DBCSI 리포트에서 '평균 CPU/s', '최대 CPU/s' 형태로 표시됨\n"
            "- IOPS (평균/피크)\n"
            "- 메모리 사용량 (평균/피크)\n"
            "- 네트워크 트래픽 (일별 바이트 단위로 변환하여 응답):\n"
            "  * AWR .out 파일의 SYSSTAT 섹션에 network_incoming_mb, network_outgoing_mb 컬럼이 있음\n"
            "    이 값은 스냅샷 기간(dur_m분) 동안의 MB 값임. 일별 바이트로 변환: MB × (1440/dur_m) × 1024 × 1024\n"
            "    network_outgoing_mb → sqlnet_bytes_sent_per_day, network_incoming_mb → sqlnet_bytes_received_per_day\n"
            "  * MAIN-METRICS 섹션의 redo_mb_s (초당 MB) → 일별 바이트: redo_mb_s × 86400 × 1024 × 1024\n"
            "  * 여러 스냅샷이 있으면 평균값을 사용하세요\n"
            "  * RAC 환경(인스턴스 2개 이상)이면 모든 인스턴스의 합산값을 사용하세요\n"
            "  * DBCSI 리포트(MD)에 SQL*Net bytes 데이터가 있으면 그것을 우선 사용하세요\n"
            "- Redo 생성량 (일별 바이트)\n\n"
            "SGA 분석에서 다음 항목을 추출하세요:\n"
            "- 현재 SGA 크기 (GB)\n"
            "- 권장 SGA 크기 (GB)\n\n"
            "스토리지 정보에서 다음 항목을 추출하세요:\n"
            "- 현재 DB 크기 (GB)\n"
            "- 연간 증가량 (GB) 또는 증가율 (%)\n\n"
            "{\n"
            '  "db_name": "데이터베이스 이름 (없으면 null)",\n'
            '  "oracle_version": "Oracle 버전 (없으면 null)",\n'
            '  "current_instance": "현재 인스턴스 유형 (예: db.r6i.xlarge, 없으면 null)",\n'
            '  "recommended_instance_by_size": "현재 사이즈 기준 권장 인스턴스 (없으면 null)",\n'
            '  "recommended_instance_by_sga": "SGA 기준 권장 인스턴스 (없으면 null)",\n'
            '  "on_prem_cost": null,\n'
            '  "engine": "소스 DB 엔진 (예: oracle-ee, 없으면 null)",\n'
            '  "target_engine": "마이그레이션 타겟 엔진. 문서에 추천 타겟이 명시되어 있으면 해당 값을 사용 '
            '(aurora-postgresql, aurora-mysql, postgresql, mysql 중 하나, 없으면 null)",\n'
            '  "cpu_cores": "CPU 코어 수 (숫자, 없으면 null)",\n'
            '  "num_cpus": "논리 CPU 수 (하이퍼스레딩 포함, 숫자, 없으면 null)",\n'
            '  "physical_memory_gb": "물리 메모리 GB (숫자, 없으면 null)",\n'
            '  "db_size_gb": "전체 DB 크기 GB (숫자, 없으면 null)",\n'
            '  "instance_config": "인스턴스 구성 설명 (예: 2 (RAC), 없으면 null)",\n'
            '  "awr_metrics": {\n'
            '    "avg_cpu_percent": "평균 CPU 사용률 % (숫자, 없으면 null)",\n'
            '    "peak_cpu_percent": "피크 CPU 사용률 % (숫자, 없으면 null)",\n'
            '    "avg_cpu_per_s": "평균 CPU/s 초당 CPU 사용량 절대값 (숫자, 없으면 null)",\n'
            '    "peak_cpu_per_s": "피크(최대) CPU/s 초당 CPU 사용량 절대값 (숫자, 없으면 null)",\n'
            '    "avg_iops": "평균 IOPS (숫자, 없으면 null)",\n'
            '    "peak_iops": "피크 IOPS (숫자, 없으면 null)",\n'
            '    "avg_memory_gb": "평균 메모리 사용량 GB (숫자, 없으면 null)",\n'
            '    "peak_memory_gb": "피크 메모리 사용량 GB (숫자, 없으면 null)",\n'
            '    "sqlnet_bytes_sent_per_day": "네트워크 송신 일별 바이트. AWR SYSSTAT의 network_outgoing_mb를 일별 바이트로 변환한 값 (숫자, 없으면 null)",\n'
            '    "sqlnet_bytes_received_per_day": "네트워크 수신 일별 바이트. AWR SYSSTAT의 network_incoming_mb를 일별 바이트로 변환한 값 (숫자, 없으면 null)",\n'
            '    "redo_bytes_per_day": "Redo 생성량 일별 바이트. AWR MAIN-METRICS의 redo_mb_s를 일별 바이트로 변환한 값 (숫자, 없으면 null)"\n'
            '  },\n'
            '  "sga_analysis": {\n'
            '    "current_sga_gb": "현재 SGA 크기 GB (숫자, 없으면 null)",\n'
            '    "recommended_sga_gb": "권장 SGA 크기 GB (숫자, 없으면 null)",\n'
            '    "sga_increase_rate_percent": "SGA 증가율 % (숫자, 없으면 null)"\n'
            '  },\n'
            '  "storage_growth": {\n'
            '    "current_db_size_gb": "현재 DB 크기 GB (숫자, 없으면 null)",\n'
            '    "yearly_growth_gb": "연간 증가량 GB (숫자, 없으면 null)",\n'
            '    "yearly_growth_rate_percent": "연간 증가율 % (숫자, 없으면 15)"\n'
            '  },\n'
            '  "provisioned_iops": "추가 프로비저닝 IOPS (3000 초과분, 숫자, 없으면 null)",\n'
            '  "provisioned_throughput_mbps": "추가 프로비저닝 처리량 MB/s (125 초과분, 숫자, 없으면 null)",\n'
            '  "metadata": {}\n'
            "}\n\n"
            "문서 내용:\n"
            f"{document_text}"
        )
        return prompt

    def _parse_response(self, response_body: dict) -> ParsedDocumentInfo:
        """Bedrock 응답에서 JSON을 추출하여 ParsedDocumentInfo로 변환."""
        try:
            text = response_body["content"][0]["text"]
        except (KeyError, IndexError, TypeError) as e:
            logger.error("Bedrock 응답 구조 파싱 실패: %s", e)
            raise DocumentParseError(
                f"Bedrock 응답에서 텍스트를 추출할 수 없습니다: {e}"
            ) from e

        logger.debug("Bedrock 응답 텍스트 추출 완료, JSON 파싱 시작")

        # ```json ... ``` 코드 블록 추출
        json_block_pattern = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)
        match = json_block_pattern.search(text)
        if match:
            json_text = match.group(1).strip()
        else:
            json_text = text.strip()

        try:
            parsed_dict = json.loads(json_text)
        except json.JSONDecodeError as e:
            logger.error("JSON 파싱 실패: %s\n텍스트: %s", e, json_text)
            raise DocumentParseError(f"Bedrock 응답 JSON 파싱 실패: {e}") from e

        # 중첩 모델 변환
        try:
            if "awr_metrics" in parsed_dict and isinstance(parsed_dict["awr_metrics"], dict):
                parsed_dict["awr_metrics"] = AWRMetrics(**parsed_dict["awr_metrics"])
            if "sga_analysis" in parsed_dict and isinstance(parsed_dict["sga_analysis"], dict):
                parsed_dict["sga_analysis"] = SGAAnalysis(**parsed_dict["sga_analysis"])
            if "storage_growth" in parsed_dict and isinstance(parsed_dict["storage_growth"], dict):
                parsed_dict["storage_growth"] = StorageGrowth(**parsed_dict["storage_growth"])

            result = ParsedDocumentInfo(**parsed_dict)
        except Exception as e:
            logger.error("ParsedDocumentInfo 모델 변환 실패: %s", e)
            raise DocumentParseError(
                f"Bedrock 응답을 ParsedDocumentInfo로 변환 실패: {e}"
            ) from e

        logger.debug(
            "문서 파싱 완료: db_name=%s, db_size=%s GB",
            result.db_name,
            result.db_size_gb,
        )
        return result
