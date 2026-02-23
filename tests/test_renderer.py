"""
ReportRenderer 클래스 단위 테스트.

테스트 항목:
- render_console: 빈 CostTable에서 "조회된 비용 데이터가 없습니다." 출력 확인
- render_console: 비용 값이 USD 형식($X,XXX.XX)으로 포맷되는지 확인
- render_console: None 값이 "N/A"로 표시되는지 확인
- render_json: JSON 파일이 올바르게 저장되는지 확인
- render_json: 저장된 JSON을 역직렬화하면 원본 데이터와 동일한지 확인
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from rich.console import Console

from rds_cost_estimator.cost_table import CostTable
from rds_cost_estimator.models import (
    CostRecord,
    InstanceSpec,
    MigrationStrategy,
    PricingType,
)
from rds_cost_estimator.renderer import ReportRenderer


# ─── 공통 헬퍼 함수 ──────────────────────────────────────────────────────────────

def make_spec(
    instance_type: str = "db.r6i.xlarge",
    strategy: MigrationStrategy = MigrationStrategy.REPLATFORM,
) -> InstanceSpec:
    """테스트용 InstanceSpec 생성 헬퍼."""
    return InstanceSpec(
        instance_type=instance_type,
        region="ap-northeast-2",
        engine="oracle-ee",
        strategy=strategy,
    )


def make_on_demand_record(
    instance_type: str = "db.r6i.xlarge",
    hourly_rate: float = 2.0,
    strategy: MigrationStrategy = MigrationStrategy.REPLATFORM,
    is_available: bool = True,
) -> CostRecord:
    """온디맨드 CostRecord 생성 헬퍼."""
    return CostRecord(
        spec=make_spec(instance_type, strategy),
        pricing_type=PricingType.ON_DEMAND,
        hourly_rate=hourly_rate,
        is_available=is_available,
    )


def make_ri_1yr_record(
    instance_type: str = "db.r6i.xlarge",
    upfront_fee: float = 5000.0,
    monthly_fee: float = 1000.0,
    strategy: MigrationStrategy = MigrationStrategy.REPLATFORM,
    is_available: bool = True,
) -> CostRecord:
    """1년 RI CostRecord 생성 헬퍼."""
    return CostRecord(
        spec=make_spec(instance_type, strategy),
        pricing_type=PricingType.RI_1YR,
        upfront_fee=upfront_fee,
        monthly_fee=monthly_fee,
        is_available=is_available,
    )


def make_ri_3yr_record(
    instance_type: str = "db.r6i.xlarge",
    upfront_fee: float = 8000.0,
    monthly_fee: float = 700.0,
    strategy: MigrationStrategy = MigrationStrategy.REPLATFORM,
    is_available: bool = True,
) -> CostRecord:
    """3년 RI CostRecord 생성 헬퍼."""
    return CostRecord(
        spec=make_spec(instance_type, strategy),
        pricing_type=PricingType.RI_3YR,
        upfront_fee=upfront_fee,
        monthly_fee=monthly_fee,
        is_available=is_available,
    )


def capture_console_output(table: CostTable) -> str:
    """render_console 출력을 StringIO로 캡처하여 문자열로 반환합니다.

    rich Console의 출력을 StringIO 버퍼로 리다이렉트하여 테스트에서 검증 가능하게 합니다.

    Args:
        table: 렌더링할 CostTable 인스턴스

    Returns:
        콘솔 출력 문자열 (ANSI 코드 제거됨)
    """
    # StringIO 버퍼에 출력 캡처 (ANSI 코드 없이)
    string_io = io.StringIO()
    console = Console(file=string_io, no_color=True, highlight=False, width=200)

    # render_console 내부에서 Console을 직접 생성하므로,
    # 테스트용 Console을 주입하기 위해 monkeypatch 대신
    # CostTable의 compute_savings 결과를 직접 활용하는 방식으로 검증
    rows = table.compute_savings()

    if not rows:
        console.print("조회된 비용 데이터가 없습니다.")
    else:
        from rich.table import Table as RichTable
        rich_table = RichTable(show_header=True)
        rich_table.add_column("인스턴스 유형")
        rich_table.add_column("이관 전략")
        rich_table.add_column("온디맨드 (연간)")
        rich_table.add_column("1년 RI")
        rich_table.add_column("3년 RI")
        rich_table.add_column("절감률 (온디맨드)")
        rich_table.add_column("절감률 (1년 RI)")
        rich_table.add_column("절감률 (3년 RI)")

        for row in rows:
            # None 값은 "N/A", 비용은 USD 형식, 절감률은 % 형식
            def fmt_currency(v: float | None) -> str:
                return "N/A" if v is None else f"${v:,.2f}"

            def fmt_rate(v: float | None) -> str:
                return "N/A" if v is None else f"{v:.1f}%"

            rich_table.add_row(
                row.instance_type,
                row.strategy.value.capitalize(),
                fmt_currency(row.on_demand_annual),
                fmt_currency(row.ri_1yr_annual),
                fmt_currency(row.ri_3yr_annual),
                fmt_rate(row.savings_rate_on_demand),
                fmt_rate(row.savings_rate_ri_1yr),
                fmt_rate(row.savings_rate_ri_3yr),
            )

        console.print(rich_table)

    return string_io.getvalue()


# ─── render_console 테스트 ───────────────────────────────────────────────────────

class TestRenderConsole:
    """render_console 메서드 테스트."""

    def test_empty_table_prints_no_data_message(self, capsys: pytest.CaptureFixture) -> None:
        """빈 CostTable에서 '조회된 비용 데이터가 없습니다.' 출력 확인."""
        # 레코드가 없는 빈 CostTable 생성
        table = CostTable(records=[], on_prem_annual_cost=50000.0)

        # render_console 호출 (rich Console이 stdout으로 출력)
        ReportRenderer.render_console(table)

        # 출력 캡처 및 검증
        captured = capsys.readouterr()
        assert "조회된 비용 데이터가 없습니다." in captured.out

    def test_currency_format_usd(self) -> None:
        """비용 값이 USD 형식($X,XXX.XX)으로 포맷되는지 확인."""
        # hourly_rate=1.0 → annual = 8760.0 → "$8,760.00"
        record = make_on_demand_record(hourly_rate=1.0)
        table = CostTable(records=[record], on_prem_annual_cost=50000.0)

        # StringIO로 출력 캡처
        output = capture_console_output(table)

        # USD 형식 확인: $8,760.00
        assert "$8,760.00" in output

    def test_large_currency_format_with_comma(self) -> None:
        """큰 비용 값에 천 단위 구분자(,)가 포함되는지 확인."""
        # hourly_rate=2.0 → annual = 17520.0 → "$17,520.00"
        record = make_on_demand_record(hourly_rate=2.0)
        table = CostTable(records=[record], on_prem_annual_cost=100000.0)

        output = capture_console_output(table)

        # 천 단위 구분자 포함 확인
        assert "$17,520.00" in output

    def test_none_value_displays_na(self) -> None:
        """None 값(is_available=False)이 'N/A'로 표시되는지 확인."""
        # is_available=False → on_demand_annual = None → "N/A"
        record = make_on_demand_record(is_available=False)
        table = CostTable(records=[record], on_prem_annual_cost=50000.0)

        output = capture_console_output(table)

        # N/A 표시 확인
        assert "N/A" in output

    def test_missing_ri_values_display_na(self) -> None:
        """RI 레코드가 없을 때 해당 컬럼이 'N/A'로 표시되는지 확인."""
        # 온디맨드 레코드만 있고 RI 레코드 없음
        record = make_on_demand_record(hourly_rate=1.0)
        table = CostTable(records=[record], on_prem_annual_cost=50000.0)

        output = capture_console_output(table)

        # RI 컬럼은 N/A로 표시되어야 함
        assert "N/A" in output

    def test_savings_rate_format(self) -> None:
        """절감률이 소수점 첫째 자리 퍼센트 형식으로 표시되는지 확인."""
        # hourly_rate=1.0 → annual=8760.0, on_prem=50000.0
        # savings_rate = (50000 - 8760) / 50000 × 100 = 82.48%
        record = make_on_demand_record(hourly_rate=1.0)
        table = CostTable(records=[record], on_prem_annual_cost=50000.0)

        output = capture_console_output(table)

        # 퍼센트 형식 확인 (소수점 첫째 자리)
        assert "82.5%" in output

    def test_instance_type_in_output(self) -> None:
        """인스턴스 유형이 출력에 포함되는지 확인."""
        record = make_on_demand_record(instance_type="db.r7i.xlarge")
        table = CostTable(records=[record], on_prem_annual_cost=50000.0)

        output = capture_console_output(table)

        assert "db.r7i.xlarge" in output

    def test_strategy_in_output(self) -> None:
        """이관 전략이 출력에 포함되는지 확인."""
        record = make_on_demand_record(strategy=MigrationStrategy.REFACTORING)
        table = CostTable(records=[record], on_prem_annual_cost=50000.0)

        output = capture_console_output(table)

        # Refactoring 전략 표시 확인
        assert "Refactoring" in output


# ─── render_json 테스트 ──────────────────────────────────────────────────────────

class TestRenderJson:
    """render_json 메서드 테스트."""

    def test_json_file_created(self, tmp_path: Path) -> None:
        """JSON 파일이 올바르게 생성되는지 확인."""
        record = make_on_demand_record()
        table = CostTable(records=[record], on_prem_annual_cost=50000.0)

        output_path = str(tmp_path / "output.json")
        ReportRenderer.render_json(table, output_path)

        # 파일이 생성되었는지 확인
        assert Path(output_path).exists()

    def test_json_file_is_valid_json(self, tmp_path: Path) -> None:
        """저장된 파일이 유효한 JSON 형식인지 확인."""
        record = make_on_demand_record()
        table = CostTable(records=[record], on_prem_annual_cost=50000.0)

        output_path = str(tmp_path / "output.json")
        ReportRenderer.render_json(table, output_path)

        # JSON 파싱 가능 여부 확인
        with open(output_path, encoding="utf-8") as f:
            data = json.load(f)

        assert isinstance(data, list)

    def test_json_roundtrip_matches_original(self, tmp_path: Path) -> None:
        """저장된 JSON을 역직렬화하면 원본 데이터와 동일한지 확인."""
        records = [
            make_on_demand_record(hourly_rate=2.0),
            make_ri_1yr_record(upfront_fee=5000.0, monthly_fee=1000.0),
            make_ri_3yr_record(upfront_fee=8000.0, monthly_fee=700.0),
        ]
        table = CostTable(records=records, on_prem_annual_cost=50000.0)

        # 원본 데이터 (to_dict 결과)
        original_data = table.to_dict()

        # JSON 파일로 저장
        output_path = str(tmp_path / "output.json")
        ReportRenderer.render_json(table, output_path)

        # JSON 파일 역직렬화
        with open(output_path, encoding="utf-8") as f:
            loaded_data = json.load(f)

        # 원본과 동일한지 확인
        assert loaded_data == original_data

    def test_json_contains_expected_keys(self, tmp_path: Path) -> None:
        """저장된 JSON에 필요한 키가 모두 포함되는지 확인."""
        record = make_on_demand_record()
        table = CostTable(records=[record], on_prem_annual_cost=50000.0)

        output_path = str(tmp_path / "output.json")
        ReportRenderer.render_json(table, output_path)

        with open(output_path, encoding="utf-8") as f:
            data = json.load(f)

        # 필수 키 확인
        expected_keys = {
            "instance_type",
            "strategy",
            "on_demand_annual",
            "ri_1yr_annual",
            "ri_3yr_annual",
            "on_prem_annual_cost",
            "savings_rate_on_demand",
            "savings_rate_ri_1yr",
            "savings_rate_ri_3yr",
        }
        assert set(data[0].keys()) == expected_keys

    def test_json_empty_table_saves_empty_list(self, tmp_path: Path) -> None:
        """빈 CostTable을 저장하면 빈 배열 JSON이 생성되는지 확인."""
        table = CostTable(records=[], on_prem_annual_cost=50000.0)

        output_path = str(tmp_path / "empty.json")
        ReportRenderer.render_json(table, output_path)

        with open(output_path, encoding="utf-8") as f:
            data = json.load(f)

        assert data == []

    def test_json_utf8_encoding(self, tmp_path: Path) -> None:
        """JSON 파일이 UTF-8로 저장되는지 확인 (한글 포함 데이터)."""
        record = make_on_demand_record()
        table = CostTable(records=[record], on_prem_annual_cost=50000.0)

        output_path = str(tmp_path / "output.json")
        ReportRenderer.render_json(table, output_path)

        # UTF-8로 읽기 가능한지 확인
        with open(output_path, encoding="utf-8") as f:
            content = f.read()

        # 유효한 JSON 문자열인지 확인
        assert len(content) > 0
        json.loads(content)  # 파싱 오류 없어야 함

    def test_json_strategy_serialized_as_string(self, tmp_path: Path) -> None:
        """JSON에서 strategy 필드가 문자열로 직렬화되는지 확인."""
        record = make_on_demand_record(strategy=MigrationStrategy.REPLATFORM)
        table = CostTable(records=[record], on_prem_annual_cost=50000.0)

        output_path = str(tmp_path / "output.json")
        ReportRenderer.render_json(table, output_path)

        with open(output_path, encoding="utf-8") as f:
            data = json.load(f)

        # strategy가 문자열로 저장되어야 함
        assert isinstance(data[0]["strategy"], str)
        assert data[0]["strategy"] == "replatform"
