"""
콘솔 표, JSON, Markdown 출력 모듈.

CostTable 데이터를 rich 라이브러리로 콘솔에 표로 출력하거나
JSON 파일, 템플릿 기반 Markdown 리포트로 저장합니다.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime
from typing import Optional

from rich.console import Console
from rich.table import Table

from rds_cost_estimator.cost_table import CostTable
from rds_cost_estimator.models import MigrationStrategy

logger = logging.getLogger(__name__)

# 템플릿 파일 경로 (프로젝트 루트의 cost_report_template_v2.md)
_TEMPLATE_SEARCH_PATHS = [
    "cost_report_template_v2.md",
    os.path.join(os.path.dirname(__file__), "..", "..", "cost_report_template_v2.md"),
]


def _fmt_currency(value: Optional[float]) -> str:
    """비용 값을 USD 통화 형식으로 변환합니다."""
    if value is None:
        return "N/A"
    return f"${value:,.2f}"


def _fmt_savings_rate(value: Optional[float]) -> str:
    """절감률을 퍼센트 형식으로 변환합니다."""
    if value is None:
        return "N/A"
    return f"{value:.1f}%"


def _find_template() -> Optional[str]:
    """템플릿 파일을 찾아 경로를 반환합니다."""
    for path in _TEMPLATE_SEARCH_PATHS:
        abs_path = os.path.abspath(path)
        if os.path.isfile(abs_path):
            return abs_path
    return None


def _remove_na_rows(content: str) -> str:
    """테이블에서 N/A만 있는 행을 제거하고, 해당 테이블 아래에 안내 문구를 추가합니다.

    마크다운 테이블의 데이터 행(헤더/구분선 제외)에서:
    1. 비용 셀($N/A)이 포함된 행 → 제거 + 상품 부재 안내 문구
    2. 데이터 셀이 모두 N/A인 행 (예: CPU 사용률 | N/A% | N/A%) → 조용히 제거
    """
    lines = content.split("\n")
    result_lines: list[str] = []
    removed_options: list[str] = []
    in_table = False

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # 테이블 행 감지 (| 로 시작하고 끝나는 행)
        if stripped.startswith("|") and stripped.endswith("|"):
            # 구분선 행 (|---|---|) 은 그대로 유지
            if re.match(r"^\|[\s\-:|]+\|$", stripped):
                result_lines.append(line)
                in_table = True
                i += 1
                continue

            # 헤더 행 감지 (다음 줄이 구분선이면 헤더)
            if i + 1 < len(lines) and re.match(
                r"^\|[\s\-:|]+\|$", lines[i + 1].strip()
            ):
                result_lines.append(line)
                in_table = True
                i += 1
                continue

            # 데이터 행: 비용 셀에 $N/A가 포함되어 있는지 확인
            if in_table and ("$N/A" in stripped or "**$N/A**" in stripped):
                # 요금 옵션 이름 추출 (첫 번째 셀)
                cells = [c.strip() for c in stripped.split("|") if c.strip()]
                if cells:
                    option_name = re.sub(r"\*\*", "", cells[0]).strip()
                    if option_name not in removed_options:
                        removed_options.append(option_name)
                # 이 행은 건너뜀 (제거)
                i += 1
                continue

            # 데이터 행: 첫 번째 셀(라벨) 제외 나머지 셀이 모두 N/A인지 확인
            if in_table:
                cells = [c.strip() for c in stripped.split("|") if c.strip()]
                if len(cells) >= 2:
                    data_cells = cells[1:]  # 라벨 제외
                    # 모든 데이터 셀이 N/A 패턴인지 확인 (N/A, N/A%, N/A GB 등)
                    all_na = all(
                        re.match(r"^(?:\*\*)?N/A(?:%| GB| IOPS)?(?:\*\*)?$", c)
                        for c in data_cells
                    )
                    if all_na:
                        # 조용히 제거 (안내 문구 없이)
                        i += 1
                        continue

            in_table = True
            result_lines.append(line)
            i += 1
            continue
        else:
            # 테이블이 끝남
            if in_table and removed_options:
                # 테이블 직후에 안내 문구 삽입
                options_str = ", ".join(removed_options)
                result_lines.append("")
                result_lines.append(
                    f"> ℹ️ {options_str} 옵션은 해당 리전/인스턴스 조합에서 "
                    f"AWS 상품이 제공되지 않아 표시되지 않습니다."
                )
                removed_options = []
            in_table = False
            result_lines.append(line)
            i += 1

    # 파일 끝에서 테이블이 끝난 경우
    if removed_options:
        options_str = ", ".join(removed_options)
        result_lines.append("")
        result_lines.append(
            f"> ℹ️ {options_str} 옵션은 해당 리전/인스턴스 조합에서 "
            f"AWS 상품이 제공되지 않아 표시되지 않습니다."
        )

    return "\n".join(result_lines)


class ReportRenderer:
    """비용 비교 결과를 콘솔 표, JSON, Markdown으로 출력하는 클래스."""

    @staticmethod
    def render_console(table: CostTable) -> None:
        """CostTable 데이터를 콘솔에 표로 출력합니다."""
        console = Console()
        rows = table.compute_savings()

        if not rows:
            console.print("조회된 비용 데이터가 없습니다.")
            return

        rich_table = Table(show_header=True, header_style="bold")
        rich_table.add_column("인스턴스 유형", style="cyan")
        rich_table.add_column("이관 전략", style="magenta")
        rich_table.add_column("온디맨드 (연간)", justify="right")
        rich_table.add_column("1년 RI", justify="right")
        rich_table.add_column("3년 RI", justify="right")
        rich_table.add_column("절감률 (온디맨드)", justify="right")
        rich_table.add_column("절감률 (1년 RI)", justify="right")
        rich_table.add_column("절감률 (3년 RI)", justify="right")

        for row in rows:
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

        console.print(rich_table)

    @staticmethod
    def render_json(table: CostTable, output_path: str) -> None:
        """CostTable 데이터를 JSON 파일로 저장합니다."""
        data = table.to_dict()
        json_str = json.dumps(data, ensure_ascii=False, indent=2)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(json_str)
        logger.info("JSON 파일 저장 완료 → %s", output_path)

    @staticmethod
    def render_json_v2(data: dict, output_path: str) -> None:
        """템플릿 v2 데이터를 JSON 파일로 저장합니다."""
        json_str = json.dumps(data, ensure_ascii=False, indent=2, default=str)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(json_str)
        logger.info("JSON v2 파일 저장 완료 → %s", output_path)

    @staticmethod
    def render_markdown(
        table: CostTable,
        output_path: str,
        title: str = "RDS 이관 비용 비교 리포트",
        source_engine: str = "",
        region: str = "",
    ) -> None:
        """CostTable 데이터를 Markdown 리포트 파일로 저장합니다 (하위 호환)."""
        rows = table.compute_savings()
        if not rows:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(f"# {title}\n\n조회된 비용 데이터가 없습니다.\n")
            return

        replatform_rows = [r for r in rows if r.strategy == MigrationStrategy.REPLATFORM]
        refactoring_rows = [r for r in rows if r.strategy == MigrationStrategy.REFACTORING]

        lines: list[str] = []
        lines.append(f"# {title}")
        lines.append("")
        lines.append(f"> 생성일: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        lines.append("")

        lines.append("## 개요")
        lines.append("")
        if source_engine:
            lines.append(f"- 원본 엔진: {source_engine}")
        if region:
            lines.append(f"- 리전: {region}")
        lines.append(f"- 온프레미스 연간 유지비용: {_fmt_currency(table.on_prem_annual_cost)}")
        lines.append("")

        if replatform_rows:
            lines.append("## Replatform (RDS for Oracle)")
            lines.append("")
            lines.append("| 인스턴스 | 온디맨드 (연간) | 1년 RI (연간) | 3년 RI (연간 환산) |")
            lines.append("|----------|---------------:|-------------:|------------------:|")
            for row in replatform_rows:
                lines.append(
                    f"| {row.instance_type} "
                    f"| {_fmt_currency(row.on_demand_annual)} "
                    f"| {_fmt_currency(row.ri_1yr_annual)} "
                    f"| {_fmt_currency(row.ri_3yr_annual)} |"
                )
            lines.append("")

        if refactoring_rows:
            lines.append("## Refactoring (Aurora PostgreSQL)")
            lines.append("")
            lines.append("| 인스턴스 | 온디맨드 (연간) | 1년 RI (연간) | 3년 RI (연간 환산) |")
            lines.append("|----------|---------------:|-------------:|------------------:|")
            for row in refactoring_rows:
                lines.append(
                    f"| {row.instance_type} "
                    f"| {_fmt_currency(row.on_demand_annual)} "
                    f"| {_fmt_currency(row.ri_1yr_annual)} "
                    f"| {_fmt_currency(row.ri_3yr_annual)} |"
                )
            lines.append("")

        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        logger.info("Markdown 리포트 저장 완료 → %s", output_path)

    @staticmethod
    def render_markdown_v2(
        template_data: dict,
        output_path: str,
        template_path: Optional[str] = None,
    ) -> None:
        """템플릿 v2 기반 Markdown 리포트를 생성합니다.

        cost_report_template_v2.md의 {placeholder}를 실제 데이터로 치환합니다.

        Args:
            template_data: Estimator.run_v2()가 반환한 플레이스홀더 데이터
            output_path: 출력 파일 경로
            template_path: 템플릿 파일 경로 (None이면 자동 탐색)
        """
        # 템플릿 파일 찾기
        if template_path is None:
            template_path = _find_template()

        if template_path is None or not os.path.isfile(template_path):
            logger.error("템플릿 파일을 찾을 수 없습니다: %s", template_path)
            # 폴백: 간단한 리포트 생성
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(f"# {template_data.get('db_name', 'Unknown')} AWS RDS 비용 예측 리포트\n\n")
                f.write("템플릿 파일(cost_report_template_v2.md)을 찾을 수 없어 간략 리포트를 생성합니다.\n\n")
                f.write(f"리전: {template_data.get('aws_region', 'N/A')}\n")
                f.write(f"DB 크기: {template_data.get('db_size', 'N/A')} GB\n")
            return

        # 템플릿 읽기
        with open(template_path, "r", encoding="utf-8") as f:
            template_content = f.read()

        # {placeholder} 치환
        # ${placeholder} 형태 (달러 기호 포함)와 {placeholder} 형태 모두 처리
        def replace_placeholder(match: re.Match) -> str:
            key = match.group(1)
            value = template_data.get(key)
            if value is not None:
                return str(value)
            # 치환할 값이 없으면 원본 유지
            return match.group(0)

        # {key} 패턴 치환 ($ 접두사 없는 것)
        result = re.sub(r"\{(\w+)\}", replace_placeholder, template_content)

        # ${key} 패턴 치환 (달러 기호 포함 - 비용 필드)
        def replace_dollar_placeholder(match: re.Match) -> str:
            key = match.group(1)
            value = template_data.get(key)
            if value is not None:
                return str(value)
            return match.group(0)

        result = re.sub(r"\$\{(\w+)\}", replace_dollar_placeholder, result)

        # N/A만 있는 테이블 행 제거 및 상품 부재 안내 추가
        result = _remove_na_rows(result)

        # 파일 저장
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(result)

        logger.info("템플릿 v2 Markdown 리포트 저장 완료 → %s", output_path)
