"""
Estimator 클래스 단위 테스트 모듈.

테스트 대상:
- --input-file 지정 시 ParsedDocumentInfo 필드로 CLIArgs 보완 (CLI 인수 우선, run_v2 경로)
- --profile 옵션에 따른 boto3.Session 생성 확인
- 네트워크 기본값 키 완전성
- TCO 연도 오프셋
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from rds_cost_estimator.models import (
    CLIArgs,
    CostRecord,
    InstanceSpec,
    MigrationStrategy,
    ParsedDocumentInfo,
    PricingType,
)


# ─────────────────────────────────────────────
# 공통 픽스처
# ─────────────────────────────────────────────

def make_args(**kwargs) -> CLIArgs:
    """테스트용 CLIArgs 생성 헬퍼 함수."""
    defaults = {
        "region": "ap-northeast-2",
        "current_instance": "db.r6i.xlarge",
        "recommended_instance_by_size": "db.r7i.xlarge",
        "on_prem_cost": 100_000.0,
        "engine": "oracle-ee",
    }
    defaults.update(kwargs)
    return CLIArgs(**defaults)


# ─────────────────────────────────────────────
# --input-file 지정 시 CLIArgs 보완 테스트 (run_v2 경로)
# ─────────────────────────────────────────────

class TestInputFileIntegration:
    """--input-file 지정 시 ParsedDocumentInfo로 CLIArgs 보완 테스트 (run_v2 경로)."""

    @pytest.mark.asyncio
    async def test_input_file_fills_missing_current_instance(self):
        """--input-file 지정 시 current_instance가 없으면 문서 파싱 결과로 보완해야 한다."""
        args = make_args(
            current_instance=None,
            recommended_instance_by_size="db.r7i.xlarge",
            on_prem_cost=100_000.0,
            input_file="/path/to/doc.txt",
        )

        parsed_info = ParsedDocumentInfo(
            current_instance="db.r6i.xlarge",
        )

        with patch("rds_cost_estimator.estimator.boto3.Session"):
            from rds_cost_estimator.estimator import Estimator
            estimator = Estimator(args)

        mock_parser = MagicMock()
        mock_parser.parse.return_value = parsed_info

        with patch("rds_cost_estimator.estimator.DocumentParser", return_value=mock_parser):
            with patch("rds_cost_estimator.estimator.BedrockClient"):
                estimator._pricing_client.fetch_all = AsyncMock(return_value=[])
                await estimator.run_v2()

        assert estimator._args.current_instance == "db.r6i.xlarge"

    @pytest.mark.asyncio
    async def test_input_file_cli_args_take_priority(self):
        """--input-file 지정 시 CLI 인수가 문서 파싱 결과보다 우선해야 한다."""
        args = make_args(
            current_instance="db.r6i.2xlarge",
            recommended_instance_by_size="db.r7i.xlarge",
            on_prem_cost=100_000.0,
            input_file="/path/to/doc.txt",
        )

        parsed_info = ParsedDocumentInfo(
            current_instance="db.r6i.xlarge",
        )

        with patch("rds_cost_estimator.estimator.boto3.Session"):
            from rds_cost_estimator.estimator import Estimator
            estimator = Estimator(args)

        mock_parser = MagicMock()
        mock_parser.parse.return_value = parsed_info

        with patch("rds_cost_estimator.estimator.DocumentParser", return_value=mock_parser):
            with patch("rds_cost_estimator.estimator.BedrockClient"):
                estimator._pricing_client.fetch_all = AsyncMock(return_value=[])
                await estimator.run_v2()

        assert estimator._args.current_instance == "db.r6i.2xlarge"

    @pytest.mark.asyncio
    async def test_input_file_fills_on_prem_cost(self):
        """--input-file 지정 시 on_prem_cost가 없으면 문서 파싱 결과로 보완해야 한다."""
        args = make_args(
            on_prem_cost=None,
            input_file="/path/to/doc.txt",
        )

        parsed_info = ParsedDocumentInfo(
            current_instance="db.r6i.xlarge",
            on_prem_cost=200_000.0,
        )

        with patch("rds_cost_estimator.estimator.boto3.Session"):
            from rds_cost_estimator.estimator import Estimator
            estimator = Estimator(args)

        mock_parser = MagicMock()
        mock_parser.parse.return_value = parsed_info

        with patch("rds_cost_estimator.estimator.DocumentParser", return_value=mock_parser):
            with patch("rds_cost_estimator.estimator.BedrockClient"):
                estimator._pricing_client.fetch_all = AsyncMock(return_value=[])
                await estimator.run_v2()

        assert estimator._args.on_prem_cost == 200_000.0

    @pytest.mark.asyncio
    async def test_input_file_fills_recommended_by_size_and_sga(self):
        """--input-file 지정 시 두 가지 권장 인스턴스가 문서 파싱 결과로 보완되어야 한다."""
        args = make_args(
            recommended_instance_by_size=None,
            recommended_instance_by_sga=None,
            input_file="/path/to/doc.txt",
        )

        parsed_info = ParsedDocumentInfo(
            recommended_instance_by_size="db.r6i.2xlarge",
            recommended_instance_by_sga="db.r6i.large",
        )

        with patch("rds_cost_estimator.estimator.boto3.Session"):
            from rds_cost_estimator.estimator import Estimator
            estimator = Estimator(args)

        mock_parser = MagicMock()
        mock_parser.parse.return_value = parsed_info

        with patch("rds_cost_estimator.estimator.DocumentParser", return_value=mock_parser):
            with patch("rds_cost_estimator.estimator.BedrockClient"):
                estimator._pricing_client.fetch_all = AsyncMock(return_value=[])
                await estimator.run_v2()

        assert estimator._args.recommended_instance_by_size == "db.r6i.2xlarge"
        assert estimator._args.recommended_instance_by_sga == "db.r6i.large"

    @pytest.mark.asyncio
    async def test_no_input_file_uses_cli_args_directly(self):
        """--input-file이 없으면 DocumentParser를 호출하지 않아야 한다."""
        args = make_args(input_file=None)

        with patch("rds_cost_estimator.estimator.boto3.Session"):
            from rds_cost_estimator.estimator import Estimator
            estimator = Estimator(args)

        estimator._pricing_client.fetch_all = AsyncMock(return_value=[])

        with patch("rds_cost_estimator.estimator.DocumentParser") as mock_parser_cls:
            await estimator.run_v2()
            mock_parser_cls.assert_not_called()


# ─────────────────────────────────────────────
# --profile 옵션에 따른 boto3.Session 생성 테스트
# ─────────────────────────────────────────────

class TestBoto3SessionCreation:
    """--profile 옵션에 따른 boto3.Session 생성 테스트."""

    def test_profile_creates_session_with_profile_name(self):
        """--profile 옵션이 있으면 profile_name을 지정하여 Session을 생성해야 한다."""
        args = make_args(profile="my-aws-profile")

        with patch("rds_cost_estimator.estimator.boto3.Session") as mock_session_cls:
            from rds_cost_estimator.estimator import Estimator
            Estimator(args)

        # profile_name 인수로 Session이 생성되어야 함
        mock_session_cls.assert_called_once_with(profile_name="my-aws-profile")

    def test_no_profile_creates_default_session(self):
        """--profile 옵션이 없으면 기본 Session을 생성해야 한다."""
        args = make_args(profile=None)

        with patch("rds_cost_estimator.estimator.boto3.Session") as mock_session_cls:
            from rds_cost_estimator.estimator import Estimator
            Estimator(args)

        # 인수 없이 기본 Session이 생성되어야 함
        mock_session_cls.assert_called_once_with()


# ─────────────────────────────────────────────
# 네트워크 기본값 키 완전성 테스트 (요구사항 14)
# ─────────────────────────────────────────────


class TestNetworkDefaultsKeyCompleteness:
    """_fill_network_defaults가 _fill_network_costs와 동일한 키를 설정하는지 검증합니다."""

    def _make_estimator_no_db(self):
        """DuckDB 없이 Estimator 인스턴스를 생성합니다."""
        args = make_args()
        with patch("rds_cost_estimator.estimator.boto3.Session"):
            from rds_cost_estimator.estimator import Estimator
            est = Estimator(args)
        est._db_store = None
        return est

    def _make_estimator_with_mock_db(self):
        """모의 DuckDB가 있는 Estimator 인스턴스를 생성합니다."""
        args = make_args()
        with patch("rds_cost_estimator.estimator.boto3.Session"):
            from rds_cost_estimator.estimator import Estimator
            est = Estimator(args)
        mock_db = MagicMock()
        mock_db.get_network_traffic_summary.return_value = {
            "sent_daily_gb": 1.5,
            "recv_daily_gb": 2.0,
            "redo_daily_gb": 0.5,
            "sent_monthly_gb": 45.0,
            "recv_monthly_gb": 60.0,
            "redo_monthly_gb": 15.0,
            "total_daily_gb": 4.0,
            "total_monthly_gb": 120.0,
        }
        est._db_store = mock_db
        return est

    def test_defaults_keys_match_costs_keys(self):
        """_fill_network_defaults가 설정하는 키 집합이 _fill_network_costs와 동일해야 합니다."""
        # 네트워크 데이터가 있는 경우의 키 수집
        est_with_db = self._make_estimator_with_mock_db()
        data_costs: dict = {}
        est_with_db._fill_network_costs(data_costs, growth_rate=0.15)
        costs_keys = set(data_costs.keys())

        # 네트워크 데이터가 없는 경우의 키 수집
        est_no_db = self._make_estimator_no_db()
        data_defaults: dict = {}
        est_no_db._fill_network_costs(data_defaults, growth_rate=0.15)
        defaults_keys = set(data_defaults.keys())

        # 두 키 집합이 동일해야 함
        missing_in_defaults = costs_keys - defaults_keys
        extra_in_defaults = defaults_keys - costs_keys

        assert missing_in_defaults == set(), (
            f"_fill_network_defaults에 누락된 키: {missing_in_defaults}"
        )
        assert extra_in_defaults == set(), (
            f"_fill_network_defaults에 불필요한 키: {extra_in_defaults}"
        )

    def test_get_all_network_keys_matches_costs_keys(self):
        """get_all_network_keys()가 반환하는 키 목록이 _fill_network_costs의 키와 일치해야 합니다."""
        from rds_cost_estimator.estimator import get_all_network_keys

        est_with_db = self._make_estimator_with_mock_db()
        data_costs: dict = {}
        est_with_db._fill_network_costs(data_costs, growth_rate=0.15)
        costs_keys = set(data_costs.keys())

        helper_keys = set(get_all_network_keys())

        assert helper_keys == costs_keys, (
            f"get_all_network_keys() 불일치.\n"
            f"  누락: {costs_keys - helper_keys}\n"
            f"  초과: {helper_keys - costs_keys}"
        )

    def test_defaults_all_values_are_strings(self):
        """기본값이 모두 문자열이어야 합니다 (템플릿 치환 호환)."""
        est = self._make_estimator_no_db()
        data: dict = {}
        est._fill_network_costs(data, growth_rate=0.15)

        for key, value in data.items():
            assert isinstance(value, str), (
                f"키 '{key}'의 값이 문자열이 아닙니다: {type(value).__name__} = {value!r}"
            )

    def test_no_unreplaced_placeholders_without_network_data(self):
        """네트워크 데이터 없이 _build_template_data 호출 시 네트워크 관련 미치환 플레이스홀더가 없어야 합니다."""
        from rds_cost_estimator.estimator import get_all_network_keys

        est = self._make_estimator_no_db()

        # 최소한의 ParsedDocumentInfo 생성
        parsed = ParsedDocumentInfo(
            db_name="TestDB",
            oracle_version="19c",
            cpu_cores=8,
            physical_memory_gb=64.0,
            db_size_gb=500.0,
        )

        # 가격 인덱스를 빈 딕셔너리로 설정 (가격 데이터 없음)
        price_index: dict = {}
        spec_instances = {"r6i": "db.r6i.xlarge"}
        sga_instances = {"r6i": "db.r6i.2xlarge"}

        data = est._build_template_data(
            parsed=parsed,
            price_index=price_index,
            refac_price_index={},
            spec_instances=spec_instances,
            sga_instances=sga_instances,
            family_a="r6i",
            family_b=None,
        )

        # 모든 네트워크 키가 data에 존재하는지 확인
        all_net_keys = get_all_network_keys()
        missing_keys = [k for k in all_net_keys if k not in data]
        assert missing_keys == [], (
            f"_build_template_data 결과에 누락된 네트워크 키: {missing_keys}"
        )

        # 네트워크 키의 값이 플레이스홀더 패턴({...})이 아닌지 확인
        import re
        placeholder_pattern = re.compile(r"\{[a-z_]+\}")
        for key in all_net_keys:
            value = data[key]
            assert not placeholder_pattern.fullmatch(str(value)), (
                f"키 '{key}'에 미치환 플레이스홀더가 남아있습니다: {value!r}"
            )


# ─────────────────────────────────────────────
# TCO 연도 오프셋 검증 테스트 (요구사항 6)
# ─────────────────────────────────────────────


class TestTcoYearOffset:
    """_fill_tco에서 연도별 스토리지/네트워크 비용이 증가율을 올바르게 반영하는지 검증합니다."""

    def _make_estimator(self):
        """DB 없이 Estimator 인스턴스를 생성합니다."""
        from rds_cost_estimator.estimator import Estimator

        args = make_args()
        est = Estimator(args)
        est._db_store = None
        return est

    def test_tco_storage_reflects_growth_rate(self):
        """TCO 1년차 스토리지 비용이 증가율 1회 적용된 값이어야 합니다."""
        from rds_cost_estimator.estimator import calc_storage_costs

        est = self._make_estimator()
        db_size = 500.0
        growth_rate = 0.20  # 20% 증가율
        prov_iops = 0
        prov_tp = 0.0

        # 인스턴스 비용 데이터 설정 (TCO 계산에 필요)
        data: dict = {
            "net_monthly": "0.00",
            "sga_r6i_ri3au_monthly": "100.00",
        }

        est._fill_tco(data, ["r6i"], db_size, growth_rate, prov_iops, prov_tp)

        # 1년차: db_size * (1 + 0.20)^1 = 600 GB
        year1_size = db_size * (1 + growth_rate) ** 1
        year1_costs = calc_storage_costs(year1_size, prov_iops, prov_tp)
        expected_stor_1y = year1_costs["total"] * 12

        # 2년차: db_size * (1 + 0.20)^2 = 720 GB
        year2_size = db_size * (1 + growth_rate) ** 2
        year2_costs = calc_storage_costs(year2_size, prov_iops, prov_tp)
        expected_stor_2y = year2_costs["total"] * 12

        # 3년차: db_size * (1 + 0.20)^3 = 864 GB
        year3_size = db_size * (1 + growth_rate) ** 3
        year3_costs = calc_storage_costs(year3_size, prov_iops, prov_tp)
        expected_stor_3y = year3_costs["total"] * 12

        # TCO 상세에서 연도별 스토리지 비용 검증
        actual_stor_1y = float(data["tco_detail_stor_1y"].replace(",", ""))
        actual_stor_2y = float(data["tco_detail_stor_2y"].replace(",", ""))
        actual_stor_3y = float(data["tco_detail_stor_3y"].replace(",", ""))

        assert actual_stor_1y == pytest.approx(expected_stor_1y, rel=1e-2), (
            f"1년차 스토리지: 기대값 {expected_stor_1y:.2f}, 실제값 {actual_stor_1y:.2f}"
        )
        assert actual_stor_2y == pytest.approx(expected_stor_2y, rel=1e-2), (
            f"2년차 스토리지: 기대값 {expected_stor_2y:.2f}, 실제값 {actual_stor_2y:.2f}"
        )
        assert actual_stor_3y == pytest.approx(expected_stor_3y, rel=1e-2), (
            f"3년차 스토리지: 기대값 {expected_stor_3y:.2f}, 실제값 {actual_stor_3y:.2f}"
        )

    def test_tco_yearly_storage_increases(self):
        """TCO 연도별 스토리지 비용이 매년 증가해야 합니다."""
        est = self._make_estimator()
        db_size = 1000.0
        growth_rate = 0.15  # 15% 증가율

        data: dict = {
            "net_monthly": "0.00",
            "sga_r6i_ri3au_monthly": "200.00",
        }

        est._fill_tco(data, ["r6i"], db_size, growth_rate, 0, 0.0)

        stor_1y = float(data["tco_detail_stor_1y"].replace(",", ""))
        stor_2y = float(data["tco_detail_stor_2y"].replace(",", ""))
        stor_3y = float(data["tco_detail_stor_3y"].replace(",", ""))

        assert stor_2y > stor_1y, (
            f"2년차({stor_2y:.2f})가 1년차({stor_1y:.2f})보다 커야 합니다"
        )
        assert stor_3y > stor_2y, (
            f"3년차({stor_3y:.2f})가 2년차({stor_2y:.2f})보다 커야 합니다"
        )

    def test_tco_network_reflects_growth_rate(self):
        """TCO 연도별 네트워크 비용이 증가율을 반영해야 합니다."""
        est = self._make_estimator()
        growth_rate = 0.10  # 10% 증가율
        net_monthly_base = 50.0

        data: dict = {
            "net_monthly": f"{net_monthly_base:.2f}",
            "sga_r6i_ri3au_monthly": "100.00",
        }

        est._fill_tco(data, ["r6i"], 100.0, growth_rate, 0, 0.0)

        # 1년차 네트워크: base * (1+0.10)^1 * 12
        expected_net_1y = net_monthly_base * (1 + growth_rate) ** 1 * 12
        expected_net_2y = net_monthly_base * (1 + growth_rate) ** 2 * 12
        expected_net_3y = net_monthly_base * (1 + growth_rate) ** 3 * 12

        actual_net_1y = float(data["tco_detail_net_1y"].replace(",", ""))
        actual_net_2y = float(data["tco_detail_net_2y"].replace(",", ""))
        actual_net_3y = float(data["tco_detail_net_3y"].replace(",", ""))

        assert actual_net_1y == pytest.approx(expected_net_1y, rel=1e-2), (
            f"1년차 네트워크: 기대값 {expected_net_1y:.2f}, 실제값 {actual_net_1y:.2f}"
        )
        assert actual_net_2y == pytest.approx(expected_net_2y, rel=1e-2), (
            f"2년차 네트워크: 기대값 {expected_net_2y:.2f}, 실제값 {actual_net_2y:.2f}"
        )
        assert actual_net_3y == pytest.approx(expected_net_3y, rel=1e-2), (
            f"3년차 네트워크: 기대값 {expected_net_3y:.2f}, 실제값 {actual_net_3y:.2f}"
        )

    def test_tco_1y_storage_not_equal_to_current(self):
        """TCO 1년차 스토리지 비용은 현재(0y) 기준과 달라야 합니다 (증가율 > 0일 때)."""
        from rds_cost_estimator.estimator import calc_storage_costs

        est = self._make_estimator()
        db_size = 500.0
        growth_rate = 0.20

        data: dict = {
            "net_monthly": "0.00",
            "sga_r6i_ri3au_monthly": "100.00",
        }

        est._fill_tco(data, ["r6i"], db_size, growth_rate, 0, 0.0)

        # 현재(0y) 기준 스토리지 연간 비용
        current_costs = calc_storage_costs(db_size, 0, 0.0)
        current_yearly = current_costs["total"] * 12

        # TCO 1년차 스토리지
        tco_stor_1y = float(data["tco_detail_stor_1y"].replace(",", ""))

        assert tco_stor_1y != pytest.approx(current_yearly, rel=1e-4), (
            f"TCO 1년차 스토리지({tco_stor_1y:.2f})가 현재 기준({current_yearly:.2f})과 같으면 안 됩니다"
        )


# ─────────────────────────────────────────────
# Replatform vs Refactoring 비용 비교 테스트 (요구사항 16)
# ─────────────────────────────────────────────


class TestRefactoringComparison:
    """_fill_refactoring_comparison 및 _fill_refactoring_defaults 검증 테스트."""

    def _make_estimator(self, engine="oracle-ee"):
        """DB 없이 Estimator 인스턴스를 생성합니다."""
        from rds_cost_estimator.estimator import Estimator

        args = make_args(engine=engine)
        est = Estimator(args)
        est._db_store = None
        return est

    def _make_refac_price_index(self, inst, hourly_rate=0.50):
        """Refactoring 전용 price_index를 생성합니다."""
        from rds_cost_estimator.estimator import REFACTORING_ENGINE

        index = {}
        for pt in PricingType:
            rec = CostRecord(
                spec=InstanceSpec(
                    instance_type=inst,
                    region="ap-northeast-2",
                    engine=REFACTORING_ENGINE,
                    strategy=MigrationStrategy.REFACTORING,
                    deployment_option="Single-AZ",
                ),
                pricing_type=pt,
                hourly_rate=hourly_rate if pt == PricingType.ON_DEMAND else None,
                upfront_fee=0.0 if pt != PricingType.ON_DEMAND else None,
                monthly_fee=hourly_rate * 500 if pt != PricingType.ON_DEMAND else None,
                is_available=True,
            )
            key = (inst, "Single-AZ", pt)
            index[key] = rec
        return index

    def test_fill_refactoring_comparison_sets_all_keys(self):
        """Oracle 엔진일 때 모든 refac_ 키가 설정되어야 합니다."""
        est = self._make_estimator()
        inst = "db.r6i.2xlarge"
        families = ["r6i"]
        sga_instances = {"r6i": inst}

        # Replatform 비용 데이터 사전 설정
        data = {
            "stor_total_0y": "40.00",
            "net_monthly": "10.00",
            "sga_r6i_od_total_yearly": "12,000.00",
            "sga_r6i_ri1nu_total_yearly": "10,000.00",
            "sga_r6i_ri1au_total_yearly": "9,500.00",
            "sga_r6i_ri3nu_total_yearly": "8,000.00",
            "sga_r6i_ri3au_total_yearly": "7,000.00",
        }

        refac_index = self._make_refac_price_index(inst)
        est._fill_refactoring_comparison(data, refac_index, sga_instances, families)

        # 모든 요금 옵션에 대해 4개 키가 설정되어야 함
        opts = ["od", "ri1nu", "ri1au", "ri3nu", "ri3au"]
        for opt in opts:
            assert f"refac_r6i_{opt}_monthly" in data, f"refac_r6i_{opt}_monthly 키 누락"
            assert f"refac_r6i_{opt}_total_yearly" in data, f"refac_r6i_{opt}_total_yearly 키 누락"
            assert f"refac_r6i_{opt}_savings" in data, f"refac_r6i_{opt}_savings 키 누락"
            assert f"refac_r6i_{opt}_savings_rate" in data, f"refac_r6i_{opt}_savings_rate 키 누락"

    def test_fill_refactoring_comparison_savings_calculation(self):
        """절감액과 절감률이 올바르게 계산되어야 합니다."""
        est = self._make_estimator()
        inst = "db.r6i.2xlarge"
        families = ["r6i"]
        sga_instances = {"r6i": inst}

        # Replatform 연간 비용: $12,000
        replat_yearly = 12_000.00
        data = {
            "stor_total_0y": "0.00",
            "net_monthly": "0.00",
            "sga_r6i_od_total_yearly": f"{replat_yearly:,.2f}",
        }

        # Refactoring 인스턴스 비용: 시간당 $0.50 → 월 $365.00 → 연 $4,380.00
        refac_index = self._make_refac_price_index(inst, hourly_rate=0.50)
        est._fill_refactoring_comparison(data, refac_index, sga_instances, families)

        refac_yearly_str = data["refac_r6i_od_total_yearly"]
        refac_yearly = float(refac_yearly_str.replace(",", ""))

        savings_str = data["refac_r6i_od_savings"]
        savings = float(savings_str.replace(",", ""))

        savings_rate_str = data["refac_r6i_od_savings_rate"]
        savings_rate = float(savings_rate_str)

        # 절감액 = Replatform - Refactoring
        expected_savings = replat_yearly - refac_yearly
        assert savings == pytest.approx(expected_savings, rel=1e-2), (
            f"절감액: 기대값 {expected_savings:.2f}, 실제값 {savings:.2f}"
        )

        # 절감률 = (Replatform - Refactoring) / Replatform * 100
        expected_rate = (replat_yearly - refac_yearly) / replat_yearly * 100
        assert savings_rate == pytest.approx(expected_rate, rel=1e-1), (
            f"절감률: 기대값 {expected_rate:.1f}%, 실제값 {savings_rate:.1f}%"
        )

    def test_fill_refactoring_defaults_sets_na(self):
        """비Oracle 엔진일 때 모든 refac_ 키가 N/A로 설정되어야 합니다."""
        est = self._make_estimator(engine="postgresql")
        families = ["r6i", "r7i"]
        data: dict = {}

        est._fill_refactoring_defaults(data, families)

        opts = ["od", "ri1nu", "ri1au", "ri3nu", "ri3au"]
        for family in families:
            for opt in opts:
                assert data[f"refac_{family}_{opt}_monthly"] == "N/A"
                assert data[f"refac_{family}_{opt}_total_yearly"] == "N/A"
                assert data[f"refac_{family}_{opt}_savings"] == "N/A"
                assert data[f"refac_{family}_{opt}_savings_rate"] == "N/A"

    def test_fill_refactoring_comparison_missing_instance(self):
        """sga_instances에 패밀리가 없으면 N/A로 설정되어야 합니다."""
        est = self._make_estimator()
        families = ["r6i"]
        sga_instances: dict = {}  # 빈 딕셔너리

        data = {
            "stor_total_0y": "40.00",
            "net_monthly": "10.00",
        }

        est._fill_refactoring_comparison(data, {}, sga_instances, families)

        assert data["refac_r6i_od_monthly"] == "N/A"
        assert data["refac_r6i_od_total_yearly"] == "N/A"

    def test_build_template_data_oracle_sets_refac_visible(self):
        """Oracle 엔진 + refac_price_index가 있으면 refac_section_visible=True."""
        est = self._make_estimator(engine="oracle-ee")
        parsed = ParsedDocumentInfo(
            db_name="TestDB", db_size_gb=100.0,
        )
        inst = "db.r6i.2xlarge"
        refac_index = self._make_refac_price_index(inst)

        data = est._build_template_data(
            parsed=parsed,
            price_index={},
            refac_price_index=refac_index,
            spec_instances={"r6i": inst},
            sga_instances={"r6i": inst},
            family_a="r6i",
            family_b=None,
        )

        assert data["refac_section_visible"] is True

    def test_build_template_data_non_oracle_sets_refac_not_visible(self):
        """비Oracle 엔진이면 refac_section_visible=False."""
        est = self._make_estimator(engine="postgresql")
        parsed = ParsedDocumentInfo(
            db_name="TestDB", db_size_gb=100.0,
        )
        inst = "db.r6i.2xlarge"

        data = est._build_template_data(
            parsed=parsed,
            price_index={},
            refac_price_index={},
            spec_instances={"r6i": inst},
            sga_instances={"r6i": inst},
            family_a="r6i",
            family_b=None,
        )

        assert data["refac_section_visible"] is False
        # 기본값이 설정되어야 함
        assert data["refac_r6i_od_monthly"] == "N/A"


class TestRefactoringRendererPostProcessing:
    """renderer.py에서 비Oracle 엔진일 때 Refactoring 섹션 제거 검증."""

    def test_refactoring_section_removed_when_not_visible(self, tmp_path):
        """refac_section_visible=False일 때 섹션 8이 제거되어야 합니다."""
        from rds_cost_estimator.renderer import ReportRenderer

        # 최소한의 template_data 생성
        template_data = {
            "family_a": "r6i",
            "family_b": "r7i",
            "refac_section_visible": False,
            "db_name": "TestDB",
            "aws_region": "ap-northeast-2",
        }

        output_path = str(tmp_path / "report.md")
        # 실제 템플릿 파일 사용
        ReportRenderer.render_markdown_v2(
            template_data=template_data,
            output_path=output_path,
        )

        with open(output_path, "r", encoding="utf-8") as f:
            content = f.read()

        # "이관 전략별 비용 비교" 섹션이 제거되어야 함
        assert "이관 전략별 비용 비교" not in content, (
            "비Oracle 엔진일 때 Refactoring 비교 섹션이 제거되어야 합니다"
        )

    def test_refactoring_section_kept_when_visible(self, tmp_path):
        """refac_section_visible=True일 때 섹션 8이 유지되어야 합니다."""
        from rds_cost_estimator.renderer import ReportRenderer

        template_data = {
            "family_a": "r6i",
            "family_b": "r7i",
            "refac_section_visible": True,
            "db_name": "TestDB",
            "aws_region": "ap-northeast-2",
        }

        output_path = str(tmp_path / "report.md")
        ReportRenderer.render_markdown_v2(
            template_data=template_data,
            output_path=output_path,
        )

        with open(output_path, "r", encoding="utf-8") as f:
            content = f.read()

        # "이관 전략별 비용 비교" 섹션이 유지되어야 함
        assert "이관 전략별 비용 비교" in content, (
            "Oracle 엔진일 때 Refactoring 비교 섹션이 유지되어야 합니다"
        )

    def test_section_9_renumbered(self, tmp_path):
        """기존 섹션 8(권장사항)이 섹션 9로 변경되어야 합니다."""
        from rds_cost_estimator.renderer import ReportRenderer

        template_data = {
            "family_a": "r6i",
            "family_b": "r7i",
            "refac_section_visible": True,
            "db_name": "TestDB",
            "aws_region": "ap-northeast-2",
        }

        output_path = str(tmp_path / "report.md")
        ReportRenderer.render_markdown_v2(
            template_data=template_data,
            output_path=output_path,
        )

        with open(output_path, "r", encoding="utf-8") as f:
            content = f.read()

        assert "## 9. 권장사항" in content, (
            "기존 섹션 8(권장사항)이 섹션 9로 변경되어야 합니다"
        )


class TestRefactoringSpecGeneration:
    """run_v2()에서 Oracle 엔진일 때 Refactoring 스펙이 생성되는지 검증."""

    def test_oracle_engine_creates_refactoring_specs(self):
        """Oracle 엔진일 때 REFACTORING 전략 스펙이 생성되어야 합니다."""
        from rds_cost_estimator.estimator import (
            ORACLE_ENGINES,
            REFACTORING_ENGINE,
        )

        # Oracle 엔진 확인
        assert "oracle-ee" in ORACLE_ENGINES
        assert "oracle-se2" in ORACLE_ENGINES
        assert REFACTORING_ENGINE == "aurora-postgresql"

    def test_refac_price_index_separates_strategies(self):
        """Refactoring 레코드가 별도 인덱스에 저장되어야 합니다."""
        from rds_cost_estimator.estimator import REFACTORING_ENGINE

        # Replatform 레코드
        replat_rec = CostRecord(
            spec=InstanceSpec(
                instance_type="db.r6i.2xlarge",
                region="ap-northeast-2",
                engine="oracle-ee",
                strategy=MigrationStrategy.REPLATFORM,
                deployment_option="Single-AZ",
            ),
            pricing_type=PricingType.ON_DEMAND,
            hourly_rate=1.0,
            is_available=True,
        )

        # Refactoring 레코드
        refac_rec = CostRecord(
            spec=InstanceSpec(
                instance_type="db.r6i.2xlarge",
                region="ap-northeast-2",
                engine=REFACTORING_ENGINE,
                strategy=MigrationStrategy.REFACTORING,
                deployment_option="Single-AZ",
            ),
            pricing_type=PricingType.ON_DEMAND,
            hourly_rate=0.5,
            is_available=True,
        )

        all_records = [replat_rec, refac_rec]

        # Replatform 인덱스
        price_index = {}
        for rec in all_records:
            if rec.spec.strategy == MigrationStrategy.REPLATFORM:
                key = (rec.spec.instance_type, rec.spec.deployment_option, rec.pricing_type)
                price_index[key] = rec

        # Refactoring 인덱스
        refac_price_index = {}
        for rec in all_records:
            if rec.spec.strategy == MigrationStrategy.REFACTORING:
                key = (rec.spec.instance_type, rec.spec.deployment_option, rec.pricing_type)
                refac_price_index[key] = rec

        # 검증: 각 인덱스에 올바른 레코드만 포함
        assert len(price_index) == 1
        assert len(refac_price_index) == 1

        replat_key = ("db.r6i.2xlarge", "Single-AZ", PricingType.ON_DEMAND)
        assert price_index[replat_key].spec.strategy == MigrationStrategy.REPLATFORM
        assert refac_price_index[replat_key].spec.strategy == MigrationStrategy.REFACTORING
        assert price_index[replat_key].hourly_rate == 1.0
        assert refac_price_index[replat_key].hourly_rate == 0.5


class TestRegionPricing:
    """리전별 스토리지/네트워크 요금 테스트 (요구사항 11)."""

    def test_calc_storage_costs_default_region(self):
        """기본 리전(ap-northeast-2)에서 스토리지 비용이 올바르게 계산됩니다."""
        from rds_cost_estimator.instance_utils import calc_storage_costs
        costs = calc_storage_costs(100.0)
        # 100 GB × $0.08/GB = $8.00
        assert costs["storage"] == 8.0
        assert costs["total"] == 8.0

    def test_calc_storage_costs_tokyo_region(self):
        """도쿄 리전(ap-northeast-1)은 서울보다 비싼 스토리지 요금을 적용합니다."""
        from rds_cost_estimator.instance_utils import calc_storage_costs
        costs_seoul = calc_storage_costs(100.0, region="ap-northeast-2")
        costs_tokyo = calc_storage_costs(100.0, region="ap-northeast-1")
        # 도쿄: 100 GB × $0.096/GB = $9.60
        assert costs_tokyo["storage"] == 9.6
        assert costs_tokyo["total"] > costs_seoul["total"]

    def test_calc_storage_costs_unknown_region_fallback(self):
        """미지원 리전은 기본값(ap-northeast-2)으로 폴백합니다."""
        from rds_cost_estimator.instance_utils import calc_storage_costs
        costs_default = calc_storage_costs(100.0, region="ap-northeast-2")
        costs_unknown = calc_storage_costs(100.0, region="unknown-region-1")
        assert costs_unknown["total"] == costs_default["total"]

    def test_get_region_pricing_returns_correct_values(self):
        """get_region_pricing이 리전별 올바른 요금을 반환합니다."""
        from rds_cost_estimator.instance_utils import get_region_pricing
        rp = get_region_pricing("ap-northeast-1")
        assert rp["gp3_per_gb"] == 0.096
        assert rp["iops_per_unit"] == 0.024

    def test_different_regions_produce_different_costs(self):
        """서로 다른 요금을 가진 리전에서 다른 결과를 반환합니다."""
        from rds_cost_estimator.instance_utils import calc_storage_costs
        costs_seoul = calc_storage_costs(500.0, region="ap-northeast-2")
        costs_tokyo = calc_storage_costs(500.0, region="ap-northeast-1")
        costs_ireland = calc_storage_costs(500.0, region="eu-west-1")
        # 서울 < 아일랜드 < 도쿄
        assert costs_seoul["total"] < costs_ireland["total"]
        assert costs_ireland["total"] < costs_tokyo["total"]
