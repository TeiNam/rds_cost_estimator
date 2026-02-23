"""
핵심 오케스트레이션 로직 모듈.

이 모듈은 CLI 인수를 받아 InstanceSpec 목록을 생성하고,
AWS Pricing API를 병렬로 호출하여 CostTable을 구성하는
Estimator 클래스를 제공합니다.

참고 요구사항: 2.1, 2.6, 3.1, 3.2, 3.5, 5.7, 7.4, 8.7, 8.8
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

import boto3

from rds_cost_estimator.bedrock_client import BedrockClient
from rds_cost_estimator.cost_table import CostTable
from rds_cost_estimator.document_parser import DocumentParser
from rds_cost_estimator.exceptions import InvalidInputError
from rds_cost_estimator.models import (
    CLIArgs,
    InstanceSpec,
    MigrationStrategy,
    ParsedDocumentInfo,
)
from rds_cost_estimator.pricing_client import PricingClient

# 모듈 레벨 로거 설정
logger = logging.getLogger(__name__)

# Refactoring 전략에서 고정으로 사용하는 엔진
REFACTORING_ENGINE = "aurora-postgresql"


class Estimator:
    """비용 예측기 핵심 오케스트레이션 클래스.

    CLI 인수를 받아 InstanceSpec 목록을 생성하고,
    AWS Pricing API를 병렬로 호출하여 CostTable을 구성합니다.

    Attributes:
        _args: CLI 인수 파싱 결과
        _session: AWS boto3 세션
        _pricing_client: AWS Pricing API 클라이언트
    """

    def __init__(self, args: CLIArgs) -> None:
        """Estimator 초기화.

        --profile 옵션이 있으면 해당 프로파일로 boto3 Session을 생성하고,
        없으면 기본 자격증명으로 Session을 생성합니다.

        Args:
            args: CLI 인수 파싱 결과 (CLIArgs 모델)
        """
        # CLI 인수 저장
        self._args = args

        # --profile 옵션에 따라 boto3 Session 생성 (요구사항 5.7)
        if args.profile:
            logger.debug("AWS 프로파일 사용: %s", args.profile)
            self._session = boto3.Session(profile_name=args.profile)
        else:
            logger.debug("기본 AWS 자격증명 사용")
            self._session = boto3.Session()

        # PricingClient 초기화 (인메모리 캐시 딕셔너리 주입)
        self._pricing_client = PricingClient(self._session, cache={})

    def _build_specs(self) -> list[InstanceSpec]:
        """InstanceSpec 목록 생성.

        current_instance × [REPLATFORM, REFACTORING] 조합과
        recommended_instance × [REPLATFORM, REFACTORING] 조합으로
        총 4개의 InstanceSpec을 생성합니다.

        - REPLATFORM 전략: args.engine 사용 (예: "oracle-ee")
        - REFACTORING 전략: "aurora-postgresql" 고정

        Returns:
            4개의 InstanceSpec 목록

        Note:
            current_instance와 recommended_instance가 None이면
            해당 조합은 생략됩니다.
        """
        specs: list[InstanceSpec] = []
        args = self._args

        # 인스턴스 유형 목록 (None 제외)
        instances: list[tuple[Optional[str], str]] = []
        if args.current_instance:
            instances.append((args.current_instance, "current"))
        if args.recommended_instance:
            instances.append((args.recommended_instance, "recommended"))

        for instance_type, _ in instances:
            if instance_type is None:
                continue

            # REPLATFORM 전략: args.engine 사용 (요구사항 3.1)
            specs.append(
                InstanceSpec(
                    instance_type=instance_type,
                    region=args.region,
                    engine=args.engine,
                    strategy=MigrationStrategy.REPLATFORM,
                )
            )

            # REFACTORING 전략: aurora-postgresql 고정 (요구사항 3.2)
            specs.append(
                InstanceSpec(
                    instance_type=instance_type,
                    region=args.region,
                    engine=REFACTORING_ENGINE,
                    strategy=MigrationStrategy.REFACTORING,
                )
            )

        logger.debug("InstanceSpec 목록 생성 완료: %d개", len(specs))
        return specs

    def _merge_parsed_info(self, parsed: ParsedDocumentInfo) -> None:
        """ParsedDocumentInfo의 필드로 CLIArgs의 누락 필드를 보완.

        CLI 인수가 우선이며, CLI 인수에 값이 없는 경우에만 문서 파싱 결과로 보완합니다.
        (요구사항 8.7)

        Args:
            parsed: Bedrock이 문서에서 추출한 인스턴스 사양 정보
        """
        # current_instance: CLI 인수 우선, 없으면 문서 파싱 결과 사용
        if self._args.current_instance is None and parsed.current_instance is not None:
            logger.debug(
                "current_instance를 문서 파싱 결과로 보완: %s", parsed.current_instance
            )
            self._args.current_instance = parsed.current_instance

        # recommended_instance: CLI 인수 우선, 없으면 문서 파싱 결과 사용
        if (
            self._args.recommended_instance is None
            and parsed.recommended_instance is not None
        ):
            logger.debug(
                "recommended_instance를 문서 파싱 결과로 보완: %s",
                parsed.recommended_instance,
            )
            self._args.recommended_instance = parsed.recommended_instance

        # on_prem_cost: CLI 인수 우선, 없으면 문서 파싱 결과 사용
        if self._args.on_prem_cost is None and parsed.on_prem_cost is not None:
            logger.debug(
                "on_prem_cost를 문서 파싱 결과로 보완: %s", parsed.on_prem_cost
            )
            self._args.on_prem_cost = parsed.on_prem_cost

        # engine: CLI 인수가 기본값("oracle-ee")이고 문서에서 추출된 값이 있으면 보완
        # (CLIArgs.engine은 기본값이 있으므로 None 체크 대신 기본값 체크)
        if parsed.engine is not None and self._args.engine == "oracle-ee":
            logger.debug("engine을 문서 파싱 결과로 보완: %s", parsed.engine)
            self._args.engine = parsed.engine

    async def run(self) -> CostTable:
        """비용 예측 실행.

        1. on_prem_cost 유효성 검증 (0 이하이면 InvalidInputError 발생)
        2. --input-file 지정 시 BedrockClient + DocumentParser로 문서 파싱 후 누락 필드 보완
        3. _build_specs()로 InstanceSpec 목록 생성
        4. asyncio.gather로 병렬 API 호출
        5. 결과를 평탄화하여 CostRecord 목록 생성
        6. CostTable 생성 후 반환

        Returns:
            비용 비교표 (CostTable 인스턴스)

        Raises:
            InvalidInputError: on_prem_cost가 None이거나 0 이하인 경우 (요구사항 3.5)
        """
        args = self._args

        # --input-file 지정 시 문서 파싱 후 누락 필드 보완 (요구사항 8.7, 8.8)
        if args.input_file is not None:
            logger.info("문서 파일 파싱 시작: %s", args.input_file)
            bedrock_client = BedrockClient(
                session=self._session,
                model_id=args.bedrock_model,
            )
            parser = DocumentParser(bedrock_client=bedrock_client)
            parsed_info = parser.parse(args.input_file)
            # 누락 필드를 문서 파싱 결과로 보완 (CLI 인수 우선)
            self._merge_parsed_info(parsed_info)
            logger.info("문서 파싱 완료, 누락 필드 보완 적용")

        # on_prem_cost 유효성 검증 (요구사항 3.5)
        # None이거나 0 이하이면 InvalidInputError 발생
        if args.on_prem_cost is None or args.on_prem_cost <= 0:
            logger.error(
                "유효하지 않은 온프레미스 비용 입력: %s", args.on_prem_cost
            )
            raise InvalidInputError(
                f"온프레미스 연간 유지비용은 0보다 커야 합니다. "
                f"입력값: {args.on_prem_cost}"
            )

        # InstanceSpec 목록 생성 (요구사항 2.6, 3.1, 3.2)
        specs = self._build_specs()
        logger.info("InstanceSpec %d개 생성, 병렬 가격 조회 시작", len(specs))

        # asyncio.gather로 모든 스펙에 대해 병렬 API 호출 (요구사항 7.4)
        results = await asyncio.gather(
            *[self._pricing_client.fetch_all(spec) for spec in specs]
        )

        # 중첩 리스트를 평탄화하여 CostRecord 목록 생성
        records = [record for spec_records in results for record in spec_records]
        logger.info("가격 조회 완료: 총 %d개의 CostRecord 수집", len(records))

        # CostTable 생성 후 반환
        cost_table = CostTable(records=records, on_prem_annual_cost=args.on_prem_cost)
        return cost_table
