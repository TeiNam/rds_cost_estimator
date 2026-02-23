"""
AWS Bedrock Runtime 클라이언트 모듈.

이 모듈은 AWS Bedrock Claude 모델을 호출하여 문서에서
인스턴스 사양 정보를 추출하는 BedrockClient 클래스를 제공합니다.
"""

from __future__ import annotations

import json
import logging
import re

import boto3

from rds_cost_estimator.exceptions import DocumentParseError
from rds_cost_estimator.models import ParsedDocumentInfo

# 모듈 레벨 로거 설정
logger = logging.getLogger(__name__)


class BedrockClient:
    """AWS Bedrock Runtime 클라이언트.

    Claude 모델을 호출하여 문서 텍스트에서 인스턴스 사양 정보를 추출합니다.

    Attributes:
        _client: boto3 bedrock-runtime 클라이언트
        _model_id: 사용할 Bedrock 모델 ID
    """

    def __init__(self, session: boto3.Session, model_id: str) -> None:
        """BedrockClient 초기화.

        Args:
            session: AWS 자격증명이 설정된 boto3 Session
            model_id: 호출할 Bedrock 모델 ID (예: "anthropic.claude-3-5-sonnet-20241022-v2:0")
        """
        # boto3 Session으로 bedrock-runtime 클라이언트 생성
        self._client = session.client("bedrock-runtime")
        # 사용할 모델 ID 저장
        self._model_id = model_id

    def invoke(self, document_text: str) -> ParsedDocumentInfo:
        """Bedrock Claude 모델을 호출하여 문서에서 인스턴스 사양 정보를 추출.

        Args:
            document_text: 분석할 문서 텍스트

        Returns:
            문서에서 추출된 인스턴스 사양 정보

        Raises:
            DocumentParseError: Bedrock API 호출 실패 또는 응답 파싱 실패 시
        """
        # 구조화된 JSON 출력을 요청하는 프롬프트 생성
        prompt = self._build_prompt(document_text)

        # Bedrock API 요청 body 구성 (Anthropic Messages API 형식)
        request_body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 1024,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
        }

        logger.debug("Bedrock 모델 호출 시작: model_id=%s", self._model_id)

        try:
            # bedrock-runtime InvokeModel API 호출
            response = self._client.invoke_model(
                modelId=self._model_id,
                body=json.dumps(request_body),
                contentType="application/json",
                accept="application/json",
            )
        except Exception as e:
            # API 호출 실패 시 DocumentParseError로 래핑
            logger.error("Bedrock API 호출 실패: %s", e)
            raise DocumentParseError(f"Bedrock API 호출 실패: {e}") from e

        # 응답 body 읽기 및 JSON 파싱
        try:
            response_body = json.loads(response["body"].read())
        except Exception as e:
            logger.error("Bedrock 응답 body 파싱 실패: %s", e)
            raise DocumentParseError(f"Bedrock 응답 body 파싱 실패: {e}") from e

        logger.debug("Bedrock 모델 호출 성공, 응답 파싱 시작")

        # 응답에서 ParsedDocumentInfo 추출 및 반환
        return self._parse_response(response_body)

    def _build_prompt(self, document_text: str) -> str:
        """구조화된 JSON 출력을 요청하는 프롬프트 생성.

        Args:
            document_text: 분석할 문서 텍스트

        Returns:
            Bedrock에 전달할 완성된 프롬프트 문자열
        """
        # 설계 문서에 정의된 프롬프트 템플릿 사용
        prompt = (
            "다음 문서에서 서버/인스턴스 사양 정보를 추출하여 아래 JSON 형식으로만 응답하세요.\n"
            "찾을 수 없는 필드는 null로 표시하세요.\n\n"
            "{\n"
            '  "current_instance": "현재 인스턴스 유형 (예: db.r6i.xlarge)",\n'
            '  "recommended_instance": "권장 인스턴스 유형 (없으면 null)",\n'
            '  "on_prem_cost": 온프레미스 연간 유지비용 숫자 (USD, 없으면 null),\n'
            '  "engine": "DB 엔진 (예: oracle-ee, aurora-postgresql, 없으면 null)",\n'
            '  "metadata": {}\n'
            "}\n\n"
            "문서 내용:\n"
            f"{document_text}"
        )
        return prompt

    def _parse_response(self, response_body: dict) -> ParsedDocumentInfo:
        """Bedrock 응답에서 JSON을 추출하여 ParsedDocumentInfo로 변환.

        Args:
            response_body: Bedrock InvokeModel API의 응답 body (dict)

        Returns:
            파싱된 인스턴스 사양 정보

        Raises:
            DocumentParseError: JSON 추출 또는 모델 변환 실패 시
        """
        # 응답 content에서 텍스트 추출 (Anthropic Messages API 형식)
        try:
            text = response_body["content"][0]["text"]
        except (KeyError, IndexError, TypeError) as e:
            logger.error("Bedrock 응답 구조 파싱 실패: %s", e)
            raise DocumentParseError(
                f"Bedrock 응답에서 텍스트를 추출할 수 없습니다: {e}"
            ) from e

        logger.debug("Bedrock 응답 텍스트 추출 완료, JSON 파싱 시작")

        # ```json ... ``` 코드 블록이 있는 경우 내용만 추출
        json_block_pattern = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)
        match = json_block_pattern.search(text)
        if match:
            # 코드 블록 내부의 JSON만 사용
            json_text = match.group(1).strip()
            logger.debug("JSON 코드 블록 감지, 블록 내용 추출")
        else:
            # 코드 블록 없이 순수 JSON 텍스트인 경우
            json_text = text.strip()

        # JSON 파싱
        try:
            parsed_dict = json.loads(json_text)
        except json.JSONDecodeError as e:
            logger.error("JSON 파싱 실패: %s\n텍스트: %s", e, json_text)
            raise DocumentParseError(
                f"Bedrock 응답 JSON 파싱 실패: {e}"
            ) from e

        # ParsedDocumentInfo Pydantic 모델로 변환
        try:
            result = ParsedDocumentInfo(**parsed_dict)
        except Exception as e:
            logger.error("ParsedDocumentInfo 모델 변환 실패: %s", e)
            raise DocumentParseError(
                f"Bedrock 응답을 ParsedDocumentInfo로 변환 실패: {e}"
            ) from e

        logger.debug(
            "문서 파싱 완료: current_instance=%s, engine=%s",
            result.current_instance,
            result.engine,
        )
        return result
