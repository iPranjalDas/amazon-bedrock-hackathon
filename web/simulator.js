// //PRANJAL DAS
// Sentinel+ Alexa+ Web Simulator Controller (web/simulator.js)
document.addEventListener("DOMContentLoaded", () => {
    const input = document.getElementById("voiceQueryInput");
    const speakBtn = document.getElementById("speakBtn");
    const speechBubble = document.getElementById("speechBubble");
    const latencyMetrics = document.getElementById("latencyMetrics");
    const duckingTag = document.getElementById("duckingTag");
    const canvas = document.getElementById("waveformCanvas");
    const ctx = canvas.getContext("2d");

    // Telemetry Elements
    const metricListeners = document.getElementById("metricListeners");
    const metricZombies = document.getElementById("metricZombies");
    const metricScanned = document.getElementById("metricScanned");
    const metricRisk = document.getElementById("metricRisk");
    const portsTableBody = document.getElementById("portsTableBody");
    const traceFeed = document.getElementById("traceFeed");

    let isSpeaking = false;
    let wavePhase = 0;

    // ==========================================
    // 1. Reactive Waveform Animation (Loop It!)
    // ==========================================
    function drawWaveform() {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.lineWidth = 2;
        ctx.strokeStyle = isSpeaking ? "#ff9900" : "#00d2ff";

        ctx.beginPath();
        const sliceWidth = canvas.width / 60;
        let x = 0;

        for (let i = 0; i < 60; i++) {
            const amplitude = isSpeaking ? 28 : 8;
            const freq = isSpeaking ? 0.2 : 0.08;
            const y = (canvas.height / 2) + Math.sin(i * freq + wavePhase) * amplitude;

            if (i === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
            x += sliceWidth;
        }

        ctx.stroke();
        wavePhase += isSpeaking ? 0.15 : 0.04;
        requestAnimationFrame(drawWaveform);
    }
    drawWaveform();

    // ==========================================
    // 2. Transmit Developer Query to MCP Router
    // ==========================================
    async function transmitQuery(query, confirm = false) {
        if (!query || query.trim() === "") return;

        isSpeaking = true;
        duckingTag.textContent = "APLA DUCKING: 10% (VOICE TRANSMISSION ACTIVE)";
        duckingTag.style.color = "#ff9900";

        const startT = performance.now();
        speechBubble.textContent = "Processing query via Sentinel+ router...";

        try {
            const resp = await fetch("/alexa/converse", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ query: query, confirm: confirm })
            });

            const data = await resp.json();
            const elapsed = Math.round(performance.now() - startT);

            // Update Speech Output
            if (data.route === "fast_path") {
                speechBubble.textContent = `"${data.result.speech_text}"`;
                latencyMetrics.innerHTML = `<span>LATENCY: <b>${data.result.latency_ms} ms</b></span> | <span>ROUTE: <b>FAST PATH</b></span> | <span>CONFIDENCE: <b>${Math.round(data.decision.confidence * 100)}%</b></span>`;
                appendTrace("FAST_ROUTER", "Deterministic Sub-10ms Routing", data.result.speech_text, "inspector");
            } 
            else if (data.route === "destructive_action") {
                speechBubble.textContent = `"${data.speech_text}"`;
                latencyMetrics.innerHTML = `<span>LATENCY: <b>${elapsed} ms</b></span> | <span>ROUTE: <b>2PC GATE</b></span> | <span>STATUS: <b>${data.status}</b></span>`;
                
                if (data.requires_2pc_confirm) {
                    appendTrace("2PC_GATEKEEPER", "Destructive State Mutation Intercepted", `Confirmation required for PID ${data.decision.target_pid}.`, "auditor");
                } else {
                    appendTrace("REMEDIATION", "Executed Process Termination", data.speech_text, "fixer");
                }
            } 
            else {
                // Agentic Loop
                speechBubble.textContent = `"${data.speech_text}"`;
                latencyMetrics.innerHTML = `<span>LATENCY: <b>${elapsed} ms</b></span> | <span>ROUTE: <b>AGENTIC BEDROCK LOOP</b></span> | <span>TRACE: <b>ACTIVE</b></span>`;
                triggerAgenticAuditDemo();
            }
        } catch (err) {
            speechBubble.textContent = `"Error communicating with Sentinel+ MCP server: ${err.message}"`;
            latencyMetrics.innerHTML = `<span>ERROR</span>`;
        } finally {
            setTimeout(() => {
                isSpeaking = false;
                duckingTag.textContent = "APLA DUCKING: 25% AMBIENT HUM";
                duckingTag.style.color = "#ff9900";
            }, 2500);
        }
    }

    // ==========================================
    // 3. Simulated Agentic Audit Trace Demo
    // ==========================================
    async function triggerAgenticAuditDemo() {
        try {
            const resp = await fetch("/mcp/call", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "Authorization": "Bearer sentinel-admin-token-2026"
                },
                body: JSON.stringify({
                    jsonrpc: "2.0",
                    id: 42,
                    method: "tools/call",
                    params: {
                        name: "sentinel_agentic_audit",
                        arguments: {}
                    }
                })
            });
            const resData = await resp.json();
            if (resData.result && resData.result.content) {
                const session = JSON.parse(resData.result.content[0].text);
                session.trace_steps.forEach(step => {
                    const roleClass = step.agent_name.includes("Inspector") ? "inspector" :
                                      step.agent_name.includes("Auditor") ? "auditor" : "fixer";
                    appendTrace(step.agent_name, step.role, step.observation, roleClass);
                });
            }
        } catch (e) {
            console.error("Failed to fetch agentic audit trace:", e);
        }
    }

    function appendTrace(name, role, text, cssClass) {
        const entry = document.createElement("div");
        entry.className = `trace-entry ${cssClass}`;
        entry.innerHTML = `
            <div class="trace-badge">${name} (${role})</div>
            <div class="trace-text">${text}</div>
        `;
        traceFeed.prepend(entry);
    }

    // ==========================================
    // 4. SSE Real-Time Telemetry Stream
    // ==========================================
    function connectSSE() {
        const evtSource = new EventSource("/sse");

        evtSource.onmessage = (e) => {
            try {
                const telemetry = JSON.parse(e.data);
                metricListeners.textContent = telemetry.active_listeners;
                metricZombies.textContent = telemetry.zombies_detected;
                metricRisk.textContent = telemetry.zombies_detected > 0 ? "CRITICAL" : "LOW";
                metricRisk.style.color = telemetry.zombies_detected > 0 ? "#ff3366" : "#00e676";
            } catch (err) {
                console.error("SSE parse error:", err);
            }
        };

        evtSource.onerror = () => {
            document.getElementById("streamStatus").innerHTML = `
                <span class="status-dot" style="background:#ff3366; box-shadow:0 0 8px #ff3366;"></span>
                <span class="status-label" style="color:#ff3366;">OFFLINE (RECONNECTING...)</span>
            `;
        };
    }
    connectSSE();

    // ==========================================
    // 5. Event Listeners & Preset Chips
    // ==========================================
    speakBtn.addEventListener("click", () => {
        transmitQuery(input.value);
    });

    input.addEventListener("keydown", (e) => {
        if (e.key === "Enter") transmitQuery(input.value);
    });

    document.querySelectorAll(".preset-chip").forEach(chip => {
        chip.addEventListener("click", () => {
            const q = chip.getAttribute("data-query");
            input.value = q;
            transmitQuery(q);
        });
    });
});
