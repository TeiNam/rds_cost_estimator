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
        # 형식: "{instance_type}:{region}:{engine}:{pricing_type.value}"
        expected = "db.r6i.xlarge:ap-northeast-2:oracle-ee:on_demand"
        assert key == expected

    def test_cache_key_ri_1yr(self, pricing_client: PricingClient, sample_spec: InstanceSpec) -> None:
        """1년 RI 캐시 키 형식 확인."""
        key = pricing_client._cache_key(sample_spec, PricingType.RI_1YR)
        expected = "db.r6i.xlarge:ap-northeast-2:oracle-ee:1yr_partial_upfront"
        assert key == expected

    def test_cache_key_ri_3yr(self, pricing_client: PricingClient, sample_spec: InstanceSpec) -> None:
        """3년 RI 캐시 키 형식 확인."""
        key = pricing_client._cache_key(sample_spec, PricingType.RI_3YR)
        expected = "db.r6i.xlarge:ap-northeast-2:oracle-ee:3yr_partial_upfront"
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

    def test_on_demand_filter_contains_term_type(
        self, pricing_client: PricingClient, sample_spec: InstanceSpec
    ) -> None:
        """온디맨드 필터에 termType=OnDemand가 포함되는지 확인."""
        filters = pricing_client._build_filters(sample_spec, "OnDemand")
        # termType 필터 찾기
        term_type_filters = [
            f for f in filters
            if f.get("Field") == "termType"
        ]
        assert len(term_type_filters) == 1
        assert term_type_filters[0]["Value"] == "OnDemand"

    def test_ri_filter_contains_term_type_reserved(
        self, pricing_client: PricingClient, sample_spec: InstanceSpec
    ) -> None:
        """RI 필터에 termType=Reserved가 포함되는지 확인."""
        filters = pricing_client._build_filters(sample_spec, "1yr")
        term_type_filters = [
            f for f in filters
            if f.get("Field") == "termType"
        ]
        assert len(term_type_filters) == 1
        assert term_type_filters[0]["Value"] == "Reserved"

    def test_ri_1yr_filter_contains_lease_contract_length(
        self, pricing_client: PricingClient, sample_spec: InstanceSpec
    ) -> None:
        """1년 RI 필터에 LeaseContractLength가 포함되는지 확인."""
        filters = pricing_client._build_filters(sample_spec, "1yr")
        lease_filters = [
            f for f in filters
            if f.get("Field") == "LeaseContractLength"
        ]
        assert len(lease_filters) == 1
        assert lease_filters[0]["Value"] == "1yr"

    def test_ri_3yr_filter_contains_lease_contract_length(
        self, pricing_client: PricingClient, sample_spec: InstanceSpec
    ) -> None:
        """3년 RI 필터에 LeaseContractLength가 포함되는지 확인."""
        filters = pricing_client._build_filters(sample_spec, "3yr")
        lease_filters = [
            f for f in filters
            if f.get("Field") == "LeaseContractLength"
        ]
        assert len(lease_filters) == 1
        assert lease_filters[0]["Value"] == "3yr"

    def test_ri_filter_contains_purchase_option(
        self, pricing_client: PricingClient, sample_spec: InstanceSpec
    ) -> None:
        """RI 필터에 PurchaseOption이 포함되는지 확인."""
        filters = pricing_client._build_filters(sample_spec, "1yr")
        purchase_filters = [
            f for f in filters
            if f.get("Field") == "PurchaseOption"
        ]
        assert len(purchase_filters) == 1
        assert purchase_filters[0]["Value"] == "Partial Upfront"

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

    def test_on_demand_filter_does_not_contain_lease_contract(
        self, pricing_client: PricingClient, sample_spec: InstanceSpec
    ) -> None:
        """온디맨드 필터에 LeaseContractLength가 포함되지 않는지 확인."""
        filters = pricing_client._build_filters(sample_spec, "OnDemand")
        lease_filters = [
            f for f in filters
            if f.get("Field") == "LeaseContractLength"
        ]
        assert len(lease_filters) == 0

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
