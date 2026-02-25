"""
template_builder 모듈 단위 테스트.

TemplateBuilder의 build 메서드와 _fill_* 메서드를 검증합니다.
"""

import pytest
from unittest.mock import MagicMock

from rds_cost_estimator.models import (
    CLIArgs,
    CostRecord,
    InstanceSpec,
    MigrationStrategy,
    ParsedDocumentInfo,
    PricingType,
)
from rds_cost_estimator.template_builder import TemplateBuilder


def make_args(**kwargs) -> CLIArgs:
    """테스트용 CLIArgs를 생성합니다."""
    defaults = {
        "region": "ap-northeast-2",
        "engine": "oracle-ee",
        "profile": None,
        "input_file": None,
        "output_dir": "/tmp",
        "bedrock_model": "test-model",
        "current_instance": None,
        "recommended_instance_by_size": None,
        "recommended_instance_by_sga": None,
        "on_prem_cost": None,
    }
    defaults.update(kwargs)
    return CLIArgs(**defaults)


class TestTemplateBuilderBuild:
    """TemplateBuilder.build 메서드 테스트."""

    def test_build_returns_dict(self):
        """build가 딕셔너리를 반환합니다."""
        args = make_args()
        builder = TemplateBuilder(db_store=None, args=args)
        parsed = ParsedDocumentInfo()
        data = builder.build(
            parsed=parsed,
            price_index={},
            refac_price_index={},
            spec_instances={},
            sga_instances={},
            family_a="r6i",
            family_b=None,
        )
        assert isinstance(data, dict)
        assert data["family_a"] == "r6i"
        assert data["family_b"] == "N/A"

    def test_build_with_two_families(self):
        """두 패밀리가 모두 data에 포함됩니다."""
        args = make_args()
        builder = TemplateBuilder(db_store=None, args=args)
        parsed = ParsedDocumentInfo()
        data = builder.build(
            parsed=parsed,
            price_index={},
            refac_price_index={},
            spec_instances={"r6i": "db.r6i.2xlarge", "r7i": "db.r7i.2xlarge"},
            sga_instances={"r6i": "db.r6i.2xlarge", "r7i": "db.r7i.2xlarge"},
            family_a="r6i",
            family_b="r7i",
        )
        assert data["family_a"] == "r6i"
        assert data["family_b"] == "r7i"

    def test_build_non_oracle_sets_refac_not_visible(self):
        """비Oracle 엔진이면 refac_section_visible=False."""
        args = make_args(engine="postgresql")
        builder = TemplateBuilder(db_store=None, args=args)
        parsed = ParsedDocumentInfo()
        data = builder.build(
            parsed=parsed,
            price_index={},
            refac_price_index={},
            spec_instances={},
            sga_instances={},
            family_a="r6i",
            family_b=None,
        )
        assert data["refac_section_visible"] is False


class TestFillNetworkDefaults:
    """_fill_network_defaults 메서드 테스트."""

    def test_all_keys_set(self):
        """네트워크 기본값이 모든 키를 설정합니다."""
        from rds_cost_estimator.instance_utils import get_all_network_keys
        args = make_args()
        builder = TemplateBuilder(db_store=None, args=args)
        data: dict = {}
        builder._fill_network_defaults(data)

        all_keys = get_all_network_keys()
        for key in all_keys:
            assert key in data, f"누락된 키: {key}"

    def test_default_values_are_strings(self):
        """기본값이 모두 문자열입니다."""
        args = make_args()
        builder = TemplateBuilder(db_store=None, args=args)
        data: dict = {}
        builder._fill_network_defaults(data)
        for key, value in data.items():
            assert isinstance(value, str), f"{key}의 값이 문자열이 아닙니다: {type(value)}"


class TestFillStorageCosts:
    """_fill_storage_costs 메서드 테스트."""

    def test_storage_costs_set(self):
        """스토리지 비용이 올바르게 설정됩니다."""
        args = make_args()
        builder = TemplateBuilder(db_store=None, args=args)
        data: dict = {}
        builder._fill_storage_costs(data, db_size=100.0, growth_rate=0.15,
                                     prov_iops=0, prov_tp=0.0)
        assert "stor_total_0y" in data
        assert "stor_total_1y" in data
        assert "stor_total_2y" in data
        assert "stor_total_3y" in data

    def test_storage_costs_increase_with_growth(self):
        """스토리지 비용이 연도별로 증가합니다."""
        args = make_args()
        builder = TemplateBuilder(db_store=None, args=args)
        data: dict = {}
        builder._fill_storage_costs(data, db_size=100.0, growth_rate=0.15,
                                     prov_iops=0, prov_tp=0.0)
        cost_0y = float(data["stor_total_0y"].replace(",", ""))
        cost_1y = float(data["stor_total_1y"].replace(",", ""))
        assert cost_1y > cost_0y

    def test_storage_costs_with_region(self):
        """리전별 스토리지 요금이 적용됩니다."""
        args = make_args(region="ap-northeast-1")
        builder = TemplateBuilder(db_store=None, args=args)
        data: dict = {}
        builder._fill_storage_costs(data, db_size=100.0, growth_rate=0.0,
                                     prov_iops=0, prov_tp=0.0,
                                     region="ap-northeast-1")
        # 도쿄: 100 GB × $0.096 = $9.60
        cost = float(data["stor_total_0y"].replace(",", ""))
        assert cost == 9.6
