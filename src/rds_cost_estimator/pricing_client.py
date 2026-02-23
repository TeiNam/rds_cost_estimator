"""
AWS Pricing API 클라이언트 모듈.

이 모듈은 AWS Pricing API를 호출하여 RDS 인스턴스의 온디맨드 및
예약 인스턴스(RI) 가격을 조회하고, 인메모리 캐시로 중복 호출을 방지합니다.

참고 요구사항: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 7.4
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Literal

import boto3

from rds_cost_estimator.exceptions import PricingAPIError, PricingDataNotFoundError
from rds_cost_estimator.models import CostRecord, InstanceSpec, PricingType

if TYPE_CHECKING:
    pass

# 모듈 레벨 로거 설정
logger = logging.getLogger(__name__)

# 리전 코드 → AWS 리전 표시명 매핑
REGION_NAMES: dict[str, str] = {
    "ap-northeast-2": "Asia Pacific (Seoul)",
    "ap-northeast-1": "Asia Pacific (Tokyo)",
    "us-east-1": "US East (N. Virginia)",
    "us-west-2": "US West (Oregon)",
    "eu-west-1": "Europe (Ireland)",
    "ap-southeast-1": "Asia Pacific (Singapore)",
    "ap-southeast-2": "Asia Pacific (Sydney)",
    "eu-central-1": "Europe (Frankfurt)",
    "us-east-2": "US East (Ohio)",
    "us-west-1": "US West (N. California)",
}

# 엔진 코드 → AWS 표시명 매핑
ENGINE_NAMES: dict[str, str] = {
    "oracle-ee": "Oracle",
    "oracle-se2": "Oracle",
    "aurora-postgresql": "Aurora PostgreSQL",
    "aurora-mysql": "Aurora MySQL",
    "mysql": "MySQL",
    "postgres": "PostgreSQL",
    "mariadb": "MariaDB",
}


class PricingClient:
    """AWS Pricing API 클라이언트.

    AWS Pricing GetProducts API를 호출하여 RDS 인스턴스의 온디맨드 및
    예약 인스턴스(RI) 가격을 조회합니다. 인메모리 캐시를 통해 동일한
    인스턴스 사양에 대한 중복 API 호출을 방지합니다.

    Args:
        session: AWS 자격증명이 설정된 boto3 Session 객체.
        cache: 캐시 키 → CostRecord 매핑 딕셔너리 (외부에서 주입).
    """

    def __init__(self, session: boto3.Session, cache: dict[str, CostRecord]) -> None:
        """PricingClient 초기화.

        AWS Pricing API는 us-east-1 엔드포인트만 지원하므로 리전을 고정합니다.

        Args:
            session: boto3 Session 객체.
            cache: 인메모리 캐시 딕셔너리.
        """
        # AWS Pricing API는 us-east-1 엔드포인트만 지원
        self._client = session.client("pricing", region_name="us-east-1")
        # 인메모리 캐시 딕셔너리 저장
        self._cache = cache

    def _cache_key(self, spec: InstanceSpec, pricing_type: PricingType) -> str:
        """캐시 키 생성.

        인스턴스 사양과 요금제 유형을 조합하여 고유한 캐시 키를 생성합니다.

        Args:
            spec: 인스턴스 사양 정보.
            pricing_type: 요금제 유형 (온디맨드, 1년 RI, 3년 RI).

        Returns:
            "{instance_type}:{region}:{engine}:{pricing_type.value}" 형식의 캐시 키.
        """
        return f"{spec.instance_type}:{spec.region}:{spec.engine}:{pricing_type.value}"

    def _build_filters(self, spec: InstanceSpec, term_type: str) -> list[dict]:
        """AWS Pricing GetProducts API용 필터 목록 생성.

        온디맨드와 RI에 따라 다른 필터를 구성합니다.
        리전 코드와 엔진 코드를 AWS 표시명으로 변환합니다.

        Args:
            spec: 인스턴스 사양 정보.
            term_type: 요금제 유형 문자열 ("OnDemand", "1yr", "3yr").

        Returns:
            AWS Pricing API GetProducts 요청에 사용할 필터 목록.
        """
        # 리전 코드를 AWS 표시명으로 변환 (매핑에 없으면 원본 코드 사용)
        location = REGION_NAMES.get(spec.region, spec.region)
        # 엔진 코드를 AWS 표시명으로 변환 (매핑에 없으면 원본 코드 사용)
        database_engine = ENGINE_NAMES.get(spec.engine, spec.engine)

        # 공통 필터: 인스턴스 유형, 리전, 엔진, 배포 옵션
        filters: list[dict] = [
            {
                "Type": "TERM_MATCH",
                "Field": "instanceType",
                "Value": spec.instance_type,
            },
            {
                "Type": "TERM_MATCH",
                "Field": "location",
                "Value": location,
            },
            {
                "Type": "TERM_MATCH",
                "Field": "databaseEngine",
                "Value": database_engine,
            },
            {
                "Type": "TERM_MATCH",
                "Field": "deploymentOption",
                "Value": "Single-AZ",
            },
        ]

        if term_type == "OnDemand":
            # 온디맨드 전용 필터
            filters.append({
                "Type": "TERM_MATCH",
                "Field": "termType",
                "Value": "OnDemand",
            })
        else:
            # RI 전용 필터: 예약 유형, 계약 기간, 결제 옵션
            filters.append({
                "Type": "TERM_MATCH",
                "Field": "termType",
                "Value": "Reserved",
            })
            filters.append({
                "Type": "TERM_MATCH",
                "Field": "LeaseContractLength",
                "Value": term_type,  # "1yr" 또는 "3yr"
            })
            filters.append({
                "Type": "TERM_MATCH",
                "Field": "PurchaseOption",
                "Value": "Partial Upfront",
            })

        return filters

    def _parse_response(
        self,
        response: dict,
        spec: InstanceSpec,
        pricing_type: PricingType,
    ) -> CostRecord:
        """AWS Pricing API 응답을 CostRecord로 파싱.

        응답의 PriceList에서 첫 번째 항목을 파싱하여 CostRecord를 생성합니다.
        온디맨드는 hourly_rate를, RI는 upfront_fee와 monthly_fee를 추출합니다.

        Args:
            response: AWS Pricing GetProducts API 응답 딕셔너리.
            spec: 인스턴스 사양 정보.
            pricing_type: 요금제 유형.

        Returns:
            파싱된 CostRecord 인스턴스.

        Raises:
            PricingDataNotFoundError: PriceList가 비어있거나 데이터를 파싱할 수 없는 경우.
        """
        price_list = response.get("PriceList", [])

        # 가격 데이터가 없으면 예외 발생
        if not price_list:
            raise PricingDataNotFoundError(
                f"가격 데이터를 찾을 수 없습니다: {spec.instance_type} / "
                f"{spec.region} / {spec.engine} / {pricing_type.value}"
            )

        # 첫 번째 항목을 JSON으로 파싱
        price_item = json.loads(price_list[0])
        terms = price_item.get("terms", {})

        if pricing_type == PricingType.ON_DEMAND:
            # 온디맨드: terms.OnDemand → priceDimensions → pricePerUnit.USD
            on_demand_terms = terms.get("OnDemand", {})
            if not on_demand_terms:
                raise PricingDataNotFoundError(
                    f"온디맨드 요금 데이터가 없습니다: {spec.instance_type}"
                )

            # 첫 번째 요금 항목에서 priceDimensions 추출
            first_term = next(iter(on_demand_terms.values()))
            price_dimensions = first_term.get("priceDimensions", {})

            if not price_dimensions:
                raise PricingDataNotFoundError(
                    f"온디맨드 priceDimensions가 없습니다: {spec.instance_type}"
                )

            # 첫 번째 priceDimension에서 시간당 요금 추출
            first_dimension = next(iter(price_dimensions.values()))
            hourly_rate_str = (
                first_dimension.get("pricePerUnit", {}).get("USD", "0")
            )
            hourly_rate = float(hourly_rate_str)

            logger.debug(
                "온디맨드 요금 파싱 완료: %s = $%.4f/hr",
                spec.instance_type,
                hourly_rate,
            )

            return CostRecord(
                spec=spec,
                pricing_type=pricing_type,
                hourly_rate=hourly_rate,
            )

        else:
            # RI: terms.Reserved → priceDimensions → Upfront Fee와 Hrs 구분
            reserved_terms = terms.get("Reserved", {})
            if not reserved_terms:
                raise PricingDataNotFoundError(
                    f"RI 요금 데이터가 없습니다: {spec.instance_type}"
                )

            # 첫 번째 요금 항목에서 priceDimensions 추출
            first_term = next(iter(reserved_terms.values()))
            price_dimensions = first_term.get("priceDimensions", {})

            if not price_dimensions:
                raise PricingDataNotFoundError(
                    f"RI priceDimensions가 없습니다: {spec.instance_type}"
                )

            upfront_fee: float = 0.0
            monthly_fee: float = 0.0

            # priceDimensions를 순회하여 선결제(Upfront Fee)와 시간당 요금(Hrs) 구분
            for dimension in price_dimensions.values():
                description = dimension.get("description", "").lower()
                price_usd = float(
                    dimension.get("pricePerUnit", {}).get("USD", "0")
                )
                unit = dimension.get("unit", "").lower()

                if "upfront" in description or unit == "quantity":
                    # 선결제 금액 (Upfront Fee)
                    upfront_fee = price_usd
                elif unit == "hrs":
                    # 시간당 요금 → 월정액으로 변환 (24시간 × 30.4375일)
                    monthly_fee = price_usd * 24 * 30.4375

            logger.debug(
                "RI 요금 파싱 완료: %s / %s = 선결제 $%.2f, 월정액 $%.2f",
                spec.instance_type,
                pricing_type.value,
                upfront_fee,
                monthly_fee,
            )

            return CostRecord(
                spec=spec,
                pricing_type=pricing_type,
                upfront_fee=upfront_fee,
                monthly_fee=monthly_fee,
            )

    async def fetch_on_demand(self, spec: InstanceSpec) -> CostRecord:
        """온디맨드 가격 조회.

        캐시를 먼저 확인하고, 없으면 AWS Pricing API를 비동기로 호출합니다.

        Args:
            spec: 인스턴스 사양 정보.

        Returns:
            온디맨드 요금 정보가 담긴 CostRecord.

        Raises:
            PricingAPIError: AWS Pricing API 호출이 실패한 경우.
            PricingDataNotFoundError: 가격 데이터가 존재하지 않는 경우.
        """
        pricing_type = PricingType.ON_DEMAND
        cache_key = self._cache_key(spec, pricing_type)

        # 캐시 확인: 이미 조회한 데이터가 있으면 반환
        if cache_key in self._cache:
            logger.debug("캐시 히트: %s", cache_key)
            return self._cache[cache_key]

        # AWS Pricing API 필터 생성
        filters = self._build_filters(spec, "OnDemand")

        try:
            # 동기 boto3 호출을 비동기로 래핑 (스레드 풀 실행)
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self._client.get_products(
                    ServiceCode="AmazonRDS",
                    Filters=filters,
                    MaxResults=1,
                ),
            )
        except Exception as exc:
            logger.error(
                "온디맨드 가격 조회 실패: %s / %s - %s",
                spec.instance_type,
                spec.region,
                exc,
            )
            raise PricingAPIError(
                f"온디맨드 가격 조회 실패: {spec.instance_type} / {spec.region}",
                instance_spec=spec,
            ) from exc

        # 응답 파싱 후 캐시 저장
        record = self._parse_response(response, spec, pricing_type)
        self._cache[cache_key] = record
        logger.info(
            "온디맨드 가격 조회 완료: %s / %s = $%.2f/yr",
            spec.instance_type,
            spec.region,
            record.annual_cost or 0,
        )
        return record

    async def fetch_reserved(
        self,
        spec: InstanceSpec,
        term: Literal["1yr", "3yr"],
    ) -> CostRecord:
        """예약 인스턴스(RI) 가격 조회.

        캐시를 먼저 확인하고, 없으면 AWS Pricing API를 비동기로 호출합니다.

        Args:
            spec: 인스턴스 사양 정보.
            term: 계약 기간 ("1yr" 또는 "3yr").

        Returns:
            RI 요금 정보가 담긴 CostRecord.

        Raises:
            PricingAPIError: AWS Pricing API 호출이 실패한 경우.
            PricingDataNotFoundError: 가격 데이터가 존재하지 않는 경우.
        """
        # 계약 기간에 따라 PricingType 결정
        pricing_type = PricingType.RI_1YR if term == "1yr" else PricingType.RI_3YR
        cache_key = self._cache_key(spec, pricing_type)

        # 캐시 확인: 이미 조회한 데이터가 있으면 반환
        if cache_key in self._cache:
            logger.debug("캐시 히트: %s", cache_key)
            return self._cache[cache_key]

        # AWS Pricing API 필터 생성 (term: "1yr" 또는 "3yr")
        filters = self._build_filters(spec, term)

        try:
            # 동기 boto3 호출을 비동기로 래핑 (스레드 풀 실행)
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self._client.get_products(
                    ServiceCode="AmazonRDS",
                    Filters=filters,
                    MaxResults=1,
                ),
            )
        except Exception as exc:
            logger.error(
                "RI 가격 조회 실패: %s / %s / %s - %s",
                spec.instance_type,
                spec.region,
                term,
                exc,
            )
            raise PricingAPIError(
                f"RI 가격 조회 실패: {spec.instance_type} / {spec.region} / {term}",
                instance_spec=spec,
            ) from exc

        # 응답 파싱 후 캐시 저장
        record = self._parse_response(response, spec, pricing_type)
        self._cache[cache_key] = record
        logger.info(
            "RI 가격 조회 완료: %s / %s / %s = $%.2f/yr",
            spec.instance_type,
            spec.region,
            term,
            record.annual_cost or 0,
        )
        return record

    async def fetch_all(self, spec: InstanceSpec) -> list[CostRecord]:
        """온디맨드, 1년 RI, 3년 RI 가격을 병렬로 조회.

        asyncio.gather를 사용하여 세 가지 요금제를 동시에 조회합니다.
        PricingDataNotFoundError가 발생한 항목은 is_available=False인
        CostRecord로 포함되며, 나머지 조회는 계속 진행됩니다.

        Args:
            spec: 인스턴스 사양 정보.

        Returns:
            조회된 CostRecord 목록 (최대 3개).
            가격 데이터가 없는 항목은 is_available=False로 포함됩니다.
        """
        # 세 가지 요금제를 병렬로 조회
        results = await asyncio.gather(
            self.fetch_on_demand(spec),
            self.fetch_reserved(spec, "1yr"),
            self.fetch_reserved(spec, "3yr"),
            return_exceptions=True,
        )

        records: list[CostRecord] = []

        # 요금제 유형과 결과를 매핑하여 처리
        pricing_types = [PricingType.ON_DEMAND, PricingType.RI_1YR, PricingType.RI_3YR]

        for pricing_type, result in zip(pricing_types, results):
            if isinstance(result, CostRecord):
                # 정상 조회 결과
                records.append(result)
            elif isinstance(result, PricingDataNotFoundError):
                # 가격 데이터 없음: is_available=False인 CostRecord로 포함
                logger.warning(
                    "가격 데이터 없음 (N/A 처리): %s / %s - %s",
                    spec.instance_type,
                    pricing_type.value,
                    result,
                )
                records.append(
                    CostRecord(
                        spec=spec,
                        pricing_type=pricing_type,
                        is_available=False,
                    )
                )
            elif isinstance(result, Exception):
                # 기타 예외: is_available=False인 CostRecord로 포함
                logger.error(
                    "가격 조회 오류 (N/A 처리): %s / %s - %s",
                    spec.instance_type,
                    pricing_type.value,
                    result,
                )
                records.append(
                    CostRecord(
                        spec=spec,
                        pricing_type=pricing_type,
                        is_available=False,
                    )
                )

        return records
