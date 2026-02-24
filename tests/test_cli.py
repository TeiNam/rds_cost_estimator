"""
CLI 인수 파싱 테스트 모듈.

parse_args 함수의 기본값, 플래그 동작, 필수 인수 검증 등을 테스트합니다.
"""

from __future__ import annotations

import pytest

from rds_cost_estimator.cli import parse_args
from rds_cost_estimator.models import CLIArgs


# 기본 입력 파일 인수 (positional argument 필수)
BASE_ARGS = ["report.md"]


class TestDefaultValues:
    """기본값 검증 테스트."""

    def test_region_default(self) -> None:
        """--region 기본값이 ap-northeast-2인지 확인."""
        args = parse_args(BASE_ARGS)
        assert args.region == "ap-northeast-2"

    def test_engine_default(self) -> None:
        """--engine 기본값이 oracle-ee인지 확인."""
        args = parse_args(BASE_ARGS)
        assert args.engine == "oracle-ee"

    def test_bedrock_model_default(self) -> None:
        """--bedrock-model 기본값이 Claude Sonnet 4.6인지 확인."""
        args = parse_args(BASE_ARGS)
        assert args.bedrock_model == "anthropic.claude-sonnet-4-6"

    def test_verbose_default_false(self) -> None:
        """--verbose 플래그 기본값이 False인지 확인."""
        args = parse_args(BASE_ARGS)
        assert args.verbose is False

    def test_profile_default_none(self) -> None:
        """--profile 기본값이 None인지 확인."""
        args = parse_args(BASE_ARGS)
        assert args.profile is None

    def test_output_format_default_none(self) -> None:
        """--json 미지정 시 output_format이 None인지 확인."""
        args = parse_args(BASE_ARGS)
        assert args.output_format is None

    def test_output_dir_default_current(self) -> None:
        """--output-dir 기본값이 '.'인지 확인."""
        args = parse_args(BASE_ARGS)
        assert args.output_dir == "."

    def test_input_file_is_positional(self) -> None:
        """input_file이 positional argument로 파싱되는지 확인."""
        args = parse_args(["my_report.md"])
        assert args.input_file == "my_report.md"


class TestVerboseFlag:
    """--verbose 플래그 동작 테스트."""

    def test_verbose_flag_enabled(self) -> None:
        """--verbose 플래그 지정 시 True로 설정되는지 확인."""
        args = parse_args(BASE_ARGS + ["--verbose"])
        assert args.verbose is True

    def test_verbose_flag_not_specified(self) -> None:
        """--verbose 플래그 미지정 시 False로 유지되는지 확인."""
        args = parse_args(BASE_ARGS)
        assert args.verbose is False


class TestRequiredArgsValidation:
    """필수 인수 누락 시 검증 테스트."""

    def test_missing_input_file_raises_system_exit(self) -> None:
        """input_file(positional) 누락 시 SystemExit 발생 확인."""
        with pytest.raises(SystemExit) as exc_info:
            parse_args([])
        assert exc_info.value.code == 2


class TestFullArgsParsing:
    """모든 인수를 정상적으로 파싱하는지 테스트."""

    def test_all_args_parsed_correctly(self) -> None:
        """모든 인수를 지정했을 때 올바르게 파싱되는지 확인."""
        args = parse_args([
            "spec.pdf",
            "--region", "us-east-1",
            "--current-instance", "db.r6i.2xlarge",
            "--recommended-instance-by-size", "db.r7i.2xlarge",
            "--recommended-instance-by-sga", "db.r7i.large",
            "--on-prem-cost", "250000.50",
            "--engine", "aurora-postgresql",
            "--profile", "my-aws-profile",
            "--verbose",
            "--json",
            "-o", "/tmp/output",
            "--bedrock-model", "anthropic.claude-3-haiku-20240307-v1:0",
        ])

        assert isinstance(args, CLIArgs)
        assert args.input_file == "spec.pdf"
        assert args.region == "us-east-1"
        assert args.current_instance == "db.r6i.2xlarge"
        assert args.recommended_instance_by_size == "db.r7i.2xlarge"
        assert args.recommended_instance_by_sga == "db.r7i.large"
        assert args.on_prem_cost == 250000.50
        assert args.engine == "aurora-postgresql"
        assert args.profile == "my-aws-profile"
        assert args.verbose is True
        assert args.output_format == "json"
        assert args.output_dir == "/tmp/output"
        assert args.bedrock_model == "anthropic.claude-3-haiku-20240307-v1:0"

    def test_returns_cli_args_instance(self) -> None:
        """반환값이 CLIArgs 인스턴스인지 확인."""
        result = parse_args(BASE_ARGS)
        assert isinstance(result, CLIArgs)

    def test_json_flag_sets_output_format(self) -> None:
        """--json 플래그 지정 시 output_format이 'json'으로 설정되는지 확인."""
        args = parse_args(BASE_ARGS + ["--json"])
        assert args.output_format == "json"

    def test_output_dir_custom(self) -> None:
        """--output-dir 커스텀 값이 올바르게 파싱되는지 확인."""
        args = parse_args(BASE_ARGS + ["-o", "/tmp/reports"])
        assert args.output_dir == "/tmp/reports"
