"""
문서 파싱 모듈.

정형 소스(AWR .out, migration_recommendation.md, DBCSI MD)는 직접 파싱하고,
비정형 소스(PDF, DOCX)는 Bedrock(AI)으로 보조 파싱합니다.
직접 파싱 결과가 항상 우선하며, Bedrock은 누락 필드만 보완합니다.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

from rds_cost_estimator.models import ParsedDocumentInfo

if TYPE_CHECKING:
    from rds_cost_estimator.bedrock_client import BedrockClient

# 모듈 레벨 로거 설정
logger = logging.getLogger(__name__)

# 지원하는 파일 형식 목록
SUPPORTED_FORMATS: list[str] = [".pdf", ".docx", ".txt", ".md", ".out"]


class DocumentParser:
    """문서 파일에서 인스턴스 사양 정보를 추출하는 클래스.

    정형 소스(AWR .out, migration_recommendation.md, DBCSI MD)는 직접 파싱하고,
    비정형 소스(PDF, DOCX)가 있으면 Bedrock(AI)으로 보조 파싱합니다.
    직접 파싱 결과가 항상 우선하며, Bedrock은 누락 필드만 보완합니다.
    """

    def __init__(self, bedrock_client: "BedrockClient | None" = None) -> None:
        """DocumentParser 초기화.

        Args:
            bedrock_client: AWS Bedrock Runtime 클라이언트 인스턴스.
                            비정형 문서(PDF/DOCX) 보조 파싱에 사용.
                            None이면 비정형 문서는 스킵됩니다.
        """
        self._bedrock_client = bedrock_client

    def parse(self, file_path: str) -> ParsedDocumentInfo:
        """파일 또는 디렉토리를 입력받아 인스턴스 사양 정보를 추출합니다.

        파싱 전략:
        1. 정형 소스 직접 파싱 (AWR .out, migration_recommendation.md, DBCSI MD)
        2. 비정형 소스(PDF/DOCX)가 있으면 Bedrock(AI)으로 보조 파싱
        3. 직접 파싱 결과 우선, Bedrock은 None인 필드만 보완

        Args:
            file_path: 파싱할 문서 파일 또는 디렉토리 경로

        Returns:
            문서에서 추출한 인스턴스 사양 정보
        """
        logger.info("문서 파싱 시작: %s", file_path)

        # 1단계: 정형 소스 직접 파싱
        awr_parsed = self._parse_awr_out_full(file_path)
        result = ParsedDocumentInfo()
        self._apply_awr_parsed(awr_parsed, result)
        self._supplement_from_md_files(file_path, result)

        # 2단계: 비정형 소스(PDF/DOCX) Bedrock 보조 파싱
        unstructured_files = self._find_unstructured_files(file_path)
        if unstructured_files:
            if self._bedrock_client is not None:
                bedrock_result = self._parse_unstructured_with_bedrock(unstructured_files)
                if bedrock_result is not None:
                    self._merge_bedrock_supplement(bedrock_result, result)
            else:
                logger.warning(
                    "비정형 파일 %d개 발견했으나 Bedrock 클라이언트 없음, 스킵: %s",
                    len(unstructured_files),
                    [os.path.basename(f) for f in unstructured_files],
                )

        logger.info("문서 파싱 완료: db_name=%s", result.db_name)
        return result









    def _parse_awr_out_full(self, file_path: str) -> dict:
        """AWR .out 파일의 모든 섹션을 직접 파싱합니다.

        OS-INFORMATION, MAIN-METRICS, MEMORY, SGA-ADVICE, PERCENT-CPU,
        SYSSTAT 섹션에서 ParsedDocumentInfo에 필요한 필드를 추출합니다.

        Returns:
            직접 파싱된 필드 딕셔너리 (키: ParsedDocumentInfo 필드명)
        """
        out_files = self._find_awr_out_files(file_path)
        if not out_files:
            return {}

        merged: dict = {}
        for out_file in out_files:
            logger.info("AWR .out 파일 전체 직접 파싱: %s", out_file)
            try:
                with open(out_file, "r", encoding="utf-8") as f:
                    content = f.read()
            except Exception as e:
                logger.warning("AWR .out 파일 읽기 실패: %s - %s", out_file, e)
                continue

            # 각 섹션 파싱
            os_info = self._parse_os_information(content)
            main_metrics = self._parse_main_metrics_full(content)
            memory = self._parse_memory_section(content)
            sga_advice = self._parse_sga_advice(content)
            network = self._parse_awr_out_network_from_content(content)

            # 결과 병합 (첫 번째 파일 우선)
            for d in [os_info, main_metrics, memory, sga_advice, network]:
                for k, v in d.items():
                    if v is not None and k not in merged:
                        merged[k] = v

        return merged

    def _apply_awr_parsed(self, awr: dict, parsed: ParsedDocumentInfo) -> None:
        """직접 파싱 결과를 ParsedDocumentInfo에 적용합니다.

        직접 파싱 결과가 있으면 Bedrock 결과를 덮어씁니다 (직접 파싱 우선).
        Bedrock에서만 추출 가능한 필드(recommended_instance 등)는 유지합니다.
        """
        if not awr:
            return

        # 기본 정보 (직접 파싱 우선)
        if awr.get("db_name"):
            parsed.db_name = awr["db_name"]
        if awr.get("oracle_version"):
            parsed.oracle_version = awr["oracle_version"]
        if awr.get("cpu_cores") is not None:
            parsed.cpu_cores = awr["cpu_cores"]
        if awr.get("num_cpus") is not None:
            parsed.num_cpus = awr["num_cpus"]
        if awr.get("physical_memory_gb") is not None:
            parsed.physical_memory_gb = awr["physical_memory_gb"]
        if awr.get("db_size_gb") is not None:
            parsed.db_size_gb = awr["db_size_gb"]
        if awr.get("instance_config"):
            parsed.instance_config = awr["instance_config"]

        # AWR 메트릭 (직접 파싱 우선 - 덮어쓰기)
        m = parsed.awr_metrics
        if awr.get("avg_cpu_percent") is not None:
            m.avg_cpu_percent = awr["avg_cpu_percent"]
        if awr.get("peak_cpu_percent") is not None:
            m.peak_cpu_percent = awr["peak_cpu_percent"]
        if awr.get("avg_cpu_per_s") is not None:
            m.avg_cpu_per_s = awr["avg_cpu_per_s"]
        if awr.get("peak_cpu_per_s") is not None:
            m.peak_cpu_per_s = awr["peak_cpu_per_s"]
        if awr.get("avg_iops") is not None:
            m.avg_iops = awr["avg_iops"]
        if awr.get("peak_iops") is not None:
            m.peak_iops = awr["peak_iops"]
        if awr.get("avg_memory_gb") is not None:
            m.avg_memory_gb = awr["avg_memory_gb"]
        if awr.get("peak_memory_gb") is not None:
            m.peak_memory_gb = awr["peak_memory_gb"]

        # 네트워크/Redo (직접 파싱 우선 - 덮어쓰기)
        if awr.get("sent_bytes_per_day") is not None:
            m.sqlnet_bytes_sent_per_day = awr["sent_bytes_per_day"]
        if awr.get("recv_bytes_per_day") is not None:
            m.sqlnet_bytes_received_per_day = awr["recv_bytes_per_day"]
        if awr.get("redo_bytes_per_day") is not None:
            m.redo_bytes_per_day = awr["redo_bytes_per_day"]

        # SGA 분석 (직접 파싱 우선)
        sga = parsed.sga_analysis
        if awr.get("current_sga_gb") is not None:
            sga.current_sga_gb = awr["current_sga_gb"]
        if awr.get("recommended_sga_gb") is not None:
            sga.recommended_sga_gb = awr["recommended_sga_gb"]

        logger.info("AWR .out 직접 파싱 결과 적용 완료: %d개 필드", len(awr))

    def _parse_os_information(self, content: str) -> dict:
        """AWR .out의 OS-INFORMATION 섹션에서 서버 기본 정보를 파싱합니다.

        추출 필드: db_name, oracle_version, cpu_cores, num_cpus,
                   physical_memory_gb, db_size_gb, instance_config, sga_target
        """
        import re

        match = re.search(
            r"~~BEGIN-OS-INFORMATION~~\s*\n(.*?)~~END-OS-INFORMATION~~",
            content, re.DOTALL,
        )
        if not match:
            return {}

        section = match.group(1)
        result: dict = {}

        # STAT_NAME → STAT_VALUE 매핑 파싱
        kv: dict[str, str] = {}
        for line in section.split("\n"):
            line = line.strip()
            if not line or line.startswith("---") or line.startswith("STAT_NAME"):
                continue
            # 고정 폭 형식: 이름(60자) + 값
            parts = line.split()
            if len(parts) >= 2:
                key = parts[0]
                value = " ".join(parts[1:])
                kv[key] = value

        # 필드 추출
        if "DB_NAME" in kv:
            result["db_name"] = kv["DB_NAME"]

        if "VERSION" in kv:
            result["oracle_version"] = kv["VERSION"]
        elif "BANNER" in kv:
            # BANNER에서 버전 추출: "Oracle Database 19c ... Release 19.0.0.0.0"
            banner = kv["BANNER"]
            ver_match = re.search(r"Release\s+([\d.]+)", banner)
            if ver_match:
                result["oracle_version"] = ver_match.group(1)

        if "NUM_CPU_CORES" in kv:
            try:
                result["cpu_cores"] = int(kv["NUM_CPU_CORES"])
            except ValueError:
                pass

        if "NUM_CPUS" in kv:
            try:
                result["num_cpus"] = int(kv["NUM_CPUS"])
            except ValueError:
                pass

        if "PHYSICAL_MEMORY_GB" in kv:
            try:
                result["physical_memory_gb"] = float(kv["PHYSICAL_MEMORY_GB"])
            except ValueError:
                pass

        if "TOTAL_DB_SIZE_GB" in kv:
            try:
                result["db_size_gb"] = float(kv["TOTAL_DB_SIZE_GB"])
            except ValueError:
                pass

        # 인스턴스 구성: "2 (RAC)" 형태
        if "INSTANCES" in kv:
            instances = kv["INSTANCES"]
            try:
                inst_count = int(instances)
                if inst_count > 1:
                    result["instance_config"] = f"{inst_count} (RAC)"
                else:
                    result["instance_config"] = "1 (Single)"
            except ValueError:
                result["instance_config"] = instances

        # SGA_TARGET (바이트 → GB)
        if "SGA_TARGET" in kv:
            try:
                sga_bytes = int(kv["SGA_TARGET"])
                if sga_bytes > 0:
                    result["current_sga_gb"] = round(sga_bytes / (1024 ** 3), 1)
            except ValueError:
                pass

        return result

    def _parse_main_metrics_full(self, content: str) -> dict:
        """AWR .out의 MAIN-METRICS 섹션에서 성능 메트릭을 파싱합니다.

        추출 필드: avg/peak CPU%, avg/peak CPU/s, avg/peak IOPS, redo_mb_s
        RAC 환경에서는 인스턴스별 합산(IOPS) 또는 평균(CPU%)을 계산합니다.

        주의: 'end' 컬럼은 날짜+시간(예: "26/01/15 09:00")으로 공백을 포함하여
        split() 시 2개 토큰이 됩니다. end 이후 컬럼만 +1 오프셋을 적용합니다.
        """
        import re

        match = re.search(
            r"~~BEGIN-MAIN-METRICS~~\s*\n(.*?)~~END-MAIN-METRICS~~",
            content, re.DOTALL,
        )
        if not match:
            return {}

        section = match.group(1)
        lines = section.strip().split("\n")

        # 헤더 행 찾기
        header_line = None
        data_start = 0
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("snap") or "os_cpu" in stripped:
                header_line = stripped
                data_start = i + 1
                break

        if not header_line:
            return {}

        headers = header_line.split()
        col_map = {h: idx for idx, h in enumerate(headers)}

        # 'end' 컬럼 위치 파악 (날짜+시간이 2개 토큰으로 분리됨)
        end_header_idx = col_map.get("end")

        # 구분선 건너뛰기
        for i in range(data_start, len(lines)):
            if lines[i].strip().startswith("---"):
                data_start = i + 1
                break

        def _col(cols: list[str], header_idx: int | None) -> str | None:
            """헤더 인덱스에서 end 컬럼 오프셋을 보정하여 데이터 값을 반환합니다.

            end 컬럼 이전: 오프셋 0 (snap, dur_m)
            end 컬럼 이후: 오프셋 +1 (inst, os_cpu, cpu_per_s, ...)
            """
            if header_idx is None:
                return None
            actual = header_idx
            if end_header_idx is not None and header_idx > end_header_idx:
                actual += 1
            if actual < len(cols):
                return cols[actual]
            return None

        # 필요한 컬럼 인덱스 (헤더 기준)
        os_cpu_idx = col_map.get("os_cpu")
        os_cpu_max_idx = col_map.get("os_cpu_max")
        cpu_per_s_idx = col_map.get("cpu_per_s")
        cpu_per_s_max_idx = col_map.get("cpu_per_s_max")
        read_iops_idx = col_map.get("read_iops")
        write_iops_idx = col_map.get("write_iops")
        read_iops_max_idx = col_map.get("read_iops_max")
        write_iops_max_idx = col_map.get("write_iops_max")
        redo_idx = col_map.get("redo_mb_s")
        dur_idx = col_map.get("dur_m")
        snap_idx = col_map.get("snap")
        inst_idx = col_map.get("inst")

        # 데이터 행 파싱 - 스냅샷×인스턴스별 수집
        rows: list[dict] = []
        for i in range(data_start, len(lines)):
            line = lines[i].strip()
            if not line or line.startswith("~~"):
                break
            cols = line.split()
            row: dict = {}
            try:
                v = _col(cols, snap_idx)
                if v is not None:
                    row["snap"] = v
                v = _col(cols, inst_idx)
                if v is not None:
                    row["inst"] = v
                v = _col(cols, os_cpu_idx)
                if v is not None:
                    row["os_cpu"] = float(v)
                v = _col(cols, os_cpu_max_idx)
                if v is not None:
                    row["os_cpu_max"] = float(v)
                v = _col(cols, cpu_per_s_idx)
                if v is not None:
                    row["cpu_per_s"] = float(v)
                v = _col(cols, cpu_per_s_max_idx)
                if v is not None:
                    row["cpu_per_s_max"] = float(v)
                v = _col(cols, read_iops_idx)
                if v is not None:
                    row["read_iops"] = float(v)
                v = _col(cols, write_iops_idx)
                if v is not None:
                    row["write_iops"] = float(v)
                v = _col(cols, read_iops_max_idx)
                if v is not None:
                    row["read_iops_max"] = float(v)
                v = _col(cols, write_iops_max_idx)
                if v is not None:
                    row["write_iops_max"] = float(v)
                v = _col(cols, redo_idx)
                if v is not None:
                    row["redo_mb_s"] = float(v)
                v = _col(cols, dur_idx)
                if v is not None:
                    row["dur_m"] = float(v)
                rows.append(row)
            except (ValueError, IndexError):
                continue

        if not rows:
            return {}

        result: dict = {}

        # 스냅샷별로 그룹핑 → 인스턴스 합산(IOPS, CPU/s) 또는 평균(CPU%)
        snap_groups: dict[str, list[dict]] = {}
        for row in rows:
            snap_key = row.get("snap", "0")
            snap_groups.setdefault(snap_key, []).append(row)

        # 스냅샷별 집계값 계산
        snap_os_cpu: list[float] = []
        snap_os_cpu_max: list[float] = []
        snap_cpu_per_s: list[float] = []
        snap_cpu_per_s_max: list[float] = []
        snap_iops: list[float] = []
        snap_iops_max: list[float] = []
        snap_redo: list[float] = []
        snap_dur: list[float] = []

        for snap_key, snap_rows in snap_groups.items():
            # CPU%: 인스턴스 평균 (각 인스턴스의 호스트 CPU 사용률)
            cpu_vals = [r["os_cpu"] for r in snap_rows if "os_cpu" in r]
            if cpu_vals:
                snap_os_cpu.append(sum(cpu_vals) / len(cpu_vals))

            cpu_max_vals = [r["os_cpu_max"] for r in snap_rows if "os_cpu_max" in r]
            if cpu_max_vals:
                snap_os_cpu_max.append(max(cpu_max_vals))

            # CPU/s: 인스턴스 합산 (RAC 전체 DB CPU 사용량)
            cps_vals = [r["cpu_per_s"] for r in snap_rows if "cpu_per_s" in r]
            if cps_vals:
                snap_cpu_per_s.append(sum(cps_vals))

            cps_max_vals = [r["cpu_per_s_max"] for r in snap_rows if "cpu_per_s_max" in r]
            if cps_max_vals:
                snap_cpu_per_s_max.append(sum(cps_max_vals))

            # IOPS: 인스턴스 합산
            iops_vals = []
            for r in snap_rows:
                ri = r.get("read_iops", 0)
                wi = r.get("write_iops", 0)
                iops_vals.append(ri + wi)
            if iops_vals:
                snap_iops.append(sum(iops_vals))

            iops_max_vals = []
            for r in snap_rows:
                ri = r.get("read_iops_max", 0)
                wi = r.get("write_iops_max", 0)
                iops_max_vals.append(ri + wi)
            if iops_max_vals:
                snap_iops_max.append(sum(iops_max_vals))

            # Redo: 인스턴스 합산
            redo_vals = [r["redo_mb_s"] for r in snap_rows if "redo_mb_s" in r]
            if redo_vals:
                snap_redo.append(sum(redo_vals))

            # dur_m: 첫 번째 값 사용
            dur_vals = [r["dur_m"] for r in snap_rows if "dur_m" in r]
            if dur_vals:
                snap_dur.append(dur_vals[0])

        # 스냅샷 평균 → 최종 결과
        if snap_os_cpu:
            result["avg_cpu_percent"] = round(sum(snap_os_cpu) / len(snap_os_cpu), 1)
        if snap_os_cpu_max:
            result["peak_cpu_percent"] = round(max(snap_os_cpu_max), 1)
        if snap_cpu_per_s:
            result["avg_cpu_per_s"] = round(sum(snap_cpu_per_s) / len(snap_cpu_per_s), 3)
        if snap_cpu_per_s_max:
            result["peak_cpu_per_s"] = round(max(snap_cpu_per_s_max), 3)
        if snap_iops:
            result["avg_iops"] = round(sum(snap_iops) / len(snap_iops), 0)
        if snap_iops_max:
            result["peak_iops"] = round(max(snap_iops_max), 0)

        # Redo → 일별 바이트
        if snap_redo:
            avg_redo_mb_s = sum(snap_redo) / len(snap_redo)
            result["redo_bytes_per_day"] = avg_redo_mb_s * 86400 * 1024 * 1024

        # dur_m (스냅샷 기간) 저장
        if snap_dur:
            result["dur_m"] = sum(snap_dur) / len(snap_dur)

        return result

    def _parse_memory_section(self, content: str) -> dict:
        """AWR .out의 MEMORY 섹션에서 메모리 사용량을 파싱합니다.

        RAC 환경에서는 인스턴스별 TOTAL(SGA+PGA)을 합산합니다.
        """
        import re

        match = re.search(
            r"~~BEGIN-MEMORY~~\s*\n(.*?)~~END-MEMORY~~",
            content, re.DOTALL,
        )
        if not match:
            return {}

        section = match.group(1)
        lines = section.strip().split("\n")

        # 헤더 행 찾기
        header_line = None
        data_start = 0
        for i, line in enumerate(lines):
            stripped = line.strip()
            if "SNAP_ID" in stripped or "TOTAL" in stripped:
                header_line = stripped
                data_start = i + 1
                break

        if not header_line:
            return {}

        headers = header_line.split()
        col_map = {h: idx for idx, h in enumerate(headers)}

        snap_idx = col_map.get("SNAP_ID")
        inst_idx = col_map.get("INSTANCE_NUMBER")
        total_idx = col_map.get("TOTAL")

        if total_idx is None:
            return {}

        # 구분선 건너뛰기
        for i in range(data_start, len(lines)):
            if lines[i].strip().startswith("---"):
                data_start = i + 1
                break

        # 데이터 행 파싱
        rows: list[dict] = []
        for i in range(data_start, len(lines)):
            line = lines[i].strip()
            if not line or line.startswith("~~"):
                break
            cols = line.split()
            try:
                row: dict = {}
                if snap_idx is not None and len(cols) > snap_idx:
                    row["snap"] = cols[snap_idx]
                if inst_idx is not None and len(cols) > inst_idx:
                    row["inst"] = cols[inst_idx]
                if total_idx is not None and len(cols) > total_idx:
                    row["total"] = float(cols[total_idx])
                rows.append(row)
            except (ValueError, IndexError):
                continue

        if not rows:
            return {}

        # 스냅샷별 인스턴스 합산
        snap_totals: dict[str, float] = {}
        for row in rows:
            snap_key = row.get("snap", "0")
            snap_totals[snap_key] = snap_totals.get(snap_key, 0) + row.get("total", 0)

        totals = list(snap_totals.values())
        if not totals:
            return {}

        return {
            "avg_memory_gb": round(sum(totals) / len(totals), 1),
            "peak_memory_gb": round(max(totals), 1),
        }

    def _parse_sga_advice(self, content: str) -> dict:
        """AWR .out의 SGA-ADVICE 섹션에서 SGA 분석 결과를 파싱합니다.

        현재 SGA 크기(SGA_SIZE_FACTOR=1.00)와 권장 SGA 크기를 추출합니다.
        권장 SGA: ESTD_DB_TIME_FACTOR가 0.90 이하인 최소 SGA 크기.
        """
        import re

        match = re.search(
            r"~~BEGIN-SGA-ADVICE~~\s*\n(.*?)~~END-SGA-ADVICE~~",
            content, re.DOTALL,
        )
        if not match:
            return {}

        section = match.group(1)
        lines = section.strip().split("\n")

        # 헤더 행 찾기
        header_line = None
        data_start = 0
        for i, line in enumerate(lines):
            stripped = line.strip()
            if "SGA_SIZE" in stripped or "INST_ID" in stripped:
                header_line = stripped
                data_start = i + 1
                break

        if not header_line:
            return {}

        headers = header_line.split()
        col_map = {h: idx for idx, h in enumerate(headers)}

        inst_idx = col_map.get("INST_ID")
        sga_size_idx = col_map.get("SGA_SIZE")
        factor_idx = col_map.get("SGA_SIZE_FACTOR")
        db_time_factor_idx = col_map.get("ESTD_DB_TIME_FACTOR")

        if sga_size_idx is None or factor_idx is None:
            return {}

        # 구분선 건너뛰기
        for i in range(data_start, len(lines)):
            if lines[i].strip().startswith("---"):
                data_start = i + 1
                break

        # 데이터 행 파싱 (인스턴스 1만 사용)
        current_sga: float | None = None
        recommended_sga: float | None = None

        for i in range(data_start, len(lines)):
            line = lines[i].strip()
            if not line or line.startswith("~~"):
                break
            cols = line.split()
            try:
                inst = int(cols[inst_idx]) if inst_idx is not None else 1
                if inst != 1:
                    continue

                sga_size = float(cols[sga_size_idx])
                sga_factor = float(cols[factor_idx])

                # 현재 SGA: factor = 1.00
                if abs(sga_factor - 1.0) < 0.01:
                    current_sga = sga_size

                # 권장 SGA: DB Time Factor ≤ 0.90인 최소 크기
                if db_time_factor_idx is not None and len(cols) > db_time_factor_idx:
                    db_time_factor = float(cols[db_time_factor_idx])
                    if db_time_factor <= 0.90:
                        if recommended_sga is None or sga_size < recommended_sga:
                            recommended_sga = sga_size
            except (ValueError, IndexError):
                continue

        result: dict = {}
        if current_sga is not None:
            result["current_sga_gb"] = current_sga
        if recommended_sga is not None:
            result["recommended_sga_gb"] = recommended_sga

        return result




    # ─── 비정형 소스(PDF/DOCX) Bedrock 보조 파싱 ───

    # 직접 파싱 대상 확장자 (Bedrock에 보내지 않음)
    _STRUCTURED_EXTENSIONS: set[str] = {".out", ".md", ".txt"}

    # 비정형 소스 확장자 (Bedrock 보조 파싱 대상)
    _UNSTRUCTURED_EXTENSIONS: set[str] = {".pdf", ".docx"}

    def _find_unstructured_files(self, file_path: str) -> list[str]:
        """디렉토리에서 비정형 파일(PDF/DOCX)을 찾습니다.

        단일 파일 입력 시 해당 파일이 비정형이면 리스트로 반환합니다.
        """
        if os.path.isfile(file_path):
            ext = os.path.splitext(file_path)[1].lower()
            if ext in self._UNSTRUCTURED_EXTENSIONS:
                return [file_path]
            return []

        if not os.path.isdir(file_path):
            return []

        result: list[str] = []
        for entry in sorted(os.listdir(file_path)):
            entry_path = os.path.join(file_path, entry)
            if not os.path.isfile(entry_path):
                continue
            ext = os.path.splitext(entry)[1].lower()
            if ext in self._UNSTRUCTURED_EXTENSIONS:
                result.append(entry_path)
        return result

    def _extract_text_from_pdf(self, file_path: str) -> str:
        """PDF 파일에서 텍스트를 추출합니다."""
        import pypdf

        logger.debug("PDF 텍스트 추출: %s", file_path)
        reader = pypdf.PdfReader(file_path)
        pages = [p.extract_text() for p in reader.pages if p.extract_text()]
        return "\n".join(pages)

    def _extract_text_from_docx(self, file_path: str) -> str:
        """DOCX 파일에서 텍스트를 추출합니다."""
        import docx

        logger.debug("DOCX 텍스트 추출: %s", file_path)
        document = docx.Document(file_path)
        return "\n".join(p.text for p in document.paragraphs)

    def _extract_unstructured_text(self, file_path: str) -> str:
        """비정형 파일에서 텍스트를 추출합니다."""
        ext = os.path.splitext(file_path)[1].lower()
        if ext == ".pdf":
            return self._extract_text_from_pdf(file_path)
        elif ext == ".docx":
            return self._extract_text_from_docx(file_path)
        return ""

    def _parse_unstructured_with_bedrock(
        self, files: list[str]
    ) -> "ParsedDocumentInfo | None":
        """비정형 파일들의 텍스트를 Bedrock에 전달하여 보조 파싱합니다.

        Returns:
            Bedrock 파싱 결과 또는 실패 시 None
        """
        text_parts: list[str] = []
        for fpath in files:
            fname = os.path.basename(fpath)
            try:
                text = self._extract_unstructured_text(fpath)
                if text.strip():
                    text_parts.append(f"=== 파일: {fname} ===\n{text}")
                    logger.info("비정형 파일 텍스트 추출 완료: %s (%d자)", fname, len(text))
            except Exception as e:
                logger.warning("비정형 파일 텍스트 추출 실패: %s - %s", fname, e)

        if not text_parts:
            return None

        combined = "\n\n".join(text_parts)
        logger.info("비정형 파일 %d개 → Bedrock 보조 파싱 시작 (%d자)",
                     len(text_parts), len(combined))

        try:
            return self._bedrock_client.invoke(combined)  # type: ignore[union-attr]
        except Exception as e:
            logger.warning("Bedrock 보조 파싱 실패: %s", e)
            return None

    @staticmethod
    def _merge_bedrock_supplement(
        bedrock: "ParsedDocumentInfo", result: "ParsedDocumentInfo"
    ) -> None:
        """Bedrock 보조 파싱 결과를 직접 파싱 결과에 병합합니다.

        직접 파싱 결과가 이미 있는 필드는 유지하고,
        None인 필드만 Bedrock 결과로 채웁니다.
        """
        # 기본 정보 (직접 파싱 결과가 없을 때만 보완)
        if not result.db_name and bedrock.db_name:
            result.db_name = bedrock.db_name
        if not result.oracle_version and bedrock.oracle_version:
            result.oracle_version = bedrock.oracle_version
        if result.cpu_cores is None and bedrock.cpu_cores is not None:
            result.cpu_cores = bedrock.cpu_cores
        if result.num_cpus is None and bedrock.num_cpus is not None:
            result.num_cpus = bedrock.num_cpus
        if result.physical_memory_gb is None and bedrock.physical_memory_gb is not None:
            result.physical_memory_gb = bedrock.physical_memory_gb
        if result.db_size_gb is None and bedrock.db_size_gb is not None:
            result.db_size_gb = bedrock.db_size_gb
        if not result.instance_config and bedrock.instance_config:
            result.instance_config = bedrock.instance_config
        if not result.current_instance and bedrock.current_instance:
            result.current_instance = bedrock.current_instance
        if not result.engine and bedrock.engine:
            result.engine = bedrock.engine
        if not result.target_engine and bedrock.target_engine:
            result.target_engine = bedrock.target_engine
        if not result.recommended_instance_by_size and bedrock.recommended_instance_by_size:
            result.recommended_instance_by_size = bedrock.recommended_instance_by_size
        if not result.recommended_instance_by_sga and bedrock.recommended_instance_by_sga:
            result.recommended_instance_by_sga = bedrock.recommended_instance_by_sga
        if result.on_prem_cost is None and bedrock.on_prem_cost is not None:
            result.on_prem_cost = bedrock.on_prem_cost

        # AWR 메트릭 (직접 파싱 결과가 없을 때만 보완)
        rm = result.awr_metrics
        bm = bedrock.awr_metrics
        if rm.avg_cpu_percent is None and bm.avg_cpu_percent is not None:
            rm.avg_cpu_percent = bm.avg_cpu_percent
        if rm.peak_cpu_percent is None and bm.peak_cpu_percent is not None:
            rm.peak_cpu_percent = bm.peak_cpu_percent
        if rm.avg_cpu_per_s is None and bm.avg_cpu_per_s is not None:
            rm.avg_cpu_per_s = bm.avg_cpu_per_s
        if rm.peak_cpu_per_s is None and bm.peak_cpu_per_s is not None:
            rm.peak_cpu_per_s = bm.peak_cpu_per_s
        if rm.avg_iops is None and bm.avg_iops is not None:
            rm.avg_iops = bm.avg_iops
        if rm.peak_iops is None and bm.peak_iops is not None:
            rm.peak_iops = bm.peak_iops
        if rm.avg_memory_gb is None and bm.avg_memory_gb is not None:
            rm.avg_memory_gb = bm.avg_memory_gb
        if rm.peak_memory_gb is None and bm.peak_memory_gb is not None:
            rm.peak_memory_gb = bm.peak_memory_gb
        if rm.sqlnet_bytes_sent_per_day is None and bm.sqlnet_bytes_sent_per_day is not None:
            rm.sqlnet_bytes_sent_per_day = bm.sqlnet_bytes_sent_per_day
        if rm.sqlnet_bytes_received_per_day is None and bm.sqlnet_bytes_received_per_day is not None:
            rm.sqlnet_bytes_received_per_day = bm.sqlnet_bytes_received_per_day
        if rm.redo_bytes_per_day is None and bm.redo_bytes_per_day is not None:
            rm.redo_bytes_per_day = bm.redo_bytes_per_day

        # SGA 분석
        rs = result.sga_analysis
        bs = bedrock.sga_analysis
        if rs.current_sga_gb is None and bs.current_sga_gb is not None:
            rs.current_sga_gb = bs.current_sga_gb
        if rs.recommended_sga_gb is None and bs.recommended_sga_gb is not None:
            rs.recommended_sga_gb = bs.recommended_sga_gb

        # 스토리지 증가 추이
        rg = result.storage_growth
        bg = bedrock.storage_growth
        if rg.current_db_size_gb is None and bg.current_db_size_gb is not None:
            rg.current_db_size_gb = bg.current_db_size_gb
        if rg.yearly_growth_gb is None and bg.yearly_growth_gb is not None:
            rg.yearly_growth_gb = bg.yearly_growth_gb

        # 프로비저닝 IOPS/처리량
        if result.provisioned_iops is None and bedrock.provisioned_iops is not None:
            result.provisioned_iops = bedrock.provisioned_iops
        if result.provisioned_throughput_mbps is None and bedrock.provisioned_throughput_mbps is not None:
            result.provisioned_throughput_mbps = bedrock.provisioned_throughput_mbps

        logger.info("Bedrock 보조 파싱 결과 병합 완료 (직접 파싱 우선)")

    def _find_awr_out_files(self, file_path: str) -> list[str]:
        """AWR .out 파일을 찾습니다."""
        if os.path.isfile(file_path) and file_path.endswith(".out"):
            return [file_path]

        if os.path.isdir(file_path):
            out_files = []
            for entry in sorted(os.listdir(file_path)):
                if entry.endswith(".out"):
                    out_files.append(os.path.join(file_path, entry))
            return out_files

        return []


    def _parse_sysstat_section(self, content: str) -> dict:
        """AWR .out의 SYSSTAT 섹션에서 네트워크 데이터를 파싱합니다.

        여러 스냅샷의 평균값을 반환합니다.
        """
        import re

        # SYSSTAT 섹션 추출
        match = re.search(
            r"~~BEGIN-SYSSTAT~~\s*\n(.*?)~~END-SYSSTAT~~",
            content, re.DOTALL
        )
        if not match:
            return {}

        section = match.group(1)
        lines = section.strip().split("\n")

        # 헤더 행 찾기
        header_line = None
        data_start = 0
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("SNAP_ID") or "network_incoming_mb" in stripped:
                header_line = stripped
                data_start = i + 1
                break

        if not header_line:
            return {}

        # 헤더에서 컬럼 인덱스 찾기
        headers = header_line.split()
        col_map = {h: idx for idx, h in enumerate(headers)}

        incoming_idx = col_map.get("network_incoming_mb")
        outgoing_idx = col_map.get("network_outgoing_mb")

        if incoming_idx is None and outgoing_idx is None:
            return {}

        # 구분선 건너뛰기
        for i in range(data_start, len(lines)):
            if lines[i].strip().startswith("---"):
                data_start = i + 1
                break

        # 데이터 행 파싱
        incoming_vals: list[float] = []
        outgoing_vals: list[float] = []

        for i in range(data_start, len(lines)):
            line = lines[i].strip()
            if not line or line.startswith("~~"):
                break
            cols = line.split()
            if len(cols) <= max(incoming_idx or 0, outgoing_idx or 0):
                continue
            try:
                if incoming_idx is not None:
                    incoming_vals.append(float(cols[incoming_idx]))
                if outgoing_idx is not None:
                    outgoing_vals.append(float(cols[outgoing_idx]))
            except (ValueError, IndexError):
                continue

        result: dict = {}
        if incoming_vals:
            result["network_incoming_mb"] = sum(incoming_vals) / len(incoming_vals)
        if outgoing_vals:
            result["network_outgoing_mb"] = sum(outgoing_vals) / len(outgoing_vals)

        # dur_m은 MAIN-METRICS에서 가져오지만, 기본값 60분 사용
        result["dur_m"] = 60

        return result

    def _parse_main_metrics_section(self, content: str) -> dict:
        """AWR .out의 MAIN-METRICS 섹션에서 redo_mb_s와 dur_m을 파싱합니다.

        여러 스냅샷/인스턴스의 평균값을 반환합니다.
        'end' 컬럼의 날짜+시간 공백 오프셋을 보정합니다.
        """
        import re

        # MAIN-METRICS 섹션 추출
        match = re.search(
            r"~~BEGIN-MAIN-METRICS~~\s*\n(.*?)~~END-MAIN-METRICS~~",
            content, re.DOTALL
        )
        if not match:
            return {}

        section = match.group(1)
        lines = section.strip().split("\n")

        # 헤더 행 찾기
        header_line = None
        data_start = 0
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("snap") or "redo_mb_s" in stripped:
                header_line = stripped
                data_start = i + 1
                break

        if not header_line:
            return {}

        # 헤더에서 컬럼 인덱스 찾기
        headers = header_line.split()
        col_map = {h: idx for idx, h in enumerate(headers)}

        # 'end' 컬럼 위치 (날짜+시간이 2개 토큰으로 분리됨)
        end_header_idx = col_map.get("end")

        redo_idx = col_map.get("redo_mb_s")
        dur_idx = col_map.get("dur_m")

        if redo_idx is None:
            return {}

        def _actual_idx(header_idx: int) -> int:
            """end 컬럼 이후만 +1 오프셋 적용."""
            if end_header_idx is not None and header_idx > end_header_idx:
                return header_idx + 1
            return header_idx

        redo_actual = _actual_idx(redo_idx)
        dur_actual = _actual_idx(dur_idx) if dur_idx is not None else None

        # 구분선 건너뛰기
        for i in range(data_start, len(lines)):
            if lines[i].strip().startswith("---"):
                data_start = i + 1
                break

        # 데이터 행 파싱
        redo_vals: list[float] = []
        dur_vals: list[float] = []

        for i in range(data_start, len(lines)):
            line = lines[i].strip()
            if not line or line.startswith("~~"):
                break
            cols = line.split()
            if len(cols) <= redo_actual:
                continue
            try:
                redo_vals.append(float(cols[redo_actual]))
                if dur_actual is not None and len(cols) > dur_actual:
                    dur_vals.append(float(cols[dur_actual]))
            except (ValueError, IndexError):
                continue

        result: dict = {}
        if redo_vals:
            result["redo_mb_s"] = sum(redo_vals) / len(redo_vals)
        if dur_vals:
            result["dur_m"] = sum(dur_vals) / len(dur_vals)

        return result

    # 타겟 엔진 키워드 → 엔진 코드 매핑
    _TARGET_ENGINE_MAP: dict[str, str] = {
        "aurora postgresql": "aurora-postgresql",
        "aurora postgres": "aurora-postgresql",
        "aurora mysql": "aurora-mysql",
        "rds for postgresql": "postgresql",
        "rds postgresql": "postgresql",
        "rds for mysql": "mysql",
        "rds mysql": "mysql",
        "rds for sql server": "sqlserver-ee",
        "rds sql server": "sqlserver-ee",
        # Oracle SE2 (LI)를 먼저 매칭해야 "rds for oracle"보다 우선 적용됨
        "rds for oracle se2": "oracle-se2",
        "oracle se2": "oracle-se2",
        "rds for oracle ee": "oracle-ee",
        "oracle ee": "oracle-ee",
        "rds for oracle": "oracle-ee",
    }

    def _supplement_from_md_files(
        self, file_path: str, parsed: "ParsedDocumentInfo"
    ) -> None:
        """migration_recommendation.md와 DBCSI MD 리포트에서 직접 파싱합니다.

        Bedrock 호출 없이 추출 가능한 필드:
        - target_engine: 추천 타겟 엔진
        - recommended_instance_by_size: 현재 서버 사양 기반 인스턴스
        - recommended_instance_by_sga: SGA 권장사항 기반 인스턴스
        - avg_cpu_per_s / peak_cpu_per_s: DBCSI 리포트의 CPU/s 메트릭
        """
        # migration_recommendation.md 파싱
        rec_file = self._find_migration_recommendation(file_path)
        if rec_file:
            rec_data = self._parse_migration_recommendation(rec_file)
            # target_engine (직접 파싱 우선)
            if rec_data.get("target_engine") and not parsed.target_engine:
                parsed.target_engine = rec_data["target_engine"]
                logger.info("migration_recommendation.md → target_engine: %s",
                            parsed.target_engine)
            # recommended_instance_by_size (직접 파싱 우선)
            if rec_data.get("recommended_instance_by_size"):
                parsed.recommended_instance_by_size = rec_data["recommended_instance_by_size"]
                logger.info("migration_recommendation.md → recommended_instance_by_size: %s",
                            parsed.recommended_instance_by_size)
            # recommended_instance_by_sga (직접 파싱 우선)
            if rec_data.get("recommended_instance_by_sga"):
                parsed.recommended_instance_by_sga = rec_data["recommended_instance_by_sga"]
                logger.info("migration_recommendation.md → recommended_instance_by_sga: %s",
                            parsed.recommended_instance_by_sga)

        # DBCSI MD 리포트에서 CPU/s 파싱
        dbcsi_files = self._find_dbcsi_files(file_path)
        if dbcsi_files:
            cpu_data = self._parse_dbcsi_cpu_per_s(dbcsi_files)
            m = parsed.awr_metrics
            if cpu_data.get("avg_cpu_per_s") is not None:
                m.avg_cpu_per_s = cpu_data["avg_cpu_per_s"]
                logger.info("DBCSI MD → avg_cpu_per_s: %s", m.avg_cpu_per_s)
            if cpu_data.get("peak_cpu_per_s") is not None:
                m.peak_cpu_per_s = cpu_data["peak_cpu_per_s"]
                logger.info("DBCSI MD → peak_cpu_per_s: %s", m.peak_cpu_per_s)

    def _parse_migration_recommendation(self, rec_file: str) -> dict:
        """migration_recommendation.md에서 타겟 엔진과 인스턴스 추천을 파싱합니다.

        추출 필드:
        - target_engine: '**추천 타겟**: ...' 패턴
        - recommended_instance_by_size: 인스턴스 추천 비교 테이블의 '현재 서버 사양 기반' 컬럼
        - recommended_instance_by_sga: 인스턴스 추천 비교 테이블의 'SGA 권장사항 기반' 컬럼
        """
        import re

        try:
            with open(rec_file, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            logger.warning("migration_recommendation.md 읽기 실패: %s", e)
            return {}

        result: dict = {}

        # 1. 타겟 엔진: "**추천 타겟**: Aurora PostgreSQL" 패턴
        target_match = re.search(
            r"\*\*추천\s*타겟\*\*\s*:\s*(.+)",
            content,
        )
        if target_match:
            target_text = target_match.group(1).strip().lower()
            for keyword, engine_code in self._TARGET_ENGINE_MAP.items():
                if keyword in target_text:
                    result["target_engine"] = engine_code
                    break

        # 2. 인스턴스 추천 비교 테이블 파싱
        # 패턴: | **인스턴스 타입** | db.r6i.8xlarge | db.r6i.4xlarge |
        inst_match = re.search(
            r"\|\s*\*\*인스턴스\s*타입\*\*\s*\|\s*(db\.\S+)\s*\|\s*(db\.\S+)\s*\|",
            content,
        )
        if inst_match:
            result["recommended_instance_by_size"] = inst_match.group(1).strip()
            result["recommended_instance_by_sga"] = inst_match.group(2).strip()

        return result

    def _parse_dbcsi_cpu_per_s(self, dbcsi_files: list[str]) -> dict:
        """DBCSI MD 리포트에서 CPU/s 메트릭을 파싱합니다.

        추출 필드:
        - avg_cpu_per_s: '| 평균 CPU/s | 47.12 |' 패턴
        - peak_cpu_per_s: '| 최대 CPU/s | 52.50 |' 패턴
        """
        import re

        for dbcsi_file in dbcsi_files:
            try:
                with open(dbcsi_file, "r", encoding="utf-8") as f:
                    content = f.read()
            except Exception as e:
                logger.warning("DBCSI MD 파일 읽기 실패: %s - %s", dbcsi_file, e)
                continue

            result: dict = {}

            # 평균 CPU/s
            avg_match = re.search(
                r"\|\s*평균\s*CPU/s\s*\|\s*([\d.]+)\s*\|",
                content,
            )
            if avg_match:
                try:
                    result["avg_cpu_per_s"] = float(avg_match.group(1))
                except ValueError:
                    pass

            # 최대 CPU/s
            peak_match = re.search(
                r"\|\s*최대\s*CPU/s\s*\|\s*([\d.]+)\s*\|",
                content,
            )
            if peak_match:
                try:
                    result["peak_cpu_per_s"] = float(peak_match.group(1))
                except ValueError:
                    pass

            if result:
                logger.info("DBCSI CPU/s 직접 파싱 완료: %s → %s",
                            os.path.basename(dbcsi_file), result)
                return result

        return {}

    def _find_dbcsi_files(self, file_path: str) -> list[str]:
        """입력 경로에서 DBCSI MD 리포트 파일을 찾습니다.

        dbcsi_report.md 또는 dbcsi_awr_report.md 등 dbcsi*.md 패턴.
        """
        candidates: list[str] = []

        if os.path.isdir(file_path):
            search_dir = file_path
        elif os.path.isfile(file_path):
            search_dir = os.path.dirname(file_path)
        else:
            return []

        for entry in sorted(os.listdir(search_dir)):
            if entry.lower().startswith("dbcsi") and entry.lower().endswith(".md"):
                candidates.append(os.path.join(search_dir, entry))

        return candidates

    def _find_migration_recommendation(self, file_path: str) -> str | None:
        """입력 경로에서 migration_recommendation.md 파일을 찾습니다."""
        if os.path.isdir(file_path):
            candidate = os.path.join(file_path, "migration_recommendation.md")
            if os.path.isfile(candidate):
                return candidate
        elif os.path.isfile(file_path):
            # 같은 디렉토리에서 찾기
            parent = os.path.dirname(file_path)
            candidate = os.path.join(parent, "migration_recommendation.md")
            if os.path.isfile(candidate):
                return candidate
        return None

