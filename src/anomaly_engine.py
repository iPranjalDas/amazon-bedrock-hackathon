# //Pranjal Das
"""
Real-Time Mathematical Anomaly Predictor (src/anomaly_engine.py)
Author: Pranjal Das //Pranjal Das

Computes real-time Exponentially Weighted Moving Averages (EWMA) and rolling Z-Scores
over process memory RSS and socket churn rates.

Why this matters for Sentinel+:
Conventional sentries only alert after a service has crashed or an OOM killer has fired.
This engine identifies progressive memory leaks (constant positive RSS derivative) and
rapid socket churn BEFORE system failure occurs, projecting an empirical Time-To-Exhaustion (TTE).
"""
import math
import time
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional

# Inject Drive D packages
_REPO_ROOT = Path(__file__).resolve().parent.parent
_PACKAGES = _REPO_ROOT / "packages"
if _PACKAGES.exists() and str(_PACKAGES) not in sys.path:
    sys.path.insert(0, str(_PACKAGES))

try:
    from pydantic import BaseModel, Field
    HAS_PYDANTIC = True
except ImportError:
    HAS_PYDANTIC = False

if HAS_PYDANTIC:
    class MetricSample(BaseModel):
        timestamp: float
        value: float

    class AnomalyFinding(BaseModel):
        metric_name: str
        target_pid: Optional[int]
        current_value: float
        ewma_value: float
        z_score: float
        trend_slope_per_min: float
        is_anomalous: bool
        severity: str  # "LOW", "MEDIUM", "HIGH", "CRITICAL"
        time_to_exhaustion_min: Optional[float] = None
        remediation_suggestion: str

    class AnomalyReport(BaseModel):
        timestamp: float
        total_metrics_evaluated: int
        anomalies_detected: int
        highest_severity: str
        findings: List[AnomalyFinding]
        voice_summary: str
else:
    class MetricSample:
        def __init__(self, timestamp, value):
            self.timestamp = timestamp
            self.value = value
        def model_dump(self):
            return self.__dict__

    class AnomalyFinding:
        def __init__(self, metric_name, target_pid, current_value, ewma_value,
                     z_score, trend_slope_per_min, is_anomalous, severity,
                     time_to_exhaustion_min, remediation_suggestion):
            self.metric_name = metric_name
            self.target_pid = target_pid
            self.current_value = current_value
            self.ewma_value = ewma_value
            self.z_score = z_score
            self.trend_slope_per_min = trend_slope_per_min
            self.is_anomalous = is_anomalous
            self.severity = severity
            self.time_to_exhaustion_min = time_to_exhaustion_min
            self.remediation_suggestion = remediation_suggestion
        def model_dump(self):
            return self.__dict__

    class AnomalyReport:
        def __init__(self, timestamp, total_metrics_evaluated, anomalies_detected,
                     highest_severity, findings, voice_summary):
            self.timestamp = timestamp
            self.total_metrics_evaluated = total_metrics_evaluated
            self.anomalies_detected = anomalies_detected
            self.highest_severity = highest_severity
            self.findings = findings
            self.voice_summary = voice_summary
        def model_dump(self):
            return {
                "timestamp": self.timestamp,
                "total_metrics_evaluated": self.total_metrics_evaluated,
                "anomalies_detected": self.anomalies_detected,
                "highest_severity": self.highest_severity,
                "findings": [f.model_dump() for f in self.findings],
                "voice_summary": self.voice_summary
            }


class RollingMetricSeries:
    """
    Sliding window time-series accumulator with EWMA and variance smoothing.
    Configured with alpha=0.3 to balance trend responsiveness against sensor noise.
    """
    def __init__(self, max_samples: int = 60, alpha: float = 0.3):
        self.max_samples = max_samples
        self.alpha = alpha
        self.samples: List[MetricSample] = []
        self._ewma: Optional[float] = None

    def add_sample(self, val: float, timestamp: Optional[float] = None) -> None:
        ts = timestamp if timestamp is not None else time.time()
        self.samples.append(MetricSample(timestamp=ts, value=val))
        if len(self.samples) > self.max_samples:
            self.samples.pop(0)

        # Update Exponentially Weighted Moving Average
        if self._ewma is None:
            self._ewma = val
        else:
            self._ewma = (self.alpha * val) + ((1.0 - self.alpha) * self._ewma)

    @property
    def ewma(self) -> float:
        return self._ewma if self._ewma is not None else 0.0

    def compute_z_score(self, current_val: float) -> float:
        """Computes current deviation relative to the rolling sample standard deviation."""
        if len(self.samples) < 3:
            return 0.0
        vals = [s.value for s in self.samples]
        mean = sum(vals) / len(vals)
        variance = sum((x - mean) ** 2 for x in vals) / len(vals)
        std_dev = math.sqrt(variance)
        if std_dev < 1e-4:
            return 0.0
        return round((current_val - mean) / std_dev, 2)

    def compute_linear_slope_per_min(self) -> float:
        """
        Computes least-squares linear regression slope normalized to units per minute.
        Positive slope indicates continuous consumption or connection accumulation.
        """
        if len(self.samples) < 2:
            return 0.0
        t0 = self.samples[0].timestamp
        xs = [s.timestamp - t0 for s in self.samples]
        ys = [s.value for s in self.samples]

        n = len(xs)
        mean_x = sum(xs) / n
        mean_y = sum(ys) / n

        denom = sum((x - mean_x) ** 2 for x in xs)
        if denom < 1e-4:
            return 0.0
        numer = sum((xs[i] - mean_x) * (ys[i] - mean_y) for i in range(n))
        slope_per_sec = numer / denom
        return round(slope_per_sec * 60.0, 2)


# In-memory metric series registry indexed by (metric_name, pid)
_METRIC_STORE: Dict[str, RollingMetricSeries] = {}

def get_or_create_series(metric_key: str) -> RollingMetricSeries:
    if metric_key not in _METRIC_STORE:
        _METRIC_STORE[metric_key] = RollingMetricSeries()
    return _METRIC_STORE[metric_key]


def evaluate_system_anomalies(
    active_process_pids: Optional[List[int]] = None,
    available_memory_mb: float = 1024.0
) -> AnomalyReport:
    """
    Evaluates running dev services against rolling baseline statistical thresholds.
    Detects memory leaks and socket churn before processes terminate abruptly.
    """
    from src.socket_sentry import get_process_memory_mb, audit_local_sockets
    
    if active_process_pids is None:
        # Auto-discover from active socket findings
        report = audit_local_sockets()
        active_process_pids = [f.pid for f in report.findings if f.pid > 0]

    # Periodic cleanup: Prune dead PIDs from metric registry to prevent unbounded memory growth
    dead_keys = [k for k in list(_METRIC_STORE.keys()) if k.startswith("proc_rss_pid_") and not os.path.exists(f"/proc/{k.split('_')[-1]}")]
    for k in dead_keys:
        _METRIC_STORE.pop(k, None)

    findings: List[AnomalyFinding] = []
    anomalies_detected = 0
    highest_severity = "LOW"

    for pid in active_process_pids:
        rss_mb = get_process_memory_mb(pid)
        series_key = f"proc_rss_pid_{pid}"
        series = get_or_create_series(series_key)
        series.add_sample(rss_mb)

        z_score = series.compute_z_score(rss_mb)
        slope_min = series.compute_linear_slope_per_min()

        # If slope is positive and z_score > 2.0, flag as progressive memory leak
        is_leak = slope_min > 2.0 and z_score >= 1.8
        tte = None
        if is_leak and slope_min > 0.1:
            headroom_mb = max(10.0, available_memory_mb - rss_mb)
            tte = round(headroom_mb / slope_min, 1)

        severity = "LOW"
        if is_leak:
            anomalies_detected += 1
            if tte and tte < 15.0:
                severity = "CRITICAL"
                highest_severity = "CRITICAL"
            elif tte and tte < 60.0:
                severity = "HIGH"
                if highest_severity != "CRITICAL":
                    highest_severity = "HIGH"
            else:
                severity = "MEDIUM"
                if highest_severity not in ["CRITICAL", "HIGH"]:
                    highest_severity = "MEDIUM"

            suggestion = (
                f"Progressive memory ramp detected (+{slope_min} MB/min). "
                f"Inspect unclosed database pools or event listener leaks in PID {pid}."
            )
        else:
            suggestion = "Memory baseline operating within statistical tolerances."

        findings.append(AnomalyFinding(
            metric_name="memory_rss_mb",
            target_pid=pid,
            current_value=rss_mb,
            ewma_value=round(series.ewma, 2),
            z_score=z_score,
            trend_slope_per_min=slope_min,
            is_anomalous=is_leak,
            severity=severity,
            time_to_exhaustion_min=tte,
            remediation_suggestion=suggestion
        ))

    # Compose natural spoken voice summary for Alexa+
    if anomalies_detected > 0:
        worst = next((f for f in findings if f.is_anomalous), None)
        voice_summary = (
            f"Preemptive Sentry Alert: Detected {anomalies_detected} memory anomaly. "
            f"PID {worst.target_pid} is climbing at {worst.trend_slope_per_min} MB per minute. "
            f"Estimated exhaustion in {worst.time_to_exhaustion_min or 'unknown'} minutes."
        )
    else:
        voice_summary = "All monitored dev services are operating within normal statistical limits."

    return AnomalyReport(
        timestamp=time.time(),
        total_metrics_evaluated=len(findings),
        anomalies_detected=anomalies_detected,
        highest_severity=highest_severity,
        findings=findings,
        voice_summary=voice_summary
    )
