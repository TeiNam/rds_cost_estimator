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
    "sqlserver-ee": "SQL Server",
    "sqlserver-se": "SQL Server",
    "sqlserver-ex": "SQL Server",
    "sqlserver-web": "SQL Server",
}

# 엔진 코드 → 라이선스 모델 매핑
LICENSE_MODELS: dict[str, str] = {
    "oracle-ee": "Bring Your Own License",
    "oracle-se2": "License Included",
    "aurora-postgresql": "No license required",
    "aurora-mysql": "No license required",
    "mysql": "General Public License",
    "postgres": "PostgreSQL License",
    "mariadb": "General Public License",
    "sqlserver-ee": "License Included",
    "sqlserver-se": "License Included",
    "sqlserver-ex": "License Included",
    "sqlserver-web": "License Included",
}


# 엔진 코드 → AWS Pricing API databaseEdition 매핑 (에디션 구분이 필요한 엔진만)
DATABASE_EDITIONS: dict[str, str] = {
    "sqlserver-ee": "Enterprise",
    "sqlserver-se": "Standard",
    "sqlserver-ex": "Express",
    "sqlserver-web": "Web",
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
        # boto3 세션 보관 (RI 폴백용 RDS 클라이언트 생성에 사용)
        self._session = session
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
        deploy = getattr(spec, 'deployment_option', 'Single-AZ')
        return f"{spec.instance_type}:{spec.region}:{spec.engine}:{deploy}:{pricing_type.value}"

    def _build_filters(self, spec: InstanceSpec, term_type: str) -> list[dict]:
        """AWS Pricing GetProducts API용 필터 목록 생성.

        AWS Pricing API는 LeaseContractLength/PurchaseOption 필터가
        product 레벨에서 동작하지 않으므로, 공통 필터만 구성합니다.
        RI term 선택은 _parse_response에서 termAttributes로 수행합니다.

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
                "Value": getattr(spec, 'deployment_option', 'Single-AZ'),
            },
        ]

        # 라이선스 모델 필터 추가 (Oracle EE vs SE2 구분 등)
        license_model = LICENSE_MODELS.get(spec.engine)
        if license_model:
            filters.append({
                "Type": "TERM_MATCH",
                "Field": "licenseModel",
                "Value": license_model,
            })

        # DB 에디션 필터 추가 (SQL Server 에디션 구분 등)
        db_edition = DATABASE_EDITIONS.get(spec.engine)
        if db_edition:
            filters.append({
                "Type": "TERM_MATCH",
                "Field": "databaseEdition",
                "Value": db_edition,
            })

        return filters

    # AWS Reserved term의 offerTermCode → (LeaseContractLength, PurchaseOption) 매핑
    # 참고: https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/ri-offer-term-codes.html
    _RI_OFFER_CODES: dict[str, tuple[str, str]] = {
        "HU7G6KETJZ": ("1yr", "Partial Upfront"),
        "4NA7Y494T4": ("1yr", "No Upfront"),
        "6QCMYABX3D": ("1yr", "All Upfront"),
        "38NPMPTW36": ("3yr", "Partial Upfront"),
        "NQ3QZPMQV9": ("3yr", "All Upfront"),
        "R5XV2EPZQZ": ("3yr", "No Upfront"),
        "VJWZNREJX2": ("1yr", "All Upfront"),    # Convertible
        "MZU6U2429S": ("3yr", "All Upfront"),    # Convertible
        "Z2E3P23VKM": ("3yr", "No Upfront"),     # Convertible
        "BPH4J8HBKS": ("3yr", "No Upfront"),     # Convertible
        "CUZHX8X6JH": ("1yr", "Partial Upfront"),  # Convertible
        "7NE97W5U4E": ("1yr", "No Upfront"),     # Convertible
    }

    def _find_ri_term(
        self,
        reserved_terms: dict,
        lease_length: str,
        purchase_option: str,
    ) -> dict | None:
        """Reserved terms에서 원하는 계약 기간 + 결제 옵션 조합의 term을 찾습니다.

        offerTermCode 매핑을 우선 사용하고, 없으면 termAttributes로 폴백합니다.

        Args:
            reserved_terms: API 응답의 terms.Reserved 딕셔너리
            lease_length: 계약 기간 ("1yr" 또는 "3yr")
            purchase_option: 결제 옵션 ("Partial Upfront")

        Returns:
            매칭되는 term 딕셔너리, 없으면 None
        """
        for term_key, term_val in reserved_terms.items():
            # term_key 형식: "SKU.offerTermCode"
            offer_code = term_key.split(".")[-1] if "." in term_key else term_key

            # 1) offerTermCode 매핑으로 확인
            if offer_code in self._RI_OFFER_CODES:
                code_lease, code_purchase = self._RI_OFFER_CODES[offer_code]
                if code_lease == lease_length and code_purchase == purchase_option:
                    return term_val
            else:
                # 2) termAttributes로 폴백
                attrs = term_val.get("termAttributes", {})
                attr_lease = attrs.get("LeaseContractLength", "")
                attr_purchase = attrs.get("PurchaseOption", "")
                if attr_lease == lease_length and attr_purchase == purchase_option:
                    return term_val

        return None

    def _parse_response(
        self,
        response: dict,
        spec: InstanceSpec,
        pricing_type: PricingType,
    ) -> CostRecord:
        """AWS Pricing API 응답을 CostRecord로 파싱.

        응답의 PriceList에서 첫 번째 항목을 파싱하여 CostRecord를 생성합니다.
        온디맨드는 hourly_rate를, RI는 termAttributes로 올바른 term을 선택한 뒤
        upfront_fee와 monthly_fee를 추출합니다.

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
            # RI: termAttributes로 올바른 term 선택 (Partial Upfront)
            reserved_terms = terms.get("Reserved", {})
            if not reserved_terms:
                raise PricingDataNotFoundError(
                    f"RI 요금 데이터가 없습니다: {spec.instance_type}"
                )

            # 계약 기간 결정
            lease_length = "1yr" if pricing_type == PricingType.RI_1YR else "3yr"

            # termAttributes로 Partial Upfront term 찾기
            matched_term = self._find_ri_term(
                reserved_terms, lease_length, "Partial Upfront"
            )

            if matched_term is None:
                raise PricingDataNotFoundError(
                    f"RI {lease_length} Partial Upfront term을 찾을 수 없습니다: "
                    f"{spec.instance_type} / {spec.engine}"
                )

            price_dimensions = matched_term.get("priceDimensions", {})

            if not price_dimensions:
                raise PricingDataNotFoundError(
                    f"RI priceDimensions가 없습니다: {spec.instance_type}"
                )

            upfront_fee: float = 0.0
            hourly_fee: float = 0.0

            # priceDimensions를 순회하여 선결제(Upfront Fee)와 시간당 요금(Hrs) 구분
            for dimension in price_dimensions.values():
                price_usd = float(
                    dimension.get("pricePerUnit", {}).get("USD", "0")
                )
                unit = dimension.get("unit", "").lower()

                if unit == "quantity":
                    # 선결제 금액 (Upfront Fee)
                    upfront_fee = price_usd
                elif unit == "hrs":
                    # 시간당 요금
                    hourly_fee = price_usd

            # 시간당 요금 → 월정액 변환 (24시간 × 30.4375일)
            monthly_fee = hourly_fee * 24 * 30.4375

            logger.debug(
                "RI 요금 파싱 완료: %s / %s = 선결제 $%.2f, 시간당 $%.4f, 월정액 $%.2f",
                spec.instance_type,
                pricing_type.value,
                upfront_fee,
                hourly_fee,
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

    async def fetch_reserved_option(
        self,
        spec: InstanceSpec,
        term: Literal["1yr", "3yr"],
        purchase_option: str = "Partial Upfront",
    ) -> CostRecord:
        """예약 인스턴스(RI) 가격 조회 - 결제 옵션 지정 가능.

        Args:
            spec: 인스턴스 사양 정보.
            term: 계약 기간 ("1yr" 또는 "3yr").
            purchase_option: 결제 옵션 ("No Upfront", "Partial Upfront", "All Upfront")

        Returns:
            RI 요금 정보가 담긴 CostRecord.
        """
        # PricingType 결정
        type_map = {
            ("1yr", "No Upfront"): PricingType.RI_1YR_NO_UPFRONT,
            ("1yr", "Partial Upfront"): PricingType.RI_1YR,
            ("1yr", "All Upfront"): PricingType.RI_1YR_ALL_UPFRONT,
            ("3yr", "No Upfront"): PricingType.RI_3YR_NO_UPFRONT,
            ("3yr", "Partial Upfront"): PricingType.RI_3YR,
            ("3yr", "All Upfront"): PricingType.RI_3YR_ALL_UPFRONT,
        }
        pricing_type = type_map.get((term, purchase_option), PricingType.RI_1YR)
        cache_key = self._cache_key(spec, pricing_type)

        if cache_key in self._cache:
            logger.debug("캐시 히트: %s", cache_key)
            return self._cache[cache_key]

        filters = self._build_filters(spec, term)

        try:
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
                "RI 가격 조회 실패: %s / %s / %s / %s - %s",
                spec.instance_type, spec.region, term, purchase_option, exc,
            )
            raise PricingAPIError(
                f"RI 가격 조회 실패: {spec.instance_type} / {spec.region} / {term}",
                instance_spec=spec,
            ) from exc

        record = self._parse_ri_response(response, spec, pricing_type, term, purchase_option)
        self._cache[cache_key] = record
        return record

    def _parse_ri_response(
        self,
        response: dict,
        spec: InstanceSpec,
        pricing_type: PricingType,
        lease_length: str,
        purchase_option: str,
    ) -> CostRecord:
        """RI 응답 파싱 - 특정 결제 옵션."""
        price_list = response.get("PriceList", [])
        if not price_list:
            raise PricingDataNotFoundError(
                f"가격 데이터를 찾을 수 없습니다: {spec.instance_type} / "
                f"{spec.region} / {spec.engine} / {pricing_type.value}"
            )

        price_item = json.loads(price_list[0])
        terms = price_item.get("terms", {})
        reserved_terms = terms.get("Reserved", {})

        if not reserved_terms:
            raise PricingDataNotFoundError(
                f"RI 요금 데이터가 없습니다: {spec.instance_type}"
            )

        matched_term = self._find_ri_term(reserved_terms, lease_length, purchase_option)
        if matched_term is None:
            raise PricingDataNotFoundError(
                f"RI {lease_length} {purchase_option} term을 찾을 수 없습니다: "
                f"{spec.instance_type} / {spec.engine}"
            )

        price_dimensions = matched_term.get("priceDimensions", {})
        if not price_dimensions:
            raise PricingDataNotFoundError(
                f"RI priceDimensions가 없습니다: {spec.instance_type}"
            )

        upfront_fee: float = 0.0
        hourly_fee: float = 0.0

        for dimension in price_dimensions.values():
            price_usd = float(dimension.get("pricePerUnit", {}).get("USD", "0"))
            unit = dimension.get("unit", "").lower()
            if unit == "quantity":
                upfront_fee = price_usd
            elif unit == "hrs":
                hourly_fee = price_usd

        monthly_fee = hourly_fee * 730

        logger.debug(
            "RI 요금 파싱 완료: %s / %s / %s = 선결제 $%.2f, 월정액 $%.2f",
            spec.instance_type, pricing_type.value, purchase_option,
            upfront_fee, monthly_fee,
        )

        return CostRecord(
            spec=spec,
            pricing_type=pricing_type,
            upfront_fee=upfront_fee,
            monthly_fee=monthly_fee,
        )

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
        """온디맨드 + 모든 RI 옵션 가격을 한 번의 API 호출로 조회.

        템플릿 v2에 필요한 모든 요금 옵션:
        - On-Demand
        - 1년 RI (No Upfront, All Upfront)
        - 3년 RI (No Upfront, All Upfront)
        """
        records: list[CostRecord] = []
        pricing_types = [
            PricingType.ON_DEMAND,
            PricingType.RI_1YR_ALL_UPFRONT,
            PricingType.RI_3YR_ALL_UPFRONT,
        ]

        # RI 타입 → (lease_length, purchase_option) 매핑
        ri_params = {
            PricingType.RI_1YR_ALL_UPFRONT: ("1yr", "All Upfront"),
            PricingType.RI_3YR_ALL_UPFRONT: ("3yr", "All Upfront"),
        }

        # 캐시에 모두 있으면 바로 반환
        all_cached = True
        for pt in pricing_types:
            ck = self._cache_key(spec, pt)
            if ck in self._cache:
                records.append(self._cache[ck])
            else:
                all_cached = False
                break

        if all_cached:
            logger.debug("캐시 히트 (전체): %s", spec.instance_type)
            return records

        # API 호출
        filters = self._build_filters(spec, "all")
        records = []

        try:
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
                "가격 조회 실패: %s / %s - %s",
                spec.instance_type, spec.region, exc,
            )
            for pt in pricing_types:
                records.append(
                    CostRecord(spec=spec, pricing_type=pt, is_available=False)
                )
            return records

        # 각 요금제별로 파싱 시도
        for pt in pricing_types:
            cache_key = self._cache_key(spec, pt)
            if cache_key in self._cache:
                records.append(self._cache[cache_key])
                continue

            try:
                if pt == PricingType.ON_DEMAND:
                    record = self._parse_response(response, spec, pt)
                else:
                    lease_length, purchase_option = ri_params[pt]
                    record = self._parse_ri_response(
                        response, spec, pt, lease_length, purchase_option
                    )
                self._cache[cache_key] = record
                records.append(record)
                logger.info(
                    "가격 파싱 완료: %s / %s = $%.2f/yr",
                    spec.instance_type, pt.value, record.annual_cost or 0,
                )
            except PricingDataNotFoundError as e:
                logger.warning(
                    "가격 데이터 없음 (N/A 처리): %s / %s - %s",
                    spec.instance_type, pt.value, e,
                )
                records.append(
                    CostRecord(spec=spec, pricing_type=pt, is_available=False)
                )
            except Exception as e:
                logger.error(
                    "가격 파싱 오류 (N/A 처리): %s / %s - %s",
                    spec.instance_type, pt.value, e,
                )
                records.append(
                    CostRecord(spec=spec, pricing_type=pt, is_available=False)
                )

        return records

    # ─── RI 폴백: DescribeReservedDBInstancesOfferings API ───

    # PricingType → (Duration 초, OfferingType) 매핑
    _RI_OFFERING_PARAMS: dict[str, tuple[str, str]] = {
        "1yr_no_upfront": ("31536000", "No Upfront"),
        "1yr_all_upfront": ("31536000", "All Upfront"),
        "1yr_partial_upfront": ("31536000", "Partial Upfront"),
        "3yr_no_upfront": ("94608000", "No Upfront"),
        "3yr_all_upfront": ("94608000", "All Upfront"),
        "3yr_partial_upfront": ("94608000", "Partial Upfront"),
    }

    # 엔진 코드 → ProductDescription 매핑
    _PRODUCT_DESCRIPTIONS: dict[str, str] = {
        "oracle-ee": "oracle",
        "oracle-se2": "oracle",
        "aurora-postgresql": "aurora-postgresql",
        "aurora-mysql": "aurora-mysql",
        "mysql": "mysql",
        "postgres": "postgresql",
        "mariadb": "mariadb",
    }

    async def fetch_ri_offering(
        self,
        spec: InstanceSpec,
        pricing_type_value: str,
    ) -> CostRecord | None:
        """DescribeReservedDBInstancesOfferings API로 RI 가격을 조회합니다.

        Pricing GetProducts API에서 RI 데이터를 찾지 못했을 때 폴백으로 사용합니다.
        RDS API는 해당 리전 엔드포인트에서 호출해야 합니다.

        Args:
            spec: 인스턴스 사양 정보.
            pricing_type_value: PricingType의 value 문자열 (예: "1yr_no_upfront").

        Returns:
            CostRecord 또는 None (조회 실패 시).
        """
        params = self._RI_OFFERING_PARAMS.get(pricing_type_value)
        if not params:
            logger.warning("알 수 없는 RI 타입: %s", pricing_type_value)
            return None

        duration_str, offering_type = params
        product_desc = self._PRODUCT_DESCRIPTIONS.get(spec.engine, spec.engine)
        is_multi_az = spec.deployment_option == "Multi-AZ"

        try:
            # RDS API는 해당 리전에서 호출
            rds_client = self._session.client("rds", region_name=spec.region)
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: rds_client.describe_reserved_db_instances_offerings(
                    DBInstanceClass=spec.instance_type,
                    Duration=duration_str,
                    ProductDescription=product_desc,
                    OfferingType=offering_type,
                    MultiAZ=is_multi_az,
                ),
            )
        except Exception as exc:
            logger.warning(
                "RI Offering 조회 실패: %s / %s / %s - %s",
                spec.instance_type, pricing_type_value, spec.region, exc,
            )
            return None

        offerings = response.get("ReservedDBInstancesOfferings", [])
        if not offerings:
            logger.warning(
                "RI Offering 데이터 없음: %s / %s / %s",
                spec.instance_type, pricing_type_value, spec.region,
            )
            return None

        # 첫 번째 매칭 오퍼링 사용
        offering = offerings[0]
        fixed_price = offering.get("FixedPrice", 0.0)  # 선결제 금액
        usage_price = offering.get("UsagePrice", 0.0)  # 시간당 요금 (구버전)
        duration_sec = offering.get("Duration", int(duration_str))

        # RecurringCharges에서 시간당 요금 추출 (최신 API 형식)
        recurring_hourly = 0.0
        for charge in offering.get("RecurringCharges", []):
            if charge.get("RecurringChargeFrequency") == "Hourly":
                recurring_hourly = charge.get("RecurringChargeAmount", 0.0)

        # 시간당 요금: RecurringCharges 우선, 없으면 UsagePrice
        hourly_rate = recurring_hourly if recurring_hourly > 0 else usage_price
        monthly_fee = hourly_rate * 730  # 730시간/월

        # PricingType 결정
        pt_map = {
            "1yr_no_upfront": PricingType.RI_1YR_NO_UPFRONT,
            "1yr_all_upfront": PricingType.RI_1YR_ALL_UPFRONT,
            "1yr_partial_upfront": PricingType.RI_1YR,
            "3yr_no_upfront": PricingType.RI_3YR_NO_UPFRONT,
            "3yr_all_upfront": PricingType.RI_3YR_ALL_UPFRONT,
            "3yr_partial_upfront": PricingType.RI_3YR,
        }
        pricing_type = pt_map.get(pricing_type_value, PricingType.RI_1YR)

        record = CostRecord(
            spec=spec,
            pricing_type=pricing_type,
            upfront_fee=fixed_price,
            monthly_fee=monthly_fee,
        )

        logger.info(
            "RI Offering 폴백 성공: %s / %s / %s = 선결제 $%.2f, 월정액 $%.2f, 연 $%.2f",
            spec.instance_type, pricing_type_value, spec.region,
            fixed_price, monthly_fee, record.annual_cost or 0,
        )

        return record
