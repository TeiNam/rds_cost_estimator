"""
CLI 인수 파싱 테스트 모듈.

parse_args 함수의 기본값, 플래그 동작, 필수 인수 검증 등을 테스트합니다.
"""

from __future__ import annotations

import pytest

from rds_cost_estimator.cli import parse_args
from rds_cost_estimator.models import CLIArgs


# 모든 필수 인수를 포함한 기본 인수 목록 (--input-file 없이 사용할 때)
REQUIRED_ARGS = [
    "--current-instance", "db.r6i.xlarge",
    "--recommended-instance", "db.r7i.xlarge",
    "--on-prem-cost", "100000",
]


class TestDefaultValues:
    """기본값 검증 테스트."""

    def test_region_default(self) -> None:
        """--region 기본값이 ap-northeast-2인지 확인."""
        args = parse_args(REQUIRED_ARGS)
        assert args.region == "ap-northeast-2"

    def test_engine_default(self) -> None:
        """--engine 기본값이 oracle-ee인지 확인."""
        args = parse_args(REQUIRED_ARGS)
        assert args.engine == "oracle-ee"

    def test_bedrock_model_default(self) -> None:
        """--bedrock-model 기본값이 Claude 3.5 Sonnet인지 확인."""
        args = parse_args(REQUIRED_ARGS)
        assert args.bedrock_model == "anthropic.claude-3-5-sonnet-20241022-v2:0"

    def test_verbose_default_false(self) -> None:
        """--verbose 플래그 기본값이 False인지 확인."""
        args = parse_args(REQUIRED_ARGS)
        assert args.verbose is False

    def test_profile_default_none(self) -> None:
        """--profile 기본값이 None인지 확인."""
        args = parse_args(REQUIRED_ARGS)
        assert args.profile is None

    def test_output_format_default_none(self) -> None:
        """--output-format 기본값이 None인지 확인."""
        args = parse_args(REQUIRED_ARGS)
        assert args.output_format is None

    def test_output_file_default_none(self) -> None:
        """--output-file 기본값이 None인지 확인."""
        args = parse_args(REQUIRED_ARGS)
        assert args.output_file is None

    def test_input_file_default_none(self) -> None:
        """--input-file 기본값이 None인지 확인."""
        args = parse_args(REQUIRED_ARGS)
        assert args.input_file is None


class TestVerboseFlag:
    """--verbose 플래그 동작 테스트."""

    def test_verbose_flag_enabled(self) -> None:
        """--verbose 플래그 지정 시 True로 설정되는지 확인."""
        args = parse_args(REQUIRED_ARGS + ["--verbose"])
        assert args.verbose is True

    def test_verbose_flag_not_specified(self) -> None:
        """--verbose 플래그 미지정 시 False로 유지되는지 확인."""
        args = parse_args(REQUIRED_ARGS)
        assert args.verbose is False


class TestRequiredArgsValidation:
    """필수 인수 누락 시 검증 테스트."""

    def test_missing_all_required_args_raises_system_exit(self) -> None:
        """--input-file 없이 모든 필수 인수 누락 시 SystemExit 발생 확인.

        argparse.error()는 내부적으로 sys.exit(2)를 호출합니다.
        """
        with pytest.raises(SystemExit) as exc_info:
            parse_args([])
        # argparse는 오류 시 종료 코드 2를 사용
        assert exc_info.value.code == 2

    def test_missing_current_instance_raises_system_exit(self) -> None:
        """--current-instance 누락 시 SystemExit 발생 확인."""
        with pytest.raises(SystemExit):
            parse_args([
                "--recommended-instance", "db.r7i.xlarge",
                "--on-prem-cost", "100000",
            ])

    def test_missing_recommended_instance_raises_system_exit(self) -> None:
        """--recommended-instance 누락 시 SystemExit 발생 확인."""
        with pytest.raises(SystemExit):
            parse_args([
                "--current-instance", "db.r6i.xlarge",
                "--on-prem-cost", "100000",
            ])

    def test_missing_on_prem_cost_raises_system_exit(self) -> None:
        """--on-prem-cost 누락 시 SystemExit 발생 확인."""
        with pytest.raises(SystemExit):
            parse_args([
                "--current-instance", "db.r6i.xlarge",
                "--recommended-instance", "db.r7i.xlarge",
            ])

    def test_input_file_bypasses_required_args(self) -> None:
        """--input-file 지정 시 다른 필수 인수 없어도 통과하는지 확인."""
        args = parse_args(["--input-file", "spec.pdf"])
        assert args.input_file == "spec.pdf"
        assert args.current_instance is None
        assert args.recommended_instance is None
        assert args.on_prem_cost is None


class TestFullArgsParsing:
    """모든 인수를 정상적으로 파싱하는지 테스트."""

    def test_all_args_parsed_correctly(self) -> None:
        """모든 인수를 지정했을 때 올바르게 파싱되는지 확인."""
        args = parse_args([
            "--region", "us-east-1",
            "--current-instance", "db.r6i.2xlarge",
            "--recommended-instance", "db.r7i.2xlarge",
            "--on-prem-cost", "250000.50",
            "--engine", "aurora-postgresql",
            "--profile", "my-aws-profile",
            "--verbose",
            "--output-format", "json",
            "--output-file", "result.json",
            "--bedrock-model", "anthropic.claude-3-haiku-20240307-v1:0",
        ])

        # CLIArgs 타입 확인
        assert isinstance(args, CLIArgs)

        # 각 인수 값 검증
        assert args.region == "us-east-1"
        assert args.current_instance == "db.r6i.2xlarge"
        assert args.recommended_instance == "db.r7i.2xlarge"
        assert args.on_prem_cost == 250000.50
        assert args.engine == "aurora-postgresql"
        assert args.profile == "my-aws-profile"
        assert args.verbose is True
        assert args.output_format == "json"
        assert args.output_file == "result.json"
        assert args.bedrock_model == "anthropic.claude-3-haiku-20240307-v1:0"

    def test_returns_cli_args_instance(self) -> None:
        """반환값이 CLIArgs 인스턴스인지 확인."""
        result = parse_args(REQUIRED_ARGS)
        assert isinstance(result, CLIArgs)

    def test_input_file_with_all_args(self) -> None:
        """--input-file과 다른 인수를 함께 지정했을 때 올바르게 파싱되는지 확인."""
        args = parse_args([
            "--input-file", "server_spec.docx",
            "--region", "ap-southeast-1",
            "--verbose",
        ])
        assert args.input_file == "server_spec.docx"
        assert args.region == "ap-southeast-1"
        assert args.verbose is True
