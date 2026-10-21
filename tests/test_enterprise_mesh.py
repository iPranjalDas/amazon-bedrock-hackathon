# //Pranjal Das
"""
Unit Tests for Sentinel+ Enterprise 2.0 Resilience Mesh
Author: Pranjal Das //Pranjal Das

Tests:
1. eBPF TCP Finite State Machine & Hex Address Decoding
2. cgroups v2 Memory Pressure Metrics
3. EWMA & Rolling Z-Score Anomaly Predictor
4. Bedrock TokenBucket Rate Limiter & Circuit Breaker
5. Distributed Fleet Manager (Local, Staging ECS, Production EKS)
6. Enterprise Dual-Path Router Integration
"""
import sys
import time
from pathlib import Path

# Inject Drive D packages
_REPO_ROOT = Path(__file__).resolve().parent.parent
_PACKAGES = _REPO_ROOT / "packages"
if _PACKAGES.exists() and str(_PACKAGES) not in sys.path:
    sys.path.insert(0, str(_PACKAGES))

from src.ebpf_sentry import (
    _hex_to_ip_port,
    parse_proc_net_tcp,
    read_cgroup_memory_pressure,
    audit_ebpf_socket_lifecycle,
    TCP_STATE_MAP
)
from src.anomaly_engine import (
    RollingMetricSeries,
    evaluate_system_anomalies
)
from src.bedrock_mesh import (
    TokenBucketLimiter,
    CircuitBreaker,
    BedrockResiliencyMesh
)
from src.cluster_manager import DistributedFleetManager
from src.router import route_and_execute, classify_intent_deterministic


def test_ebpf_tcp_hex_conversion():
    # 0100007F is 127.0.0.1 in little-endian, 1F90 is 8080 hex
    ip, port = _hex_to_ip_port("0100007F:1F90")
    assert ip == "127.0.0.1"
    assert port == 8080

    # 00000000:0050 is 0.0.0.0:80
    ip2, port2 = _hex_to_ip_port("00000000:0050")
    assert ip2 == "0.0.0.0"
    assert port2 == 80

    # Malformed falls back gracefully
    bad_ip, bad_port = _hex_to_ip_port("invalid")
    assert bad_ip == "0.0.0.0"
    assert bad_port == 0


def test_ebpf_socket_lifecycle_audit():
    report = audit_ebpf_socket_lifecycle(target_ports=[3000, 8000, 8080])
    assert report.total_sockets_scanned >= 0
    assert isinstance(report.state_distribution, dict)
    assert report.cgroup_metrics.current_bytes > 0
    assert report.cgroup_metrics.usage_percent >= 0.0
    assert report.cgroup_metrics.memory_pressure_risk in ["NOMINAL", "ELEVATED", "CRITICAL"]


def test_anomaly_engine_ewma_and_zscore():
    series = RollingMetricSeries(max_samples=20, alpha=0.3)
    # Feed 10 steady baseline values
    for _ in range(10):
        series.add_sample(100.0)

    assert round(series.ewma, 1) == 100.0
    assert series.compute_z_score(100.0) == 0.0

    # Spike to 180.0
    spike_z = series.compute_z_score(180.0)
    # Variance of identical array is 0, but once we add distinct values variance appears
    series.add_sample(105.0)
    series.add_sample(110.0)
    series.add_sample(150.0)
    z_final = series.compute_z_score(180.0)
    assert z_final > 1.0


def test_anomaly_linear_slope_calculation():
    series = RollingMetricSeries(max_samples=10)
    t0 = 1000.0
    # Simulate a process whose memory grows by 5 MB every 10 seconds (+30 MB/min)
    for i in range(5):
        series.add_sample(val=100.0 + (i * 5.0), timestamp=t0 + (i * 10.0))

    slope_per_min = series.compute_linear_slope_per_min()
    assert slope_per_min == 30.0


def test_bedrock_token_bucket_limiter():
    limiter = TokenBucketLimiter(capacity=2, refill_rate_per_sec=0.01)
    assert limiter.consume(1.0) is True
    assert limiter.consume(1.0) is True
    # 3rd token immediately exhausted
    assert limiter.consume(1.0) is False


def test_bedrock_circuit_breaker_tripping():
    cb = CircuitBreaker(failure_threshold=3, cooldown_sec=10.0)
    assert cb.state == "CLOSED"
    assert cb.allow_request() is True

    cb.record_failure()
    cb.record_failure()
    assert cb.state == "CLOSED"

    # 3rd failure trips breaker
    cb.record_failure()
    assert cb.state == "OPEN"
    assert cb.allow_request() is False


def test_bedrock_resiliency_mesh_dispatch():
    mesh = BedrockResiliencyMesh()
    res = mesh.dispatch_inference("audit local port status")
    assert res.status in ["SUCCESS", "LOCAL_FALLBACK"]
    assert res.latency_ms >= 0.0
    assert len(res.payload_response) > 0


def test_cluster_fleet_manager():
    # Staging ECS
    staging = DistributedFleetManager.get_cluster_topology("staging-ecs")
    assert staging.cluster_name == "staging-ecs"
    assert staging.provider == "aws_ecs"
    assert len(staging.nodes) == 2

    # Production EKS
    prod = DistributedFleetManager.get_cluster_topology("production-k8s")
    assert prod.cluster_name == "production-k8s"
    assert prod.provider == "aws_eks"
    assert len(prod.nodes) == 3

    # Entire Fleet Audit
    fleet = DistributedFleetManager.audit_entire_fleet()
    assert fleet.total_clusters == 3
    assert "Fleet audit complete" in fleet.spoken_summary


def test_router_enterprise_routes():
    # 1. eBPF routing
    dec1 = classify_intent_deterministic("run ebpf socket state audit")
    assert dec1.route == "fast_path"
    assert dec1.intent_category == "ebpf_trace"

    res1 = route_and_execute("run ebpf socket state audit")
    assert res1["route"] == "fast_path"
    assert "eBPF Kernel Audit" in res1["result"]["speech_text"]

    # 2. Anomaly prediction routing
    dec2 = classify_intent_deterministic("predict memory leak and socket anomalies")
    assert dec2.route == "fast_path"
    assert dec2.intent_category == "anomaly_prediction"

    res2 = route_and_execute("predict memory leak anomaly")
    assert res2["route"] == "fast_path"
    assert res2["result"]["latency_ms"] < 100.0

    # 3. Cluster fleet routing
    dec3 = classify_intent_deterministic("audit the production kubernetes cluster")
    assert dec3.route == "fast_path"
    assert dec3.intent_category == "cluster_fleet"

    res3 = route_and_execute("audit the production kubernetes cluster")
    assert res3["route"] == "fast_path"
    assert "Production Kubernetes" in res3["result"]["speech_text"]
