# {db_name} AWS RDS 비용 예측 리포트

---

## 리포트 개요

| 항목 | 값 |
|------|-----|
| **데이터베이스 이름** | {db_name} |
| **Oracle 버전** | {oracle_version} |
| **리전** | {aws_region} |
| **리포트 생성일** | {report_date} |
| **분석 기준** | AWR/Statspack 기반 |
| **요금 기준일** | {pricing_date} |

---

## 1. 현재 서버 사양

| 항목 | 값 |
|------|-----|
| CPU 코어 수 | {cpu_cores} |
| 물리 메모리 | {physical_memory} GB |
| 전체 DB 크기 | {db_size} GB |
| 인스턴스 구성 | {instance_config} |

### 성능 메트릭 (AWR 기준)

| 항목 | 평균 | 피크 (P99) |
|------|------|-----------|
| CPU 사용률 | {avg_cpu}% | {peak_cpu}% |
| DB CPU/s | {avg_cpu_per_s} | {peak_cpu_per_s} |
| I/O 부하 | {avg_iops} IOPS | {peak_iops} IOPS |
| 메모리 사용량 | {avg_memory} GB | {peak_memory} GB |

### SGA 분석

| 항목 | 값 |
|------|-----|
| 현재 SGA 크기 | {current_sga} GB |
| 권장 SGA 크기 | {recommended_sga} GB |
| SGA 증가율 | {sga_increase_rate}% |

> **권장 SGA**는 Buffer Pool Advisory 데이터 기반으로 Physical Reads가 더 이상 감소하지 않는 최적 지점을 분석한 결과입니다.

### 스토리지 증가 추이

| 항목 | 값 |
|------|-----|
| 현재 DB 크기 | {db_size} GB |
| 최근 1년 증가량 | {yearly_growth} GB |
| 연간 증가율 | {yearly_growth_rate}% |
| **1년 후 예상 크기** | **{db_size_1y} GB** |
| 2년 후 예상 크기 | {db_size_2y} GB |
| 3년 후 예상 크기 | {db_size_3y} GB |

> **증가율 산정 기준**: AWR 스냅샷의 테이블스페이스 사용량 변화 또는 운영팀 제공 데이터 기반.
> 증가율이 확인되지 않을 경우 업계 평균 15~20%를 기본값으로 적용합니다.

---

## 2. RDS 인스턴스 권장 사양

### 2-1. 현재 서버 사양 매칭 (1:1 대응)

> 현재 온프레미스 서버와 동일한 수준의 리소스를 제공하는 RDS 인스턴스입니다.

| 항목 | r6i | r7i |
|------|-----|-----|
| **인스턴스 타입** | **{spec_r6i_instance}** | **{spec_r7i_instance}** |
| vCPU | {spec_r6i_vcpu} | {spec_r7i_vcpu} |
| 메모리 | {spec_r6i_memory} GB | {spec_r7i_memory} GB |
| 네트워크 대역폭 | {spec_r6i_network} Gbps | {spec_r7i_network} Gbps |
| 프로세서 | 3세대 Intel Xeon | 4세대 Intel Xeon (Sapphire Rapids) |

### 2-2. SGA 기반 최적화 권장 (비용 최적화)

> 권장 SGA({recommended_sga}GB) + 여유율({buffer_rate}%) 기준으로 산정합니다.

| 항목 | r6i | r7i |
|------|-----|-----|
| **인스턴스 타입** | **{sga_r6i_instance}** | **{sga_r7i_instance}** |
| vCPU | {sga_r6i_vcpu} | {sga_r7i_vcpu} |
| 메모리 | {sga_r6i_memory} GB | {sga_r7i_memory} GB |
| 네트워크 대역폭 | {sga_r6i_network} Gbps | {sga_r7i_network} Gbps |
| 프로세서 | 3세대 Intel Xeon | 4세대 Intel Xeon (Sapphire Rapids) |

> 💡 **r7i vs r6i**: r7i는 r6i 대비 약 15~20% 향상된 컴퓨팅 성능을 제공합니다. 동일 사이즈에서 더 높은 처리량이 필요하거나, 한 단계 낮은 사이즈로 비용 절감을 노릴 수 있습니다.

---

## 3. 스토리지 비용

> 인스턴스 비용과 별도로 스토리지 비용이 발생하며, DB 크기에 따라 함께 산정합니다.

### 스토리지 구성

| 항목 | 값 |
|------|-----|
| 스토리지 타입 | {storage_type} |
{storage_config_rows}

### 연도별 스토리지 비용 예측

| 항목 | 현재 (0년차) | 1년차 | 2년차 | 3년차 |
|------|-------------|-------|-------|-------|
| 예상 DB 크기 | {db_size} GB | {db_size_1y} GB | {db_size_2y} GB | {db_size_3y} GB |
| 스토리지 비용 | ${stor_cost_0y}/월 | ${stor_cost_1y}/월 | ${stor_cost_2y}/월 | ${stor_cost_3y}/월 |
{storage_extra_cost_rows}| **월 스토리지 합계** | **${stor_total_0y}/월** | **${stor_total_1y}/월** | **${stor_total_2y}/월** | **${stor_total_3y}/월** |
| **연 스토리지 합계** | **${stor_yearly_0y}** | **${stor_yearly_1y}** | **${stor_yearly_2y}** | **${stor_yearly_3y}** |

> **{storage_type} 요금**: {storage_price_per_gb} ({aws_region} 기준). {storage_pricing_detail}

---

## 4. 네트워크 전송 비용

> AWR 성능 데이터의 I/O 메트릭과 SQL*Net 통계를 기반으로 예상 네트워크 전송량과 비용을 산정합니다.

### AWR 기반 네트워크 트래픽 추정

| 트래픽 유형 | 추정 소스 (AWR) | 일 평균 | 월 예상 (×30) |
|------------|----------------|--------|-------------|
| 클라이언트 ↔ DB (수신) | SQL*Net bytes received from client | {sqlnet_recv_daily} GB/일 | {sqlnet_recv_monthly} GB/월 |
| 클라이언트 ↔ DB (송신) | SQL*Net bytes sent to client | {sqlnet_sent_daily} GB/일 | {sqlnet_sent_monthly} GB/월 |
| DB 간 통신 | SQL*Net bytes received from dblink | {dblink_daily} GB/일 | {dblink_monthly} GB/월 |
| Redo 생성량 | Redo size (복제 트래픽 추정용) | {redo_daily} GB/일 | {redo_monthly} GB/월 |
| **총 네트워크 트래픽** | - | **{net_total_daily} GB/일** | **{net_total_monthly} GB/월** |

### AWS 네트워크 과금 구간

| 트래픽 경로 | 과금 | 비고 |
|------------|------|------|
| 같은 AZ 내 (App ↔ RDS) | **무료** | Private IP 사용 시 |
| Cross-AZ (App ↔ RDS) | **$0.01/GB** (양방향) | Multi-AZ 또는 App이 다른 AZ에 있는 경우 |
| Multi-AZ 복제 (RDS 내부) | **무료** | AWS 관리형 복제 |
| Read Replica (같은 리전, Cross-AZ) | **$0.01/GB** | Redo 기반 복제 트래픽 |
| Read Replica (Cross-Region) | **$0.02/GB** | 리전 간 전송 요금 |
| RDS → 인터넷 (Outbound) | **$0.09/GB** (처음 10TB) | 외부 연동 시 |
| RDS → 같은 리전 AWS 서비스 | **무료** | S3, Lambda 등 |

### 배포 시나리오별 월 네트워크 비용 예측

| 시나리오 | 클라이언트 트래픽 | 복제 트래픽 | **월 네트워크 비용** | **연 네트워크 비용** |
|---------|-----------------|-----------|-------------------|-------------------|
| **Single-AZ (같은 AZ)** | 무료 | - | **$0** | **$0** |
| **Single-AZ (Cross-AZ App)** | ({sqlnet_recv_monthly} + {sqlnet_sent_monthly}) GB × $0.01 × 2 | - | **${net_cost_cross_az}** | **${net_cost_cross_az_yearly}** |
| **Multi-AZ (같은 AZ App)** | 무료 | 무료 (AWS 관리) | **$0** | **$0** |
| **Multi-AZ (Cross-AZ App)** | ({sqlnet_recv_monthly} + {sqlnet_sent_monthly}) GB × $0.01 × 2 | 무료 (AWS 관리) | **${net_cost_maz_cross_az}** | **${net_cost_maz_cross_az_yearly}** |
| **+ Read Replica (Cross-AZ)** | 위와 동일 | {redo_monthly} GB × $0.01 | **${net_cost_rr_cross_az}** | **${net_cost_rr_cross_az_yearly}** |
| **+ Read Replica (Cross-Region)** | 위와 동일 | {redo_monthly} GB × $0.02 | **${net_cost_rr_cross_region}** | **${net_cost_rr_cross_region_yearly}** |

### 연도별 네트워크 비용 예측

> 네트워크 트래픽은 DB 사용량 증가에 비례하여 증가한다고 가정합니다 (스토리지 증가율 {yearly_growth_rate}% 적용).

| 항목 | 현재 (0년차) | 1년차 | 2년차 | 3년차 |
|------|-------------|-------|-------|-------|
| 예상 월 트래픽 | {net_total_monthly} GB | {net_total_monthly_1y} GB | {net_total_monthly_2y} GB | {net_total_monthly_3y} GB |
| 월 비용 (Cross-AZ 기준) | ${net_cost_cross_az} | ${net_cost_cross_az_1y} | ${net_cost_cross_az_2y} | ${net_cost_cross_az_3y} |
| **연 비용 (Cross-AZ 기준)** | **${net_cost_cross_az_yearly}** | **${net_cost_cross_az_yearly_1y}** | **${net_cost_cross_az_yearly_2y}** | **${net_cost_cross_az_yearly_3y}** |

> 💡 **비용 절감 팁**: App과 RDS를 같은 AZ에 배치하면 네트워크 전송 비용을 완전히 제거할 수 있습니다. 단, 가용성 측면에서 단일 AZ 장애 시 영향도를 고려해야 합니다.

---

## 5. 인스턴스 + 스토리지 + 네트워크 통합 비용: 현재 서버 사양 매칭

### 5-1. r6i 계열 ({spec_r6i_instance})

#### Single-AZ

| 요금 옵션 | 인스턴스/월 | 스토리지/월 | 네트워크/월 | **월 합계** | **연 합계** |
|-----------|-----------|-----------|-----------|-----------|-----------|
| **On-Demand** | ${spec_r6i_od_monthly} | ${stor_total_0y} | ${net_monthly} | **${spec_r6i_od_total_monthly}** | **${spec_r6i_od_total_yearly}** |
| **1년 RI (All Upfront)** | ${spec_r6i_ri1au_monthly} | ${stor_total_0y} | ${net_monthly} | **${spec_r6i_ri1au_total_monthly}** | **${spec_r6i_ri1au_total_yearly}** |
| **3년 RI (All Upfront)** | ${spec_r6i_ri3au_monthly} | ${stor_total_0y} | ${net_monthly} | **${spec_r6i_ri3au_total_monthly}** | **${spec_r6i_ri3au_total_yearly}** |

> 네트워크 비용은 {net_scenario} 시나리오 기준입니다. 같은 AZ 배치 시 $0입니다.

#### Multi-AZ

| 요금 옵션 | 인스턴스/월 | 스토리지/월 | 네트워크/월 | **월 합계** | **연 합계** |
|-----------|-----------|-----------|-----------|-----------|-----------|
| **On-Demand** | ${spec_r6i_maz_od_monthly} | ${stor_maz_total_0y} | ${net_maz_monthly} | **${spec_r6i_maz_od_total_monthly}** | **${spec_r6i_maz_od_total_yearly}** |
| **1년 RI (All Upfront)** | ${spec_r6i_maz_ri1au_monthly} | ${stor_maz_total_0y} | ${net_maz_monthly} | **${spec_r6i_maz_ri1au_total_monthly}** | **${spec_r6i_maz_ri1au_total_yearly}** |
| **3년 RI (All Upfront)** | ${spec_r6i_maz_ri3au_monthly} | ${stor_maz_total_0y} | ${net_maz_monthly} | **${spec_r6i_maz_ri3au_total_monthly}** | **${spec_r6i_maz_ri3au_total_yearly}** |

> ⚠️ Multi-AZ: {maz_storage_note}

### 5-2. r7i 계열 ({spec_r7i_instance})

#### Single-AZ

| 요금 옵션 | 인스턴스/월 | 스토리지/월 | 네트워크/월 | **월 합계** | **연 합계** |
|-----------|-----------|-----------|-----------|-----------|-----------|
| **On-Demand** | ${spec_r7i_od_monthly} | ${stor_total_0y} | ${net_monthly} | **${spec_r7i_od_total_monthly}** | **${spec_r7i_od_total_yearly}** |
| **1년 RI (All Upfront)** | ${spec_r7i_ri1au_monthly} | ${stor_total_0y} | ${net_monthly} | **${spec_r7i_ri1au_total_monthly}** | **${spec_r7i_ri1au_total_yearly}** |
| **3년 RI (All Upfront)** | ${spec_r7i_ri3au_monthly} | ${stor_total_0y} | ${net_monthly} | **${spec_r7i_ri3au_total_monthly}** | **${spec_r7i_ri3au_total_yearly}** |

#### Multi-AZ

| 요금 옵션 | 인스턴스/월 | 스토리지/월 | 네트워크/월 | **월 합계** | **연 합계** |
|-----------|-----------|-----------|-----------|-----------|-----------|
| **On-Demand** | ${spec_r7i_maz_od_monthly} | ${stor_maz_total_0y} | ${net_maz_monthly} | **${spec_r7i_maz_od_total_monthly}** | **${spec_r7i_maz_od_total_yearly}** |
| **1년 RI (All Upfront)** | ${spec_r7i_maz_ri1au_monthly} | ${stor_maz_total_0y} | ${net_maz_monthly} | **${spec_r7i_maz_ri1au_total_monthly}** | **${spec_r7i_maz_ri1au_total_yearly}** |
| **3년 RI (All Upfront)** | ${spec_r7i_maz_ri3au_monthly} | ${stor_maz_total_0y} | ${net_maz_monthly} | **${spec_r7i_maz_ri3au_total_monthly}** | **${spec_r7i_maz_ri3au_total_yearly}** |

---

## 6. 인스턴스 + 스토리지 + 네트워크 통합 비용: SGA 기반 최적화

### 6-1. r6i 계열 ({sga_r6i_instance})

#### Single-AZ

| 요금 옵션 | 인스턴스/월 | 스토리지/월 | 네트워크/월 | **월 합계** | **연 합계** |
|-----------|-----------|-----------|-----------|-----------|-----------|
| **On-Demand** | ${sga_r6i_od_monthly} | ${stor_total_0y} | ${net_monthly} | **${sga_r6i_od_total_monthly}** | **${sga_r6i_od_total_yearly}** |
| **1년 RI (All Upfront)** | ${sga_r6i_ri1au_monthly} | ${stor_total_0y} | ${net_monthly} | **${sga_r6i_ri1au_total_monthly}** | **${sga_r6i_ri1au_total_yearly}** |
| **3년 RI (All Upfront)** | ${sga_r6i_ri3au_monthly} | ${stor_total_0y} | ${net_monthly} | **${sga_r6i_ri3au_total_monthly}** | **${sga_r6i_ri3au_total_yearly}** |

#### Multi-AZ

| 요금 옵션 | 인스턴스/월 | 스토리지/월 | 네트워크/월 | **월 합계** | **연 합계** |
|-----------|-----------|-----------|-----------|-----------|-----------|
| **On-Demand** | ${sga_r6i_maz_od_monthly} | ${stor_maz_total_0y} | ${net_maz_monthly} | **${sga_r6i_maz_od_total_monthly}** | **${sga_r6i_maz_od_total_yearly}** |
| **1년 RI (All Upfront)** | ${sga_r6i_maz_ri1au_monthly} | ${stor_maz_total_0y} | ${net_maz_monthly} | **${sga_r6i_maz_ri1au_total_monthly}** | **${sga_r6i_maz_ri1au_total_yearly}** |
| **3년 RI (All Upfront)** | ${sga_r6i_maz_ri3au_monthly} | ${stor_maz_total_0y} | ${net_maz_monthly} | **${sga_r6i_maz_ri3au_total_monthly}** | **${sga_r6i_maz_ri3au_total_yearly}** |

### 6-2. r7i 계열 ({sga_r7i_instance})

#### Single-AZ

| 요금 옵션 | 인스턴스/월 | 스토리지/월 | 네트워크/월 | **월 합계** | **연 합계** |
|-----------|-----------|-----------|-----------|-----------|-----------|
| **On-Demand** | ${sga_r7i_od_monthly} | ${stor_total_0y} | ${net_monthly} | **${sga_r7i_od_total_monthly}** | **${sga_r7i_od_total_yearly}** |
| **1년 RI (All Upfront)** | ${sga_r7i_ri1au_monthly} | ${stor_total_0y} | ${net_monthly} | **${sga_r7i_ri1au_total_monthly}** | **${sga_r7i_ri1au_total_yearly}** |
| **3년 RI (All Upfront)** | ${sga_r7i_ri3au_monthly} | ${stor_total_0y} | ${net_monthly} | **${sga_r7i_ri3au_total_monthly}** | **${sga_r7i_ri3au_total_yearly}** |

#### Multi-AZ

| 요금 옵션 | 인스턴스/월 | 스토리지/월 | 네트워크/월 | **월 합계** | **연 합계** |
|-----------|-----------|-----------|-----------|-----------|-----------|
| **On-Demand** | ${sga_r7i_maz_od_monthly} | ${stor_maz_total_0y} | ${net_maz_monthly} | **${sga_r7i_maz_od_total_monthly}** | **${sga_r7i_maz_od_total_yearly}** |
| **1년 RI (All Upfront)** | ${sga_r7i_maz_ri1au_monthly} | ${stor_maz_total_0y} | ${net_maz_monthly} | **${sga_r7i_maz_ri1au_total_monthly}** | **${sga_r7i_maz_ri1au_total_yearly}** |
| **3년 RI (All Upfront)** | ${sga_r7i_maz_ri3au_monthly} | ${stor_maz_total_0y} | ${net_maz_monthly} | **${sga_r7i_maz_ri3au_total_monthly}** | **${sga_r7i_maz_ri3au_total_yearly}** |

---

## 7. 전체 비용 비교 요약

### 연간 비용 비교 (Single-AZ, 인스턴스 + 스토리지 + 네트워크 합산)

> 모든 금액은 스토리지 비용이 포함된 총 비용입니다.

| 요금 옵션 | 서버 매칭 r6i | 서버 매칭 r7i | SGA 최적화 r6i | SGA 최적화 r7i |
|-----------|-------------|-------------|--------------|--------------|
| | {spec_r6i_instance} | {spec_r7i_instance} | {sga_r6i_instance} | {sga_r7i_instance} |
| **On-Demand** | ${comp_spec_r6i_od} | ${comp_spec_r7i_od} | ${comp_sga_r6i_od} | ${comp_sga_r7i_od} |
| **1년 RI (All Upfront)** | ${comp_spec_r6i_ri1au} | ${comp_spec_r7i_ri1au} | ${comp_sga_r6i_ri1au} | ${comp_sga_r7i_ri1au} |
| **3년 RI (All Upfront)** | ${comp_spec_r6i_ri3au} | ${comp_spec_r7i_ri3au} | ${comp_sga_r6i_ri3au} | ${comp_sga_r7i_ri3au} |

### 3년 TCO 비교 (스토리지 증가분 반영)

> 스토리지 비용은 연도별 증가분({yearly_growth_rate}%/년)이 반영된 누적 합계입니다.

| 시나리오 | 서버 매칭 r6i | 서버 매칭 r7i | SGA 최적화 r6i | SGA 최적화 r7i |
|---------|-------------|-------------|--------------|--------------|
| On-Demand 3년 | ${tco_spec_r6i_od} | ${tco_spec_r7i_od} | ${tco_sga_r6i_od} | ${tco_sga_r7i_od} |
| 1년 RI × 3회 | ${tco_spec_r6i_ri1} | ${tco_spec_r7i_ri1} | ${tco_sga_r6i_ri1} | ${tco_sga_r7i_ri1} |
| 3년 RI 1회 | ${tco_spec_r6i_ri3} | ${tco_spec_r7i_ri3} | ${tco_sga_r6i_ri3} | ${tco_sga_r7i_ri3} |

#### 3년 TCO 비용 구성 상세 (최적 시나리오: SGA 최적화 + 3년 RI)

| 비용 항목 | 1년차 | 2년차 | 3년차 | 3년 합계 |
|----------|-------|-------|-------|---------|
| 인스턴스 비용 (r6i) | ${tco_detail_r6i_inst_1y} | ${tco_detail_r6i_inst_2y} | ${tco_detail_r6i_inst_3y} | ${tco_detail_r6i_inst_total} |
| 스토리지 비용 | ${tco_detail_stor_1y} | ${tco_detail_stor_2y} | ${tco_detail_stor_3y} | ${tco_detail_stor_total} |
| 네트워크 비용 | ${tco_detail_net_1y} | ${tco_detail_net_2y} | ${tco_detail_net_3y} | ${tco_detail_net_total} |
| **연도별 합계 (r6i)** | **${tco_detail_r6i_1y}** | **${tco_detail_r6i_2y}** | **${tco_detail_r6i_3y}** | **${tco_detail_r6i_total}** |
| 인스턴스 비용 (r7i) | ${tco_detail_r7i_inst_1y} | ${tco_detail_r7i_inst_2y} | ${tco_detail_r7i_inst_3y} | ${tco_detail_r7i_inst_total} |
| 스토리지 비용 | ${tco_detail_stor_1y} | ${tco_detail_stor_2y} | ${tco_detail_stor_3y} | ${tco_detail_stor_total} |
| 네트워크 비용 | ${tco_detail_net_1y} | ${tco_detail_net_2y} | ${tco_detail_net_3y} | ${tco_detail_net_total} |
| **연도별 합계 (r7i)** | **${tco_detail_r7i_1y}** | **${tco_detail_r7i_2y}** | **${tco_detail_r7i_3y}** | **${tco_detail_r7i_total}** |

---

## 8. 권장사항

### 비용 최적화 전략

1. **SGA 기반 인스턴스로 시작**: 실제 메모리 사용량 기준 최적화 사이즈로 시작하여 불필요한 비용 방지
2. **r7i 우선 검토**: 동일 사이즈에서 15~20% 향상된 성능 제공, 가격 대비 성능비(price-performance) 우위
3. **부하 테스트 후 사이즈 확정**: POC 기간 동안 On-Demand로 운영하며 적정 사이즈 검증
4. **RI 전환 시점**: 프로덕션 안정화 후 3년 RI(All Upfront) 전환으로 최대 비용 절감
5. **스토리지 모니터링**: 연간 증가율({yearly_growth_rate}%)을 주기적으로 검증하고, 예상보다 빠른 증가 시 용량 계획 조정
6. **네트워크 비용 최소화**: App과 RDS를 같은 AZ에 배치하여 Cross-AZ 전송 비용 제거. Multi-AZ 배포 시에도 Primary와 같은 AZ에 App 배치 권장

### 단계별 접근

| 단계 | 기간 | 요금 모델 | 인스턴스 | 비고 |
|------|------|----------|---------|------|
| POC/테스트 | 1-2개월 | On-Demand | {sga_r7i_instance} | SGA 기반 r7i로 시작 |
| 프로덕션 안정화 | 2-3개월 | On-Demand | 부하 테스트 결과 반영 | 필요 시 스케일 업 |
| 비용 최적화 | 안정화 후 | 3년 RI (All Upfront) | 확정된 인스턴스 | 최대 절감 |

### Multi-AZ 필요성 검토

| 고려 항목 | 설명 |
|----------|------|
| SLA 요구사항 | 99.99% 이상 가용성 필요 시 Multi-AZ 권장 |
| 비용 증가 | 인스턴스 + 스토리지 모두 약 2배 |
| 대안 | Single-AZ + 자동 백업 + Cross-Region Read Replica |

---

## 부록 A: r6i 인스턴스 패밀리

| 인스턴스 타입 | vCPU | 메모리 (GB) | 네트워크 (Gbps) |
|-------------|------|------------|----------------|
| db.r6i.large | 2 | 16 | 12.5 |
| db.r6i.xlarge | 4 | 32 | 12.5 |
| db.r6i.2xlarge | 8 | 64 | 12.5 |
| db.r6i.4xlarge | 16 | 128 | 12.5 |
| db.r6i.8xlarge | 32 | 256 | 12.5 |
| db.r6i.12xlarge | 48 | 384 | 18.75 |
| db.r6i.16xlarge | 64 | 512 | 25.0 |
| db.r6i.24xlarge | 96 | 768 | 37.5 |

> **r6i**: 3세대 Intel Xeon (Ice Lake) 기반 메모리 최적화 인스턴스.

## 부록 B: r7i 인스턴스 패밀리

| 인스턴스 타입 | vCPU | 메모리 (GB) | 네트워크 (Gbps) |
|-------------|------|------------|----------------|
| db.r7i.large | 2 | 16 | 12.5 |
| db.r7i.xlarge | 4 | 32 | 12.5 |
| db.r7i.2xlarge | 8 | 64 | 12.5 |
| db.r7i.4xlarge | 16 | 128 | 12.5 |
| db.r7i.8xlarge | 32 | 256 | 12.5 |
| db.r7i.12xlarge | 48 | 384 | 18.75 |
| db.r7i.16xlarge | 64 | 512 | 25.0 |
| db.r7i.24xlarge | 96 | 768 | 37.5 |

> **r7i**: 4세대 Intel Xeon (Sapphire Rapids) 기반. r6i 대비 약 15~20% 성능 향상.

## 부록 C: gp3 스토리지 요금 기준

| 항목 | 요금 ({aws_region}) |
|------|---------------------|
| 스토리지 | $0.08/GB-월 |
| 추가 IOPS (3,000 초과) | $0.02/IOPS-월 |
| 추가 처리량 (125 MB/s 초과) | $0.04/MB/s-월 |
| 백업 스토리지 (보관 기간 초과분) | $0.095/GB-월 |

## 부록 D: 네트워크 전송 요금 기준

| 트래픽 경로 | 요금 ({aws_region}) |
|------------|---------------------|
| 같은 AZ 내 (Private IP) | 무료 |
| Cross-AZ (양방향) | $0.01/GB |
| 같은 리전 내 AWS 서비스 | 무료 |
| Cross-Region | $0.02/GB |
| 인터넷 Outbound (처음 10TB) | $0.09/GB |
| 인터넷 Outbound (10-50TB) | $0.085/GB |
| 인터넷 Inbound | 무료 |

## 부록 E: 비용 산정 공식

```
월 인스턴스 비용 = 시간당 요금 × 730시간
월 스토리지 비용 = (DB 크기 × $0.08) + (추가 IOPS × $0.02) + (추가 처리량 × $0.04)
N년차 스토리지 = DB 크기 × (1 + 연간증가율)^N × $0.08
월 네트워크 비용 = (SQL*Net sent + received)(GB) × $0.01 × 2 (Cross-AZ 기준)
N년차 네트워크 = 월 네트워크 비용 × (1 + 연간증가율)^N × 12
3년 TCO = Σ(연도별 인스턴스 비용) + Σ(연도별 스토리지 비용) + Σ(연도별 네트워크 비용)
Multi-AZ 비용 = Single-AZ 인스턴스 비용 × 2 + Single-AZ 스토리지 비용 × 2 + 네트워크 비용
```

---

*본 리포트는 AWS 공개 요금 기준으로 작성되었으며, 실제 비용은 사용 패턴, 데이터 전송량, 백업 설정 등에 따라 달라질 수 있습니다.*

*리포트 생성: {report_date} | 리전: {aws_region} | 요금 기준일: {pricing_date}*