// //Pranjal Das
/**
 * Sentinel+ Web Simulator Controller (web/simulator.js)
 * Author: Pranjal Das //Pranjal Das
 * 
 * Drives the interactive MANUS bento voice & diagnostics console:
 * - High-DPI 3-Wave multi-harmonic audio visualizer with Hann window envelope.
 * - Native Web Speech API (Microphone) voice ingress.
 * - Sub-10ms dispatch to the local FastAPI MCP server.
 * - Dynamic 2PC Confirmation cards for destructive operations.
 * - Live Server-Sent Events (SSE) telemetry feed populating the active ports table.
 * - Tabbed workspace controller (AegisAgent Triad, Staged PR Diff, Amazon RFC).
 */
document.addEventListener("DOMContentLoaded", () => {
    const input = document.getElementById("voiceQueryInput");
    const speakBtn = document.getElementById("speakBtn");
    const micBtn = document.getElementById("micBtn");
    const liveSpeechStream = document.getElementById("liveSpeechStream");
    const chatHistory = document.getElementById("chatHistory");
    const latencyMetrics = document.getElementById("latencyMetrics");
    const duckingTag = document.getElementById("duckingTag");
    const canvas = document.getElementById("waveformCanvas");

    // Telemetry Elements
    const metricListeners = document.getElementById("metricListeners");
    const metricZombies = document.getElementById("metricZombies");
    const metricScanned = document.getElementById("metricScanned");
    const metricRisk = document.getElementById("metricRisk");
    const portsTableBody = document.getElementById("portsTableBody");
    const traceFeed = document.getElementById("traceFeed");
    const prTitle = document.getElementById("prTitle");
    const prBranch = document.getElementById("prBranch");
    const prDiffContent = document.getElementById("prDiffContent");
    const visionBadge = document.getElementById("visionBadge");
    const visionCardBody = document.getElementById("visionCardBody");

    let isSpeaking = false;
    let inFlightTimer = null;
    let pending2PC = null;

    // -------------------------------------------------------------
    // 1. High-DPI Multi-Harmonic Audio Waveform Visualizer
    // -------------------------------------------------------------
    const ctx = canvas.getContext("2d");
    let wavePhase = 0;

    function resizeCanvas() {
        const dpr = window.devicePixelRatio || 1;
        const rect = canvas.getBoundingClientRect();
        canvas.width = rect.width * dpr;
        canvas.height = rect.height * dpr;
        ctx.scale(dpr, dpr);
    }
    window.addEventListener("resize", resizeCanvas);
    resizeCanvas();

    function drawWaveform() {
        const rect = canvas.getBoundingClientRect();
        const width = rect.width;
        const height = rect.height;
        ctx.clearRect(0, 0, width, height);

        const centerY = height / 2;
        const waveCount = isSpeaking ? 3 : 2;

        for (let w = 0; w < waveCount; w++) {
            ctx.beginPath();
            const freq = isSpeaking ? 0.024 * (w + 1) : 0.015;
            const amp = isSpeaking ? (26 - w * 6) : (6 - w * 2);
            const currentPhase = wavePhase * (1 + w * 0.35);

            // Luxury Light Palette: Royal Indigo & Sky Azure (idle) -> Imperial Champagne Gold & Amber (speaking)
            const strokeColor = isSpeaking
                ? (w === 0 ? "rgba(180, 83, 9, 0.95)" : (w === 1 ? "rgba(217, 119, 6, 0.65)" : "rgba(245, 158, 11, 0.35)"))
                : (w === 0 ? "rgba(67, 56, 202, 0.9)" : "rgba(2, 132, 199, 0.45)");

            ctx.lineWidth = w === 0 ? 2.5 : 1.2;
            ctx.strokeStyle = strokeColor;

            const step = 4;
            for (let x = 0; x <= width; x += step) {
                // Hann Window Envelope: Tapers smoothly to zero at boundaries
                const normX = x / width;
                const envelope = Math.sin(normX * Math.PI);
                const y = centerY + Math.sin(x * freq + currentPhase) * amp * envelope;

                if (x === 0) ctx.moveTo(x, y);
                else ctx.lineTo(x, y);
            }
            ctx.stroke();
        }

        wavePhase += isSpeaking ? 0.14 : 0.035;
        requestAnimationFrame(drawWaveform);
    }
    drawWaveform();

    // -------------------------------------------------------------
    // 2. Chat Transcript & Live Voice Helper
    // -------------------------------------------------------------
    function appendChatMessage(text, modelTag, isUser = false) {
        if (!chatHistory) return;
        const msgDiv = document.createElement("div");
        msgDiv.className = `chat-msg ${isUser ? "user-msg" : "assistant-msg"}`;
        const timeStr = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
        const cleanText = String(text).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

        msgDiv.innerHTML = `
            <div class="msg-meta">
                <span class="agent-tag">${modelTag}</span>
                <span class="time-tag">${timeStr}</span>
            </div>
            <div class="msg-body">${isUser ? cleanText : `"${cleanText}"`}</div>
        `;
        chatHistory.appendChild(msgDiv);
        chatHistory.scrollTop = chatHistory.scrollHeight;
    }

    function startInFlightTimer() {
        const t0 = performance.now();
        clearInterval(inFlightTimer);
        inFlightTimer = setInterval(() => {
            const elapsed = Math.round(performance.now() - t0);
            if (latencyMetrics) {
                latencyMetrics.innerHTML = `<span>IN-FLIGHT: <b style="color:#ff9900;">${elapsed} ms</b></span> | <span>ROUTE: <b>ROUTING...</b></span> | <span>MODEL: <b>AMAZON NOVA PRO</b></span>`;
            }
        }, 20);
        return () => {
            clearInterval(inFlightTimer);
            return Math.round(performance.now() - t0);
        };
    }

    // -------------------------------------------------------------
    // 3. Interactive 2PC Confirmation Gate
    // -------------------------------------------------------------
    function render2PCConfirmation(targetText, rawQuery) {
        pending2PC = { rawQuery };
        const card = document.createElement("div");
        card.className = "confirm-action-card";
        card.innerHTML = `
            <span>⚠️ Safety Check: Confirm termination of ${targetText}?</span>
            <div style="display:flex; gap:6px;">
                <button class="btn-confirm-kill" id="btn2PCConfirm">Confirm (SIGTERM)</button>
                <button class="btn-cancel-kill" id="btn2PCCancel">Cancel</button>
            </div>
        `;
        chatHistory.appendChild(card);
        chatHistory.scrollTop = chatHistory.scrollHeight;

        document.getElementById("btn2PCConfirm").onclick = () => {
            card.remove();
            transmitQuery(rawQuery, true);
            pending2PC = null;
        };

        document.getElementById("btn2PCCancel").onclick = () => {
            card.remove();
            appendChatMessage("Action cancelled by developer. Zero system state altered.", "🛡️ 2PC Safety Gate");
            if (liveSpeechStream) liveSpeechStream.textContent = '"Action cancelled. Safe state preserved."';
            pending2PC = null;
        };
    }

    // -------------------------------------------------------------
    // 4. Dispatch Developer Query to Backend Router
    // -------------------------------------------------------------
    async function transmitQuery(query, confirm = false) {
        if (!query || query.trim() === "") return;

        appendChatMessage(query, "Developer", true);
        if (input) input.value = "";

        isSpeaking = true;
        duckingTag.textContent = "APLA DUCKING: 10% (SPEECH ACTIVE)";
        duckingTag.style.color = "#ff9900";

        const stopInFlightTimer = startInFlightTimer();
        if (liveSpeechStream) liveSpeechStream.textContent = "Routing query via Sentinel+ deterministic router...";

        try {
            const resp = await fetch("/alexa/converse", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ query: query, confirm: confirm })
            });

            const data = await resp.json();
            const elapsed = stopInFlightTimer();

            // Route 1: Fast Path (Procfs / Kernel sensor)
            if (data.route === "fast_path") {
                const speech = data.result.speech_text;
                appendChatMessage(speech, "⚡ Fast Path (Procfs)");
                if (liveSpeechStream) liveSpeechStream.textContent = `"${speech}"`;
                latencyMetrics.innerHTML = `<span>LATENCY: <b>${data.result.latency_ms} ms</b></span> | <span>ROUTE: <b>FAST PATH</b></span> | <span>MODEL: <b>NOVA PRO</b></span>`;
                appendTrace("FAST_ROUTER", "Deterministic Sub-10ms procfs", speech, "inspector");

                // Check if multimodal diagram report was returned
                if (data.decision.intent_category === "verify_diagram" && data.result.data) {
                    const rep = data.result.data;
                    visionBadge.textContent = rep.status;
                    visionBadge.style.color = rep.status === "VERIFIED_COMPLIANT" ? "#00e676" : "#ff9900";
                    visionCardBody.innerHTML = `<b>Status:</b> ${rep.status} | <b>Drift Score:</b> ${rep.drift_score}<br><b>Declared:</b> ${rep.declared_services_count} services | <b>Active:</b> ${rep.live_listeners_count} sockets.<br>${rep.summary_verdict}`;
                }

                // Check if PR diff was generated
                if (data.decision.intent_category === "generate_pr" && data.result.data) {
                    const pr = data.result.data;
                    switchTab("tabDiff");
                    prTitle.textContent = pr.pr_title;
                    prBranch.textContent = pr.branch_name;
                    prDiffContent.textContent = pr.unified_diff;
                }

                // Check if Friction Log was requested
                if (data.decision.intent_category === "friction_log" && data.result.data) {
                    switchTab("tabRfc");
                }
            }
            // Route 2: Destructive Operation Intercepted by 2PC
            else if (data.route === "destructive_action") {
                if (data.requires_2pc_confirm) {
                    appendChatMessage(data.speech_text, "🛡️ Two-Phase Commit Gate");
                    if (liveSpeechStream) liveSpeechStream.textContent = `"${data.speech_text}"`;
                    latencyMetrics.innerHTML = `<span>LATENCY: <b>${elapsed} ms</b></span> | <span>ROUTE: <b>2PC GATE</b></span> | <span>STATUS: <b>CONFIRMATION REQUIRED</b></span>`;
                    appendTrace("2PC_GATEKEEPER", "Destructive Mutation Intercepted", data.speech_text, "auditor");

                    const targetLabel = data.decision.target_pid ? `PID ${data.decision.target_pid}` : `port ${data.decision.target_port}`;
                    render2PCConfirmation(targetLabel, query);
                } else {
                    appendChatMessage(data.speech_text, "🛡️ 2PC Remediation Executed");
                    if (liveSpeechStream) liveSpeechStream.textContent = `"${data.speech_text}"`;
                    latencyMetrics.innerHTML = `<span>LATENCY: <b>${elapsed} ms</b></span> | <span>ROUTE: <b>2PC EXECUTED</b></span> | <span>STATUS: <b>${data.status}</b></span>`;
                    appendTrace("REMEDIATION", "Executed Process Termination", data.speech_text, "fixer");
                }
            }
            // Route 3: Conversational Amazon Bedrock / Nova Pro
            else if (data.route === "conversational_bedrock") {
                appendChatMessage(data.speech_text, "🧠 Amazon Nova Pro (Bedrock)");
                if (liveSpeechStream) liveSpeechStream.textContent = `"${data.speech_text}"`;
                latencyMetrics.innerHTML = `<span>LATENCY: <b>${data.latency_ms} ms</b></span> | <span>ROUTE: <b>CONVERSATIONAL BEDROCK</b></span> | <span>MODEL: <b>NOVA PRO</b></span>`;
                appendTrace("NOVA_PRO", "Conversational Intelligence", data.speech_text, "inspector");
            }
            // Route 4: Deep Multi-Agent Audit
            else {
                appendChatMessage(data.speech_text || "Engaged multi-agent audit pipeline.", "🤖 AegisAgent Multi-Agent Loop");
                if (liveSpeechStream) liveSpeechStream.textContent = `"${data.speech_text || 'Audit completed.'}"`;
                latencyMetrics.innerHTML = `<span>LATENCY: <b>${elapsed} ms</b></span> | <span>ROUTE: <b>AGENTIC AUDIT</b></span> | <span>MODEL: <b>NOVA PRO</b></span>`;
                triggerAgenticAuditDemo();
            }
        } catch (err) {
            stopInFlightTimer();
            appendChatMessage(`Error communicating with Sentinel+ server: ${err.message}`, "System Error");
            if (liveSpeechStream) liveSpeechStream.textContent = `"Connection error: ${err.message}"`;
            latencyMetrics.innerHTML = `<span>ERROR</span>`;
        } finally {
            setTimeout(() => {
                isSpeaking = false;
                duckingTag.textContent = "APLA DUCKING: 25% AMBIENT HUM";
                duckingTag.style.color = "#ff9900";
            }, 2500);
        }
    }

    // Expose transmitQuery globally for table action buttons and mini bento cards
    window.transmitQuery = transmitQuery;

    // -------------------------------------------------------------
    // 5. Native Web Speech API (Microphone) Ingress
    // -------------------------------------------------------------
    let recognition = null;
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

    if (SpeechRecognition) {
        recognition = new SpeechRecognition();
        recognition.continuous = false;
        recognition.interimResults = false;
        recognition.lang = "en-US";

        recognition.onstart = () => {
            micBtn.classList.add("recording");
            micBtn.querySelector(".mic-label").textContent = "Listening...";
        };

        recognition.onresult = (event) => {
            const transcript = event.results[0][0].transcript;
            if (input) input.value = transcript;
            transmitQuery(transcript);
        };

        recognition.onerror = (e) => {
            console.warn("Speech recognition error:", e.error);
            micBtn.classList.remove("recording");
            micBtn.querySelector(".mic-label").textContent = "Mic";
        };

        recognition.onend = () => {
            micBtn.classList.remove("recording");
            micBtn.querySelector(".mic-label").textContent = "Mic";
        };

        micBtn.addEventListener("click", () => {
            if (micBtn.classList.contains("recording")) {
                recognition.stop();
            } else {
                try {
                    recognition.start();
                } catch (e) {
                    console.error("Mic start failed:", e);
                }
            }
        });
    } else {
        if (micBtn) {
            micBtn.title = "Web Speech API not supported in this browser. Use keyboard input.";
            micBtn.style.opacity = "0.5";
        }
    }

    // -------------------------------------------------------------
    // 6. Dynamic Ports Table Renderer
    // -------------------------------------------------------------
    function updatePortsTable(findings) {
        if (!portsTableBody) return;
        if (!findings || findings.length === 0) {
            portsTableBody.innerHTML = `<tr><td colspan="6" class="empty-state">No socket leaks detected. All target ports clean.</td></tr>`;
            return;
        }

        portsTableBody.innerHTML = findings.map(f => {
            const isZombie = f.is_stale_zombie;
            const stateClass = isZombie ? "badge-zombie" : "badge-listen";
            const stateLabel = isZombie ? "ZOMBIE" : (f.state || "LISTEN");
            const memLabel = f.memory_rss_mb > 0 ? `${f.memory_rss_mb} MB` : "-";
            const killBtn = f.pid > 1
                ? `<button class="btn-table-kill" onclick="window.transmitQuery('kill PID ${f.pid}', false)">Terminate</button>`
                : "-";

            return `
                <tr>
                    <td><b>:${f.port}</b></td>
                    <td>${f.process_name || 'unknown'}</td>
                    <td><code>${f.pid > 0 ? f.pid : '-'}</code></td>
                    <td><span class="badge-state ${stateClass}">${stateLabel}</span></td>
                    <td>${memLabel}</td>
                    <td>${killBtn}</td>
                </tr>
            `;
        }).join("");
    }

    // -------------------------------------------------------------
    // 7. Tabbed Workspace Controller (AegisAgent, PR Diff, RFC)
    // -------------------------------------------------------------
    const tabButtons = document.querySelectorAll(".tab-btn");
    function switchTab(targetTabId) {
        tabButtons.forEach(btn => {
            if (btn.getAttribute("data-tab") === targetTabId) {
                btn.classList.add("active");
            } else {
                btn.classList.remove("active");
            }
        });
        document.querySelectorAll(".tab-content").forEach(content => {
            if (content.id === targetTabId) {
                content.classList.add("active");
            } else {
                content.classList.remove("active");
            }
        });
    }

    tabButtons.forEach(btn => {
        btn.addEventListener("click", () => {
            switchTab(btn.getAttribute("data-tab"));
        });
    });

    // -------------------------------------------------------------
    // 8. Multi-Agent Audit Trigger & PR Stager
    // -------------------------------------------------------------
    async function triggerAgenticAuditDemo() {
        switchTab("tabTrace");
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
                if (session.trace_steps) {
                    session.trace_steps.forEach(step => {
                        const roleClass = step.agent_name.includes("Inspector") ? "inspector" :
                                          step.agent_name.includes("Auditor") ? "auditor" : "fixer";
                        appendTrace(step.agent_name, step.role, step.observation, roleClass);
                    });
                }
                if (session.remediation_patch) {
                    const p = session.remediation_patch;
                    prTitle.textContent = p.pr_title || "Staged Unified Patch";
                    prBranch.textContent = p.patch_id || "sentinel/patch";
                    prDiffContent.textContent = p.diff_content;
                }
            }
        } catch (e) {
            console.error("Failed to fetch agentic audit trace:", e);
        }
    }

    function appendTrace(name, role, text, cssClass) {
        if (!traceFeed) return;
        const entry = document.createElement("div");
        entry.className = `trace-entry ${cssClass}`;
        entry.innerHTML = `
            <div class="trace-badge">${name} (${role})</div>
            <div class="trace-text">${text}</div>
        `;
        traceFeed.prepend(entry);
    }

    // -------------------------------------------------------------
    // 9. Server-Sent Events (SSE) Telemetry Stream
    // -------------------------------------------------------------
    function connectSSE() {
        const streamStatus = document.getElementById("streamStatus");
        const evtSource = new EventSource("/sse");

        evtSource.onopen = () => {
            if (streamStatus) {
                streamStatus.innerHTML = `
                    <span class="status-dot online"></span>
                    <span class="status-text">SSE ACTIVE :8000</span>
                `;
            }
        };

        evtSource.onmessage = (e) => {
            try {
                const telemetry = JSON.parse(e.data);
                if (metricListeners) metricListeners.textContent = telemetry.active_listeners;
                if (metricZombies) metricZombies.textContent = telemetry.zombies_detected;
                if (metricScanned) metricScanned.textContent = telemetry.total_scanned || 8;
                if (metricRisk) {
                    metricRisk.textContent = telemetry.zombies_detected > 0 ? "CRITICAL" : "LOW";
                    metricRisk.style.color = telemetry.zombies_detected > 0 ? "#ff3366" : "#00e676";
                }
                if (telemetry.findings) {
                    updatePortsTable(telemetry.findings);
                }
            } catch (err) {
                console.error("SSE parse error:", err);
            }
        };

        evtSource.onerror = () => {
            if (streamStatus) {
                streamStatus.innerHTML = `
                    <span class="status-dot" style="background:#ff3366; box-shadow:0 0 8px #ff3366;"></span>
                    <span class="status-text" style="color:#ff3366;">OFFLINE (RECONNECTING...)</span>
                `;
            }
        };
    }
    connectSSE();

    // -------------------------------------------------------------
    // 10. Input & Preset Bindings
    // -------------------------------------------------------------
    speakBtn.addEventListener("click", () => {
        transmitQuery(input.value);
    });

    input.addEventListener("keydown", (e) => {
        if (e.key === "Enter") transmitQuery(input.value);
    });

    document.querySelectorAll(".chip").forEach(chip => {
        chip.addEventListener("click", () => {
            const q = chip.getAttribute("data-query");
            input.value = q;
            transmitQuery(q);
        });
    });
});
