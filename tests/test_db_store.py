"""DuckDB 저장소 모듈 테스트."""

from __future__ import annotations

import pytest

from rds_cost_estimator.db_store import DuckDBStore
from rds_cost_estimator.models import (
    AWRMetrics,
    CostRecord,
    InstanceSpec,
    MigrationStrategy,
    ParsedDocumentInfo,
    PricingType,
    SGAAnalysis,
    StorageGrowth,
)


@pytest.fixture
def store() -> DuckDBStore:
    """인메모리 DuckDB 저장소 픽스처."""
    s = DuckDBStore()
    yield s
    s.close()


@pytest.fixture
def sample_parsed_info() -> ParsedDocumentInfo:
    """샘플 ParsedDocumentInfo 픽스처."""
    return ParsedDocumentInfo(
        db_name="TESTDB",
        oracle_version="19c",
        cpu_cores=16,
        physical_memory_gb=128.0,
        db_size_gb=500.0,
        instance_config="2 (RAC)",
        awr_metrics=AWRMetrics(
            avg_cpu_percent=45.0,
            peak_cpu_percent=85.0,
            avg_iops=5000.0,
            peak_iops=15000.0,
            avg_memory_gb=96.0,
            peak_memory_gb=120.0,
            sqlnet_bytes_sent_per_day=5_000_000_000.0,  # ~4.66 GB
            sqlnet_bytes_received_per_day=2_000_000_000.0,  # ~1.86 GB
            redo_bytes_per_day=1_000_000_000.0,  # ~0.93 GB
        ),
        sga_analysis=SGAAnalysis(
            current_sga_gb=64.0,
            recommended_sga_gb=80.0,
            sga_increase_rate_percent=25.0,
        ),
        storage_growth=StorageGrowth(
            current_db_size_gb=500.0,
            yearly_growth_gb=75.0,
            yearly_growth_rate_percent=15.0,
        ),
    )


def _make_cost_record(
    instance_type: str,
    deployment: str,
    pricing_type: PricingType,
    hourly_rate: float | None = None,
    monthly_fee: float | None = None,
    is_available: bool = True,
) -> CostRecord:
    """테스트용 CostRecord 생성 헬퍼."""
    spec = InstanceSpec(
        instance_type=instance_type,
        region="ap-northeast-2",
        engine="oracle-ee",
        strategy=MigrationStrategy.REPLATFORM,
        deployment_option=deployment,
    )
    return CostRecord(
        spec=spec,
        pricing_type=pricing_type,
        hourly_rate=hourly_rate,
        monthly_fee=monthly_fee,
        is_available=is_available,
    )


class TestDuckDBStoreBasic:
    """DuckDB 저장소 기본 기능 테스트."""

    def test_store_and_get_server_specs(
        self, store: DuckDBStore, sample_parsed_info: ParsedDocumentInfo
    ) -> None:
        """서버 사양 저장 및 조회."""
        store.store_parsed_info(sample_parsed_info)
        specs = store.get_server_specs()
        assert specs is not None
        assert specs["db_name"] == "TESTDB"
        assert specs["cpu_cores"] == 16
        assert specs["physical_memory_gb"] == 128.0

    def test_store_and_get_awr_metrics(
        self, store: DuckDBStore, sample_parsed_info: ParsedDocumentInfo
    ) -> None:
        """AWR 메트릭 저장 및 조회."""
        store.store_parsed_info(sample_parsed_info)
        awr = store.get_awr_metrics()
        assert awr is not None
        assert awr["avg_cpu_percent"] == 45.0
        assert awr["sqlnet_bytes_sent_per_day"] == 5_000_000_000.0

    def test_store_and_get_sga_analysis(
        self, store: DuckDBStore, sample_parsed_info: ParsedDocumentInfo
    ) -> None:
        """SGA 분석 저장 및 조회."""
        store.store_parsed_info(sample_parsed_info)
        sga = store.get_sga_analysis()
        assert sga is not None
        assert sga["current_sga_gb"] == 64.0
        assert sga["recommended_sga_gb"] == 80.0

    def test_store_and_get_storage_growth(
        self, store: DuckDBStore, sample_parsed_info: ParsedDocumentInfo
    ) -> None:
        """스토리지 증가 추이 저장 및 조회."""
        store.store_parsed_info(sample_parsed_info)
        sg = store.get_storage_growth()
        assert sg is not None
        assert sg["current_db_size_gb"] == 500.0
        assert sg["yearly_growth_rate_percent"] == 15.0


class TestDuckDBStorePricing:
    """DuckDB 저장소 가격 데이터 테스트."""

    def test_store_and_get_pricing(self, store: DuckDBStore) -> None:
        """가격 레코드 저장 및 조회."""
        records = [
            _make_cost_record(
                "db.r6i.4xlarge", "Single-AZ",
                PricingType.ON_DEMAND, hourly_rate=3.50,
            ),
        ]
        store.store_pricing_records(records)
        result = store.get_pricing("db.r6i.4xlarge", "Single-AZ", "on_demand")
        assert result is not None
        assert result["is_available"] is True

    def test_get_unavailable_ri_records(self, store: DuckDBStore) -> None:
        """is_available=False인 RI 레코드 조회."""
        records = [
            _make_cost_record(
                "db.r6i.4xlarge", "Single-AZ",
                PricingType.ON_DEMAND, hourly_rate=3.50,
            ),
            _make_cost_record(
                "db.r6i.4xlarge", "Single-AZ",
                PricingType.RI_1YR_NO_UPFRONT, is_available=False,
            ),
            _make_cost_record(
                "db.r6i.4xlarge", "Single-AZ",
                PricingType.RI_3YR_ALL_UPFRONT, is_available=False,
            ),
        ]
        store.store_pricing_records(records)
        unavailable = store.get_unavailable_ri_records()
        assert len(unavailable) == 2
        types = {r["pricing_type"] for r in unavailable}
        assert "1yr_no_upfront" in types
        assert "3yr_all_upfront" in types

    def test_update_pricing_record(self, store: DuckDBStore) -> None:
        """가격 레코드 업데이트 (RI 폴백)."""
        records = [
            _make_cost_record(
                "db.r6i.4xlarge", "Single-AZ",
                PricingType.RI_1YR_NO_UPFRONT, is_available=False,
            ),
        ]
        store.store_pricing_records(records)

        store.update_pricing_record(
            "db.r6i.4xlarge", "Single-AZ", "1yr_no_upfront",
            monthly_cost=1500.0, annual_cost=18000.0,
        )

        result = store.get_pricing("db.r6i.4xlarge", "Single-AZ", "1yr_no_upfront")
        assert result is not None
        assert result["is_available"] is True
        assert result["monthly_cost"] == 1500.0


class TestDuckDBStoreNetwork:
    """DuckDB 저장소 네트워크 트래픽 테스트."""

    def test_network_traffic_summary(
        self, store: DuckDBStore, sample_parsed_info: ParsedDocumentInfo
    ) -> None:
        """네트워크 트래픽 요약 조회."""
        store.store_parsed_info(sample_parsed_info)
        net = store.get_network_traffic_summary()

        # 5GB/일 sent → ~4.66 GB
        assert net["sent_daily_gb"] > 4.0
        assert net["recv_daily_gb"] > 1.0
        assert net["redo_daily_gb"] > 0.5
        assert net["total_daily_gb"] > 6.0
        assert net["total_monthly_gb"] > 180.0

    def test_network_traffic_empty(self, store: DuckDBStore) -> None:
        """AWR 데이터 없을 때 기본값 반환."""
        net = store.get_network_traffic_summary()
        assert net["total_daily_gb"] == 0
        assert net["total_monthly_gb"] == 0
