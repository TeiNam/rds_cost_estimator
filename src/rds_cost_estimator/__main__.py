"""
진입점 모듈.

`python -m rds_cost_estimator` 또는 `rds-cost-estimator` 명령으로 실행됩니다.
리포트 파일을 입력받아 Bedrock으로 파싱 → Pricing API 조회 → MD 리포트 생성.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys

from dotenv import load_dotenv

from rds_cost_estimator.cli import parse_args
from rds_cost_estimator.estimator import Estimator
from rds_cost_estimator.renderer import ReportRenderer

logger = logging.getLogger(__name__)


def _derive_output_basename(input_file: str) -> str:
    """입력 파일명에서 출력 파일 기본 이름을 생성합니다."""
    basename = os.path.splitext(os.path.basename(input_file))[0]
    return f"{basename}_cost"


def main() -> None:
    """CLI 진입점 메인 함수.

    실행 흐름:
        1. CLI 인수 파싱 (input_file 필수)
        2. .env 로드 및 logging 설정
        3. Estimator 초기화 및 run_v2() 실행
        4. 템플릿 v2 기반 MD 리포트 생성
        5. --json 지정 시 JSON 파일도 생성
    """
    args = parse_args()
    load_dotenv()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    try:
        estimator = Estimator(args)
        logger.info("비용 예측 시작: %s", args.input_file)

        # 템플릿 v2 기반 실행
        template_data = asyncio.run(estimator.run_v2())
        logger.info("비용 예측 완료")

        # 출력 파일명 생성
        output_base = _derive_output_basename(args.input_file or "report")
        output_dir = args.output_dir
        os.makedirs(output_dir, exist_ok=True)

        # 템플릿 v2 기반 MD 리포트 생성
        md_path = os.path.join(output_dir, f"{output_base}.md")
        ReportRenderer.render_markdown_v2(template_data, md_path)
        print(f"MD 리포트 생성 완료: {md_path}")

        # --json 지정 시 JSON 파일도 생성
        if args.output_format == "json":
            json_path = os.path.join(output_dir, f"{output_base}.json")
            ReportRenderer.render_json_v2(template_data, json_path)
            print(f"JSON 파일 생성 완료: {json_path}")

    except Exception as e:
        logger.error("오류 발생: %s", e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
