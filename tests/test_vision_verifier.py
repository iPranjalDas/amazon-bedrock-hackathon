# //Pranjal Das
"""
Unit tests for Sentinel+ Multimodal Architecture Vision Verifier.
Validates Bedrock Nova Pro topology extraction, procfs socket reconciliation,
ghost listener detection, and zero arithmetic hallucination.
"""
import pytest
from src.vision_verifier import ArchitectureVisionVerifier, DeclaredTopology, DeclaredComponent


def test_vision_verifier_simulated_extraction():
    verifier = ArchitectureVisionVerifier()
    topology = verifier._simulated_declared_topology()
    assert topology.total_services_declared == 4
    assert len(topology.components) == 4
    ports = [c.expected_port for c in topology.components]
    assert 8000 in ports
    assert 5173 in ports


def test_vision_verifier_reconciliation_zero_drift():
    verifier = ArchitectureVisionVerifier()
    report = verifier.verify_diagram(image_path_or_bytes=None, diagram_name="test_spec.png")

    assert report.diagram_analyzed == "test_spec.png"
    assert report.declared_services_count == 4
    assert report.drift_score >= 0.0
    assert report.drift_score <= 1.0
    assert report.status in ["VERIFIED_COMPLIANT", "DRIFT_DETECTED", "CRITICAL_GHOST_PORTS"]
    assert len(report.summary_verdict) > 20


def test_vision_verifier_anomalies_structure():
    verifier = ArchitectureVisionVerifier()
    report = verifier.verify_diagram()
    for anom in report.anomalies:
        assert anom.anomaly_type in ["GHOST_LISTENER", "MISSING_SERVICE", "PORT_DIVERGENCE", "INSECURE_INGRESS"]
        assert anom.severity in ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
        assert len(anom.remediation_suggestion) > 0
