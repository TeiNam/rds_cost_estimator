"""
진입점 모듈.

`python -m rds_cost_estimator` 명령으로 실행되는 진입점입니다.
CLI 인수 파싱 → Estimator 실행 → 결과 렌더링 순서로 동작합니다.

참고 요구사항: 6.1, 6.2, 6.3
"""

from __future__ import annotations

import asyncio
import logging
import sys

from rds_cost_estimator.cli import parse_args
from rds_cost_estimator.estimator import Estimator
from rds_cost_estimator.renderer import ReportRenderer

# 모듈 레벨 로거 설정
logger = logging.getLogger(__name__)

# JSON 출력 파일 기본 이름
DEFAULT_OUTPUT_FILE = "rds_cost_report.json"


def main() -> None:
    """CLI 진입점 메인 함수.

    실행 흐름:
        1. CLI 인수 파싱 (parse_args)
        2. logging 설정 (INFO 기본, --verbose 시 DEBUG)
        3. Estimator 초기화 및 비동기 실행 (asyncio.run)
        4. 콘솔 표 렌더링 (ReportRenderer.render_console)
        5. --output-format json 지정 시 JSON 파일 저장 (ReportRenderer.render_json)

    예외 처리:
        처리되지 않은 모든 예외를 캐치하여 ERROR 레벨로 스택 트레이스를 로깅하고
        종료 코드 1로 프로세스를 종료합니다. (요구사항 6.3)
    """
    # CLI 인수 파싱 (필수 인수 누락 시 argparse가 종료 코드 1로 종료)
    args = parse_args()

    # logging 설정: --verbose 플래그에 따라 레벨 결정 (요구사항 6.1, 6.2)
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    logger.debug("로깅 설정 완료: 레벨=%s", logging.getLevelName(log_level))

    try:
        # Estimator 초기화 및 비용 예측 실행
        estimator = Estimator(args)
        logger.info("비용 예측 시작")
        cost_table = asyncio.run(estimator.run())
        logger.info("비용 예측 완료")

        # 콘솔 표 렌더링 (항상 실행)
        ReportRenderer.render_console(cost_table)

        # --output-format json 지정 시 JSON 파일 저장 (요구사항 4.5)
        if args.output_format == "json":
            # --output-file 미지정 시 기본 파일명 사용
            output_file = args.output_file if args.output_file else DEFAULT_OUTPUT_FILE
            ReportRenderer.render_json(cost_table, output_file)
            logger.info("JSON 결과 저장 완료: %s", output_file)

    except Exception as e:
        # 처리되지 않은 예외: 스택 트레이스 포함 ERROR 로그 후 종료 코드 1 (요구사항 6.3)
        logger.error("오류 발생: %s", e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
