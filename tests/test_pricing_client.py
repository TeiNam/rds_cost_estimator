"""
PricingClient 단위 테스트 모듈.

_cache_key, _build_filters 메서드의 동작을 검증합니다.
AWS API 호출이 필요한 테스트는 moto를 사용하여 모킹합니다.
"""

import pytest
import boto3
from moto import mock_aws

from rds_cost_estimator.models import InstanceSpec, MigrationStrategy, PricingType
from rds_cost_estimator.pricing_client import PricingClient, REGION_NAMES


@pytest.fixture
def aws_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """가짜 AWS 자격증명 설정."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")


@pytest.fixture
def session(aws_credentials: None) -> boto3.Session:
    """테스트용 boto3 세션."""
    return boto3.Session(region_name="us-east-1")


@pytest.fixture
def pricing_client(session: boto3.Session) -> PricingClient:
    """테스트용 PricingClient 인스턴스 (moto 환경)."""
    with mock_aws():
        yield PricingClient(session=session, cache={})


@pytest.fixture
def sample_spec() -> InstanceSpec:
    """테스트용 기본 InstanceSpec."""
    return InstanceSpec(
        instance_type="db.r6i.xlarge",
        region="ap-northeast-2",
        engine="oracle-ee",
        strategy=MigrationStrategy.REPLATFORM,
    )


class TestCacheKey:
    """_cache_key 메서드 테스트."""

    def test_cache_key_format(self, pricing_client: PricingClient, sample_spec: InstanceSpec) -> None:
        """캐시 키가 올바른 형식으로 반환되는지 확인."""
        key = pricing_client._cache_key(sample_spec, PricingType.ON_DEMAND)
        # 형식: "{instance_type}:{region}:{engine}:{deployment}:{pricing_type.value}"
        expected = "db.r6i.xlarge:ap-northeast-2:oracle-ee:Single-AZ:on_demand"
        assert key == expected

    def test_cache_key_ri_1yr_all_upfront(self, pricing_client: PricingClient, sample_spec: InstanceSpec) -> None:
        """1년 RI All Upfront 캐시 키 형식 확인."""
        key = pricing_client._cache_key(sample_spec, PricingType.RI_1YR_ALL_UPFRONT)
        expected = "db.r6i.xlarge:ap-northeast-2:oracle-ee:Single-AZ:1yr_all_upfront"
        assert key == expected

    def test_cache_key_ri_3yr_all_upfront(self, pricing_client: PricingClient, sample_spec: InstanceSpec) -> None:
        """3년 RI All Upfront 캐시 키 형식 확인."""
        key = pricing_client._cache_key(sample_spec, PricingType.RI_3YR_ALL_UPFRONT)
        expected = "db.r6i.xlarge:ap-northeast-2:oracle-ee:Single-AZ:3yr_all_upfront"
        assert key == expected

    def test_cache_key_different_specs_are_unique(
        self, pricing_client: PricingClient
    ) -> None:
        """서로 다른 InstanceSpec의 캐시 키가 고유한지 확인."""
        spec1 = InstanceSpec(
            instance_type="db.r6i.xlarge",
            region="ap-northeast-2",
            engine="oracle-ee",
            strategy=MigrationStrategy.REPLATFORM,
        )
        spec2 = InstanceSpec(
            instance_type="db.r7i.xlarge",
            region="ap-northeast-2",
            engine="oracle-ee",
            strategy=MigrationStrategy.REPLATFORM,
        )
        key1 = pricing_client._cache_key(spec1, PricingType.ON_DEMAND)
        key2 = pricing_client._cache_key(spec2, PricingType.ON_DEMAND)
        assert key1 != key2

    def test_cache_key_different_regions_are_unique(
        self, pricing_client: PricingClient
    ) -> None:
        """리전이 다른 경우 캐시 키가 고유한지 확인."""
        spec1 = InstanceSpec(
            instance_type="db.r6i.xlarge",
            region="ap-northeast-2",
            engine="oracle-ee",
            strategy=MigrationStrategy.REPLATFORM,
        )
        spec2 = InstanceSpec(
            instance_type="db.r6i.xlarge",
            region="us-east-1",
            engine="oracle-ee",
            strategy=MigrationStrategy.REPLATFORM,
        )
        key1 = pricing_client._cache_key(spec1, PricingType.ON_DEMAND)
        key2 = pricing_client._cache_key(spec2, PricingType.ON_DEMAND)
        assert key1 != key2


class TestBuildFilters:
    """_build_filters 메서드 테스트."""

    def test_common_filters_always_present(
        self, pricing_client: PricingClient, sample_spec: InstanceSpec
    ) -> None:
        """공통 필터(instanceType, location, databaseEngine, deploymentOption)가 항상 포함되는지 확인."""
        filters = pricing_client._build_filters(sample_spec, "OnDemand")
        field_names = [f.get("Field") for f in filters]
        assert "instanceType" in field_names
        assert "location" in field_names
        assert "databaseEngine" in field_names
        assert "deploymentOption" in field_names

    def test_no_term_type_in_filters(
        self, pricing_client: PricingClient, sample_spec: InstanceSpec
    ) -> None:
        """필터에 termType이 포함되지 않는지 확인 (term 선택은 파싱 단계에서 수행)."""
        filters = pricing_client._build_filters(sample_spec, "OnDemand")
        term_type_filters = [
            f for f in filters
            if f.get("Field") == "termType"
        ]
        assert len(term_type_filters) == 0

    def test_no_lease_contract_in_filters(
        self, pricing_client: PricingClient, sample_spec: InstanceSpec
    ) -> None:
        """필터에 LeaseContractLength가 포함되지 않는지 확인."""
        filters = pricing_client._build_filters(sample_spec, "1yr")
        lease_filters = [
            f for f in filters
            if f.get("Field") == "LeaseContractLength"
        ]
        assert len(lease_filters) == 0

    def test_no_purchase_option_in_filters(
        self, pricing_client: PricingClient, sample_spec: InstanceSpec
    ) -> None:
        """필터에 PurchaseOption이 포함되지 않는지 확인."""
        filters = pricing_client._build_filters(sample_spec, "1yr")
        purchase_filters = [
            f for f in filters
            if f.get("Field") == "PurchaseOption"
        ]
        assert len(purchase_filters) == 0

    def test_license_model_filter_for_oracle_ee(
        self, pricing_client: PricingClient
    ) -> None:
        """Oracle EE 엔진에 BYOL 라이선스 모델 필터가 포함되는지 확인."""
        spec = InstanceSpec(
            instance_type="db.r6i.xlarge",
            region="ap-northeast-2",
            engine="oracle-ee",
            strategy=MigrationStrategy.REPLATFORM,
        )
        filters = pricing_client._build_filters(spec, "OnDemand")
        license_filters = [
            f for f in filters
            if f.get("Field") == "licenseModel"
        ]
        assert len(license_filters) == 1
        assert license_filters[0]["Value"] == "Bring Your Own License"

    def test_license_model_filter_for_oracle_se2(
        self, pricing_client: PricingClient
    ) -> None:
        """Oracle SE2 엔진에 License Included 라이선스 모델 필터가 포함되는지 확인."""
        spec = InstanceSpec(
            instance_type="db.r6i.xlarge",
            region="ap-northeast-2",
            engine="oracle-se2",
            strategy=MigrationStrategy.REPLATFORM,
        )
        filters = pricing_client._build_filters(spec, "OnDemand")
        license_filters = [
            f for f in filters
            if f.get("Field") == "licenseModel"
        ]
        assert len(license_filters) == 1
        assert license_filters[0]["Value"] == "License Included"

    def test_region_code_converted_to_display_name(
        self, pricing_client: PricingClient
    ) -> None:
        """리전 코드가 AWS 표시명으로 변환되는지 확인 (ap-northeast-2 → Asia Pacific (Seoul))."""
        spec = InstanceSpec(
            instance_type="db.r6i.xlarge",
            region="ap-northeast-2",
            engine="oracle-ee",
            strategy=MigrationStrategy.REPLATFORM,
        )
        filters = pricing_client._build_filters(spec, "OnDemand")
        location_filters = [
            f for f in filters
            if f.get("Field") == "location"
        ]
        assert len(location_filters) == 1
        assert location_filters[0]["Value"] == "Asia Pacific (Seoul)"

    def test_us_east_1_region_converted(
        self, pricing_client: PricingClient
    ) -> None:
        """us-east-1 리전 코드가 올바른 표시명으로 변환되는지 확인."""
        spec = InstanceSpec(
            instance_type="db.r6i.xlarge",
            region="us-east-1",
            engine="oracle-ee",
            strategy=MigrationStrategy.REPLATFORM,
        )
        filters = pricing_client._build_filters(spec, "OnDemand")
        location_filters = [
            f for f in filters
            if f.get("Field") == "location"
        ]
        assert location_filters[0]["Value"] == "US East (N. Virginia)"

    def test_unknown_region_uses_original_code(
        self, pricing_client: PricingClient
    ) -> None:
        """매핑에 없는 리전 코드는 원본 코드를 그대로 사용하는지 확인."""
        spec = InstanceSpec(
            instance_type="db.r6i.xlarge",
            region="unknown-region-99",
            engine="oracle-ee",
            strategy=MigrationStrategy.REPLATFORM,
        )
        filters = pricing_client._build_filters(spec, "OnDemand")
        location_filters = [
            f for f in filters
            if f.get("Field") == "location"
        ]
        assert location_filters[0]["Value"] == "unknown-region-99"

    def test_filters_contain_instance_type(
        self, pricing_client: PricingClient, sample_spec: InstanceSpec
    ) -> None:
        """필터에 instanceType이 포함되는지 확인."""
        filters = pricing_client._build_filters(sample_spec, "OnDemand")
        instance_filters = [
            f for f in filters
            if f.get("Field") == "instanceType"
        ]
        assert len(instance_filters) == 1
        assert instance_filters[0]["Value"] == "db.r6i.xlarge"


class TestRegionNamesMapping:
    """REGION_NAMES 매핑 테스트."""

    def test_seoul_region_mapping(self) -> None:
        """서울 리전 매핑 확인."""
        assert REGION_NAMES["ap-northeast-2"] == "Asia Pacific (Seoul)"

    def test_tokyo_region_mapping(self) -> None:
        """도쿄 리전 매핑 확인."""
        assert REGION_NAMES["ap-northeast-1"] == "Asia Pacific (Tokyo)"

    def test_virginia_region_mapping(self) -> None:
        """버지니아 리전 매핑 확인."""
        assert REGION_NAMES["us-east-1"] == "US East (N. Virginia)"


class TestPartialCacheHit:
    """부분 캐시 히트 테스트 (요구사항 2)."""

    @pytest.fixture
    def spec(self) -> InstanceSpec:
        return InstanceSpec(
            instance_type="db.r6i.2xlarge",
            region="ap-northeast-2",
            engine="oracle-ee",
            strategy=MigrationStrategy.REPLATFORM,
            deployment_option="Single-AZ",
        )

    def _make_cached_record(self, spec, pt):
        """캐시용 CostRecord를 생성합니다."""
        from rds_cost_estimator.models import CostRecord
        return CostRecord(
            spec=spec,
            pricing_type=pt,
            is_available=True,
            monthly_fee=100.0,
            monthly_cost=100.0,
            annual_cost=1200.0,
        )

    @pytest.mark.asyncio
    async def test_full_cache_hit_returns_all_cached(self, session, spec):
        """전체 캐시 히트 시 API 호출 없이 캐시된 레코드를 반환합니다."""
        cache = {}
        client = PricingClient(session, cache=cache)

        all_types = [
            PricingType.ON_DEMAND,
            PricingType.RI_1YR_ALL_UPFRONT,
            PricingType.RI_3YR_ALL_UPFRONT,
        ]
        # 모든 타입을 캐시에 미리 넣기
        for pt in all_types:
            ck = client._cache_key(spec, pt)
            cache[ck] = self._make_cached_record(spec, pt)

        records = await client.fetch_all(spec)
        assert len(records) == 3
        # 모든 레코드가 캐시에서 온 것 확인
        for rec in records:
            assert rec.is_available is True
            assert rec.monthly_cost == 100.0

    @pytest.mark.asyncio
    async def test_partial_cache_preserves_cached_on_api_failure(self, session, spec):
        """부분 캐시 상태에서 API 실패 시 캐시된 레코드는 유지됩니다."""
        from unittest.mock import patch, MagicMock
        from rds_cost_estimator.models import CostRecord

        cache = {}
        client = PricingClient(session, cache=cache)

        # On-Demand만 캐시에 넣기
        cached_types = [PricingType.ON_DEMAND]
        for pt in cached_types:
            ck = client._cache_key(spec, pt)
            cache[ck] = self._make_cached_record(spec, pt)

        # API 호출이 실패하도록 모킹
        with patch.object(client, "_client") as mock_client:
            mock_client.get_products.side_effect = Exception("API 오류")
            records = await client.fetch_all(spec)

        assert len(records) == 3
        # 캐시된 1개는 available
        available = [r for r in records if r.is_available]
        unavailable = [r for r in records if not r.is_available]
        assert len(available) == 1
        assert len(unavailable) == 2

    @pytest.mark.asyncio
    async def test_partial_cache_does_not_duplicate(self, session, spec):
        """부분 캐시 히트 시 캐시된 레코드가 중복되지 않습니다."""
        from unittest.mock import patch, MagicMock
        import json

        cache = {}
        client = PricingClient(session, cache=cache)

        # RI_3YR_ALL_UPFRONT만 캐시에 넣기
        ck = client._cache_key(spec, PricingType.RI_3YR_ALL_UPFRONT)
        cache[ck] = self._make_cached_record(spec, PricingType.RI_3YR_ALL_UPFRONT)

        # API 호출이 실패하도록 모킹
        with patch.object(client, "_client") as mock_client:
            mock_client.get_products.side_effect = Exception("API 오류")
            records = await client.fetch_all(spec)

        # 총 3개 레코드, RI_3YR_ALL_UPFRONT는 1개만
        assert len(records) == 3
        ri3au_records = [r for r in records if r.pricing_type == PricingType.RI_3YR_ALL_UPFRONT]
        assert len(ri3au_records) == 1
        assert ri3au_records[0].is_available is True
