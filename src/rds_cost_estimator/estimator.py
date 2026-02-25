"""
핵심 오케스트레이션 로직 모듈.

CLI 인수를 받아 InstanceSpec 목록을 생성하고,
AWS Pricing API를 병렬로 호출하여 비용 데이터를 수집합니다.
TemplateBuilder에 위임하여 템플릿 데이터를 구성합니다.
DuckDB를 통해 파싱 데이터를 저장하고 리포트 데이터를 추출합니다.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

import boto3

from rds_cost_estimator.bedrock_client import BedrockClient
from rds_cost_estimator.db_store import DuckDBStore
from rds_cost_estimator.document_parser import DocumentParser
from rds_cost_estimator.exceptions import InvalidInputError
from rds_cost_estimator.instance_utils import (
    AURORA_ENGINES,
    AURORA_STORAGE_PER_GB,
    AURORA_IO_PER_MILLION,
    AURORA_BACKUP_PER_GB,
    GRAVITON_FAMILIES,
    ORACLE_ENGINES,
    REFACTORING_ENGINE,
    extract_family_and_size,
    get_all_network_keys,
    get_instance_specs,
    expand_instance_families,
    find_matching_instance,
    calc_storage_costs,
    calc_aurora_storage_costs,
)
from rds_cost_estimator.models import (
    CLIArgs,
    CostRecord,
    InstanceFamily,
    InstanceSpec,
    MigrationStrategy,
    ParsedDocumentInfo,
    PricingType,
)
from rds_cost_estimator.pricing_client import PricingClient
from rds_cost_estimator.template_builder import TemplateBuilder

logger = logging.getLogger(__name__)


class Estimator:
    """비용 예측기 핵심 오케스트레이션 클래스."""

    def __init__(self, args: CLIArgs) -> None:
        self._args = args
        if args.profile:
            self._session = boto3.Session(profile_name=args.profile)
        else:
            self._session = boto3.Session()
        self._pricing_client = PricingClient(self._session, cache={})
        self._db_store: Optional[DuckDBStore] = None

    def _merge_parsed_info(self, parsed: ParsedDocumentInfo) -> None:
        """ParsedDocumentInfo의 필드로 CLIArgs의 누락 필드를 보완."""
        if self._args.current_instance is None and parsed.current_instance is not None:
            self._args.current_instance = parsed.current_instance
        if (
            self._args.recommended_instance_by_size is None
            and parsed.recommended_instance_by_size is not None
        ):
            self._args.recommended_instance_by_size = parsed.recommended_instance_by_size
        if (
            self._args.recommended_instance_by_sga is None
            and parsed.recommended_instance_by_sga is not None
        ):
            self._args.recommended_instance_by_sga = parsed.recommended_instance_by_sga
        if self._args.on_prem_cost is None and parsed.on_prem_cost is not None:
            self._args.on_prem_cost = parsed.on_prem_cost
        # 타겟 엔진 결정: target_engine > engine (소스 엔진은 무시)
        if parsed.target_engine is not None:
            self._args.engine = parsed.target_engine
        elif parsed.engine is not None and self._args.engine == "oracle-ee":
            # target_engine이 없으면 기존 로직 유지 (소스 엔진 사용)
            self._args.engine = parsed.engine

    async def run_v2(self) -> dict:
        """템플릿 v2 기반 비용 예측 실행. DuckDB에 데이터를 저장하고 리포트 데이터를 추출."""
        args = self._args
        parsed_info: Optional[ParsedDocumentInfo] = None

        # DuckDB 저장소를 컨텍스트 매니저로 안전하게 관리
        with DuckDBStore() as store:
            self._db_store = store

            # 문서 파싱
            if args.input_file is not None:
                logger.info("문서 파일 파싱 시작: %s", args.input_file)
                bedrock_client = BedrockClient(
                    session=self._session, model_id=args.bedrock_model,
                )
                parser = DocumentParser(bedrock_client=bedrock_client)
                parsed_info = parser.parse(args.input_file)
                self._merge_parsed_info(parsed_info)
                logger.info("문서 파싱 완료")

            if parsed_info is None:
                parsed_info = ParsedDocumentInfo()

            # DuckDB에 파싱 데이터 저장
            self._db_store.store_parsed_info(parsed_info)

            # 인스턴스 사양 매칭 - 동적 패밀리 추출
            spec_base = args.recommended_instance_by_size or args.current_instance
            sga_base = args.recommended_instance_by_sga

            # 기본 패밀리와 대안 패밀리 결정
            spec_families = self._resolve_family_pair(spec_base)
            sga_families = self._resolve_family_pair(sga_base)

            family_a = spec_families[0] if spec_families else "r6i"
            family_b = spec_families[1] if len(spec_families) > 1 else None

            # 패밀리별 인스턴스 타입 매핑
            spec_instances: dict[str, str] = {}
            sga_instances: dict[str, str] = {}

            if spec_base:
                parsed = extract_family_and_size(spec_base)
                if parsed:
                    base_family, size = parsed
                    spec_instances[base_family] = spec_base
                    for fam in spec_families:
                        if fam != base_family:
                            spec_instances[fam] = f"db.{fam}.{size}"

            if sga_base:
                parsed = extract_family_and_size(sga_base)
                if parsed:
                    base_family, size = parsed
                    sga_instances[base_family] = sga_base
                    for fam in sga_families:
                        if fam != base_family:
                            sga_instances[fam] = f"db.{fam}.{size}"

            # 가격 조회 대상 인스턴스
            target_instances: set[str] = set()
            target_instances.update(spec_instances.values())
            target_instances.update(sga_instances.values())

            # Single-AZ + Multi-AZ 스펙 생성 (Replatform)
            all_specs: list[InstanceSpec] = []
            for inst in target_instances:
                for deploy in ["Single-AZ", "Multi-AZ"]:
                    all_specs.append(InstanceSpec(
                        instance_type=inst,
                        region=args.region,
                        engine=args.engine,
                        strategy=MigrationStrategy.REPLATFORM,
                        deployment_option=deploy,
                    ))

            # Oracle 엔진일 때 Refactoring(Aurora PostgreSQL) 스펙 추가
            if args.engine in ORACLE_ENGINES:
                for inst in target_instances:
                    for deploy in ["Single-AZ", "Multi-AZ"]:
                        all_specs.append(InstanceSpec(
                            instance_type=inst,
                            region=args.region,
                            engine=REFACTORING_ENGINE,
                            strategy=MigrationStrategy.REFACTORING,
                            deployment_option=deploy,
                        ))

            logger.info("v2 InstanceSpec %d개 생성, 병렬 가격 조회 시작", len(all_specs))

            # 병렬 가격 조회
            results = await asyncio.gather(
                *[self._pricing_client.fetch_all(spec) for spec in all_specs]
            )
            all_records = [r for spec_records in results for r in spec_records]

            # DuckDB에 가격 데이터 저장
            self._db_store.store_pricing_records(all_records)

            # RI 폴백: is_available=False인 RI 레코드에 대해 RDS API로 조회
            await self._apply_ri_fallback()

            # 레코드를 인덱싱 (Replatform 전용)
            price_index: dict[tuple[str, str, PricingType], CostRecord] = {}
            for rec in all_records:
                if rec.spec.strategy == MigrationStrategy.REPLATFORM:
                    key = (rec.spec.instance_type, rec.spec.deployment_option, rec.pricing_type)
                    price_index[key] = rec

            # Refactoring 전용 인덱스 (Aurora PostgreSQL)
            refac_price_index: dict[tuple[str, str, PricingType], CostRecord] = {}
            for rec in all_records:
                if rec.spec.strategy == MigrationStrategy.REFACTORING:
                    key = (rec.spec.instance_type, rec.spec.deployment_option, rec.pricing_type)
                    refac_price_index[key] = rec

            # 폴백 적용된 레코드 반영
            self._sync_fallback_to_index(price_index, all_records)

            # TemplateBuilder에 위임하여 템플릿 데이터 구성
            builder = TemplateBuilder(self._db_store, self._args)
            data = builder.build(
                parsed_info, price_index, refac_price_index,
                spec_instances, sga_instances,
                family_a, family_b,
            )

        return data

    def _resolve_family_pair(self, instance_type: Optional[str]) -> list[str]:
        """인스턴스 타입에서 기본 패밀리와 대안 패밀리를 결정합니다.

        Oracle 엔진이면 Graviton 제외, 동일 카테고리에서 최대 2개 패밀리 반환.
        """
        if not instance_type:
            return []
        parsed = extract_family_and_size(instance_type)
        if not parsed:
            return []

        family, _ = parsed
        is_oracle = self._args.engine in ORACLE_ENGINES
        same_cat = InstanceFamily.same_category_families(family)

        result: list[str] = [family]  # 기본 패밀리 우선
        for fam in same_cat:
            if fam == family:
                continue
            if is_oracle and fam in GRAVITON_FAMILIES:
                continue
            result.append(fam)
            if len(result) >= 2:
                break

        return result

    async def _apply_ri_fallback(self) -> None:
        """RI 가격이 없는 레코드에 대해 DescribeReservedDBInstancesOfferings API로 조회합니다."""
        if not self._db_store:
            return

        unavailable = self._db_store.get_unavailable_ri_records()
        if not unavailable:
            return

        logger.info(
            "RI 폴백 대상 %d건 발견, DescribeReservedDBInstancesOfferings API 조회 시작",
            len(unavailable),
        )

        for rec in unavailable:
            spec = InstanceSpec(
                instance_type=rec["instance_type"],
                region=rec["region"],
                engine=rec["engine"],
                strategy=MigrationStrategy.REPLATFORM,
                deployment_option=rec["deployment_option"],
            )
            pt_val = rec["pricing_type"]

            result = await self._pricing_client.fetch_ri_offering(spec, pt_val)
            if result and result.monthly_cost is not None:
                self._db_store.update_pricing_record(
                    rec["instance_type"],
                    rec["deployment_option"],
                    pt_val,
                    round(result.monthly_cost, 2),
                    round(result.annual_cost or 0, 2),
                )
                logger.info(
                    "RI 폴백 적용: %s / %s / %s → $%.2f/월",
                    rec["instance_type"], rec["deployment_option"],
                    pt_val, result.monthly_cost,
                )
            else:
                logger.warning(
                    "RI 폴백 실패: %s / %s / %s",
                    rec["instance_type"], rec["deployment_option"], pt_val,
                )

    def _sync_fallback_to_index(
        self,
        price_index: dict[tuple[str, str, PricingType], CostRecord],
        all_records: list[CostRecord],
    ) -> None:
        """DuckDB에서 폴백 적용된 레코드를 price_index에 반영합니다."""
        if not self._db_store:
            return

        for rec in all_records:
            if rec.is_available:
                continue

            pt_val = rec.pricing_type.value
            updated = self._db_store.get_pricing(
                rec.spec.instance_type, rec.spec.deployment_option, pt_val
            )
            if updated and updated.get("is_available"):
                # 폴백으로 업데이트된 레코드 반영
                rec.is_available = True
                rec.monthly_fee = updated["monthly_cost"]
                rec.annual_cost = updated["annual_cost"]
                key = (rec.spec.instance_type, rec.spec.deployment_option, rec.pricing_type)
                price_index[key] = rec

    # ------------------------------------------------------------------
    # TemplateBuilder 위임 메서드 (기존 테스트 호환성 유지)
    # ------------------------------------------------------------------

    def _build_template_data(
        self,
        parsed: ParsedDocumentInfo,
        price_index: dict,
        refac_price_index: dict,
        spec_instances: dict[str, str],
        sga_instances: dict[str, str],
        family_a: str,
        family_b: Optional[str],
    ) -> dict:
        """TemplateBuilder.build에 위임합니다."""
        builder = TemplateBuilder(self._db_store, self._args)
        return builder.build(
            parsed, price_index, refac_price_index,
            spec_instances, sga_instances, family_a, family_b,
        )

    def _fill_network_costs(self, data: dict, growth_rate: float) -> None:
        """TemplateBuilder._fill_network_costs에 위임합니다."""
        builder = TemplateBuilder(self._db_store, self._args)
        builder._fill_network_costs(data, growth_rate)

    def _fill_network_defaults(self, data: dict) -> None:
        """TemplateBuilder._fill_network_defaults에 위임합니다."""
        builder = TemplateBuilder(self._db_store, self._args)
        builder._fill_network_defaults(data)

    def _fill_tco(self, data: dict, families: list[str], db_size: float,
                  growth_rate: float, prov_iops: int, prov_tp: float,
                  region: str = "ap-northeast-2") -> None:
        """TemplateBuilder._fill_tco에 위임합니다."""
        builder = TemplateBuilder(self._db_store, self._args)
        builder._fill_tco(data, families, db_size, growth_rate, prov_iops, prov_tp, region)

    def _fill_refactoring_comparison(
        self, data: dict, refac_price_index: dict,
        sga_instances: dict[str, str], families: list[str],
    ) -> None:
        """TemplateBuilder._fill_refactoring_comparison에 위임합니다."""
        builder = TemplateBuilder(self._db_store, self._args)
        builder._fill_refactoring_comparison(data, refac_price_index, sga_instances, families)

    def _fill_refactoring_defaults(self, data: dict, families: list[str]) -> None:
        """TemplateBuilder._fill_refactoring_defaults에 위임합니다."""
        builder = TemplateBuilder(self._db_store, self._args)
        builder._fill_refactoring_defaults(data, families)
