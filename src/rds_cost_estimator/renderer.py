"""
콘솔 표 및 JSON 출력 모듈.

이 모듈은 CostTable 데이터를 rich 라이브러리를 사용하여 콘솔에 표로 출력하거나
JSON 파일로 저장하는 기능을 제공합니다.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from rich.console import Console
from rich.table import Table

from rds_cost_estimator.cost_table import CostTable

# 모듈 레벨 로거 설정
logger = logging.getLogger(__name__)


def _fmt_currency(value: Optional[float]) -> str:
    """비용 값을 USD 통화 형식으로 변환합니다.

    Args:
        value: 비용 값 (USD). None이면 "N/A" 반환.

    Returns:
        USD 통화 형식 문자열 (예: "$12,345.67") 또는 "N/A"
    """
    if value is None:
        return "N/A"
    return f"${value:,.2f}"


def _fmt_savings_rate(value: Optional[float]) -> str:
    """절감률을 소수점 첫째 자리 퍼센트 형식으로 변환합니다.

    Args:
        value: 절감률 (%). None이면 "N/A" 반환.

    Returns:
        퍼센트 형식 문자열 (예: "83.3%") 또는 "N/A"
    """
    if value is None:
        return "N/A"
    return f"{value:.1f}%"


class ReportRenderer:
    """비용 비교 결과를 콘솔 표 또는 JSON 파일로 출력하는 클래스.

    모든 메서드는 정적 메서드로 구현되어 인스턴스 생성 없이 사용 가능합니다.
    """

    @staticmethod
    def render_console(table: CostTable) -> None:
        """CostTable 데이터를 rich 라이브러리를 사용하여 콘솔에 표로 출력합니다.

        데이터가 없으면 "조회된 비용 데이터가 없습니다." 메시지를 출력합니다.

        Args:
            table: 출력할 CostTable 인스턴스
        """
        console = Console()

        # 절감 계산 결과 조회
        rows = table.compute_savings()

        # 데이터가 없으면 안내 메시지 출력 후 종료
        if not rows:
            console.print("조회된 비용 데이터가 없습니다.")
            return

        # rich Table 생성 및 컬럼 정의
        rich_table = Table(show_header=True, header_style="bold")
        rich_table.add_column("인스턴스 유형", style="cyan")
        rich_table.add_column("이관 전략", style="magenta")
        rich_table.add_column("온디맨드 (연간)", justify="right")
        rich_table.add_column("1년 RI", justify="right")
        rich_table.add_column("3년 RI", justify="right")
        rich_table.add_column("절감률 (온디맨드)", justify="right")
        rich_table.add_column("절감률 (1년 RI)", justify="right")
        rich_table.add_column("절감률 (3년 RI)", justify="right")

        # 각 CostRow를 테이블 행으로 추가
        for row in rows:
            # 이관 전략 표시명 변환 (Enum 값 → 표시 문자열)
            strategy_display = row.strategy.value.capitalize()

            rich_table.add_row(
                row.instance_type,
                strategy_display,
                _fmt_currency(row.on_demand_annual),
                _fmt_currency(row.ri_1yr_annual),
                _fmt_currency(row.ri_3yr_annual),
                _fmt_savings_rate(row.savings_rate_on_demand),
                _fmt_savings_rate(row.savings_rate_ri_1yr),
                _fmt_savings_rate(row.savings_rate_ri_3yr),
            )

        # 콘솔에 테이블 출력
        console.print(rich_table)
        logger.debug("render_console: %d개의 행을 콘솔에 출력 완료", len(rows))

    @staticmethod
    def render_json(table: CostTable, output_path: str) -> None:
        """CostTable 데이터를 JSON 파일로 저장합니다.

        CostTable.to_dict() 결과를 JSON 형식으로 직렬화하여 지정된 경로에 저장합니다.
        한글 문자가 포함된 경우에도 올바르게 저장되도록 ensure_ascii=False를 사용합니다.

        Args:
            table: 저장할 CostTable 인스턴스
            output_path: JSON 파일 저장 경로
        """
        # CostTable을 딕셔너리 목록으로 변환
        data = table.to_dict()

        # JSON 직렬화 (한글 지원, 들여쓰기 2칸)
        json_str = json.dumps(data, ensure_ascii=False, indent=2)

        # UTF-8 인코딩으로 파일 저장
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(json_str)

        logger.info("render_json: JSON 파일 저장 완료 → %s", output_path)
