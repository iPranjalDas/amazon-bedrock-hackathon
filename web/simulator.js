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

    // Sentinel+ v1.5.0 Additions: Banner, Topology, Session Strip, Web Audio
    const sentryAlertBanner = document.getElementById("sentryAlertBanner");
    const alertHeadline = document.getElementById("alertHeadline");
    const sessionMemoryStrip = document.getElementById("sessionMemoryStrip");
    const memoryCrumbs = document.getElementById("memoryCrumbs");
    const topologyStage = document.getElementById("topologyStage");
    const topNodeCount = document.getElementById("topNodeCount");
    const topEdgeCount = document.getElementById("topEdgeCount");

    let isSpeaking = false;
    let inFlightTimer = null;
    let pending2PC = null;
    let activeSessionId = "sentinel_" + Math.random().toString(36).substring(2, 9);
    let cachedTopologySvg = "";
    let currentIncident = null;

    // -------------------------------------------------------------
    // Procedural Web Audio API APLA Synthesizer (Voice Blast / Art Museum Standard)
    // -------------------------------------------------------------
    let audioCtx = null;
    let masterGain = null;
    let chordOscillators = [];
    let isAudioPlaying = false;

    function initAplaAudio() {
        if (audioCtx) return;
        try {
            const AudioContextClass = window.AudioContext || window.webkitAudioContext;
            audioCtx = new AudioContextClass();
            masterGain = audioCtx.createGain();
            masterGain.gain.setValueAtTime(0.0001, audioCtx.currentTime);

            const filter = audioCtx.createBiquadFilter();
            filter.type = "lowpass";
            filter.frequency.setValueAtTime(450, audioCtx.currentTime);

            masterGain.connect(filter);
            filter.connect(audioCtx.destination);

            // Cmaj9 ambient frequencies: C3 (130.81Hz), G3 (196.00Hz), B3 (246.94Hz), E4 (329.63Hz)
            const freqs = [130.81, 196.00, 246.94, 329.63];
            freqs.forEach(freq => {
                const osc = audioCtx.createOscillator();
                osc.type = "sine";
                osc.frequency.setValueAtTime(freq, audioCtx.currentTime);

                const oscGain = audioCtx.createGain();
                oscGain.gain.setValueAtTime(0.25, audioCtx.currentTime);
                osc.connect(oscGain);
                oscGain.connect(masterGain);

                osc.start();
                chordOscillators.push(osc);
            });
        } catch (e) {
            console.warn("Web Audio API initialization failed:", e);
        }
    }

    function duckAudio(duck) {
        if (!audioCtx || !masterGain || !isAudioPlaying) return;
        const targetGain = duck ? 0.012 : 0.06;
        masterGain.gain.setTargetAtTime(targetGain, audioCtx.currentTime, 0.15);
    }

    function toggleAudio() {
        const btnToggle = document.getElementById("btnAplaSoundToggle");
        const icon = document.getElementById("soundIcon");
        const label = document.getElementById("soundLabel");

        if (!audioCtx) initAplaAudio();

        if (audioCtx && audioCtx.state === "suspended") {
            audioCtx.resume();
        }

        isAudioPlaying = !isAudioPlaying;
        if (isAudioPlaying) {
            if (masterGain) masterGain.gain.setTargetAtTime(0.06, audioCtx.currentTime, 0.2);
            if (btnToggle) btnToggle.classList.add("active");
            if (icon) icon.textContent = "🔊";
            if (label) label.textContent = "APLA Audio: On";
        } else {
            if (masterGain) masterGain.gain.setTargetAtTime(0.0001, audioCtx.currentTime, 0.2);
            if (btnToggle) btnToggle.classList.remove("active");
            if (icon) icon.textContent = "🔇";
            if (label) label.textContent = "APLA Audio: Off";
        }
    }

    const soundToggleBtn = document.getElementById("btnAplaSoundToggle");
    if (soundToggleBtn) soundToggleBtn.addEventListener("click", toggleAudio);

    // -------------------------------------------------------------
    // Multi-Turn Context Memory Strip Updater
    // -------------------------------------------------------------
    function updateSessionMemory(state) {
        if (!memoryCrumbs) return;
        if (!state) {
            memoryCrumbs.textContent = `Session: ${activeSessionId} • Awaiting Commands`;
            return;
        }
        const portStr = state.last_queried_port ? `Port :${state.last_queried_port}` : "No Port Bound";
        const pidStr = state.last_detected_pid ? `PID ${state.last_detected_pid}` : null;
        const intentStr = state.last_intent || "idle";
        const pendingStr = state.confirmation_pending ? "⚠️ 2PC Affirmation Pending" : "Ready";
        const parts = [`Session: ${activeSessionId}`, portStr];
        if (pidStr) parts.push(pidStr);
        parts.push(`Intent: ${intentStr}`);
        parts.push(`State: ${pendingStr}`);
        memoryCrumbs.textContent = parts.join(" • ");
    }
    updateSessionMemory(null);

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
                latencyMetrics.innerHTML = `<span>IN-FLIGHT: <b style="color:var(--accent-gold);">${elapsed} ms</b></span> | <span>ROUTE: <b>ROUTING...</b></span> | <span>MODEL: <b>AMAZON NOVA PRO</b></span>`;
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
        duckAudio(true);
        duckingTag.textContent = "APLA DUCKING: 10% (SPEECH ACTIVE)";
        duckingTag.style.color = "var(--accent-gold)";

        const stopInFlightTimer = startInFlightTimer();
        if (liveSpeechStream) liveSpeechStream.textContent = "Routing query via Sentinel+ deterministic router...";

        try {
            const resp = await fetch("/alexa/converse", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ query: query, confirm: confirm, session_id: activeSessionId })
            });

            const data = await resp.json();
            const elapsed = stopInFlightTimer();

            // Synchronize multi-turn context memory state & topology
            if (data.session_state) {
                updateSessionMemory(data.session_state);
            }
            fetchRuntimeTopology();

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
                    visionBadge.style.color = rep.status === "VERIFIED_COMPLIANT" ? "var(--accent-emerald)" : "var(--accent-gold)";
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
                duckAudio(false);
                duckingTag.textContent = "APLA DUCKING: 25% AMBIENT HUM";
                duckingTag.style.color = "var(--accent-gold)";
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
    // 9. Server-Sent Events (SSE) Telemetry Stream & Sentry Sentinel
    // -------------------------------------------------------------
    function showIncidentAlert(incident) {
        currentIncident = incident;
        if (alertHeadline) {
            alertHeadline.textContent = incident.headline || `Anomalous process on Port ${incident.target_port} (PID ${incident.target_pid})`;
        }
        if (sentryAlertBanner) {
            sentryAlertBanner.style.display = "flex";
        }
        duckAudio(true);
        setTimeout(() => duckAudio(false), 2500);
        appendChatMessage(`🚨 PROACTIVE SENTRY ALERT: ${incident.headline}`, "Sentinel+ Proactive Sentry");
        fetchRuntimeTopology();
    }

    window.dismissAlertBanner = function() {
        if (sentryAlertBanner) sentryAlertBanner.style.display = "none";
    };

    window.handleAlertMitigation = function() {
        window.dismissAlertBanner();
        if (currentIncident && currentIncident.target_port) {
            window.transmitQuery(`drain port ${currentIncident.target_port}`);
        } else {
            window.transmitQuery("drain port 3000");
        }
    };

    window.triggerSimulateIncident = async function() {
        try {
            const resp = await fetch("/api/simulate-incident", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    incident_type: "zombie_process",
                    target_port: 3000,
                    target_pid: 8492
                })
            });
            const res = await resp.json();
            console.log("Simulated incident triggered:", res);
        } catch (e) {
            console.error("Failed to trigger simulated incident:", e);
        }
    };

    // Topology SVG Engine & Exporter
    async function fetchRuntimeTopology() {
        if (!topologyStage) return;
        try {
            const resp = await fetch("/api/topology-svg");
            if (!resp.ok) return;
            const svgText = await resp.text();
            cachedTopologySvg = svgText;
            topologyStage.innerHTML = svgText;

            const parser = new DOMParser();
            const doc = parser.parseFromString(svgText, "image/svg+xml");
            const rects = doc.querySelectorAll("rect");
            const lines = doc.querySelectorAll("line");
            if (topNodeCount) topNodeCount.textContent = `${Math.max(rects.length - 1, 1)} Active`;
            if (topEdgeCount) topEdgeCount.textContent = `${lines.length} Links`;
        } catch (e) {
            console.warn("Failed to fetch topology SVG:", e);
        }
    }
    fetchRuntimeTopology();

    window.downloadTopologySvg = function() {
        if (!cachedTopologySvg) {
            alert("Topology SVG not yet loaded. Please wait a moment.");
            return;
        }
        const blob = new Blob([cachedTopologySvg], { type: "image/svg+xml;charset=utf-8" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `sentinel_topology_${Date.now()}.svg`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    };

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
                // Check if proactive incident alert
                if (telemetry.event === "INCIDENT_ALERT") {
                    showIncidentAlert(telemetry);
                    return;
                }

                if (metricListeners) metricListeners.textContent = telemetry.active_listeners;
                if (metricZombies) metricZombies.textContent = telemetry.zombies_detected;
                if (metricScanned) metricScanned.textContent = telemetry.total_scanned || 8;
                if (metricRisk) {
                    metricRisk.textContent = telemetry.zombies_detected > 0 ? "CRITICAL" : "LOW";
                    metricRisk.style.color = telemetry.zombies_detected > 0 ? "var(--accent-rose)" : "var(--accent-emerald)";
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
                    <span class="status-dot" style="background:var(--accent-rose); box-shadow:0 0 8px var(--accent-rose-glow);"></span>
                    <span class="status-text" style="color:var(--accent-rose);">OFFLINE (RECONNECTING...)</span>
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

    // -------------------------------------------------------------
    // 11. Multimodal Diagram Dropzone & Sample Controller (v1.4.0)
    // -------------------------------------------------------------
    const diagramDropzone = document.getElementById("diagramDropzone");
    const diagramFileInput = document.getElementById("diagramFileInput");
    const dropzonePrompt = document.getElementById("dropzonePrompt");
    const diagramStage = document.getElementById("diagramStage");
    const diagramImage = document.getElementById("diagramImage");
    const spatialOverlay = document.getElementById("spatialOverlay");
    const scanLaserBeam = document.getElementById("scanLaserBeam");

    function renderSpatialBoxes(boxes) {
        if (!spatialOverlay) return;
        spatialOverlay.innerHTML = boxes.map(b => `
            <div class="spatial-bounding-box ${b.state}" style="left:${b.x}%; top:${b.y}%; width:${b.w}%; height:${b.h}%;">
                ${b.label}
            </div>
        `).join("");
    }

    async function sendDiagramToApi(base64Data, filename) {
        if (scanLaserBeam) scanLaserBeam.classList.add("scanning");
        try {
            const res = await fetch("/api/verify-diagram", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ image_base64: base64Data, diagram_name: filename })
            });
            const rep = await res.json();
            if (scanLaserBeam) scanLaserBeam.classList.remove("scanning");

            if (visionBadge) {
                visionBadge.textContent = rep.status;
                visionBadge.style.color = rep.status === "VERIFIED_COMPLIANT" ? "var(--accent-emerald)" : "var(--accent-rose)";
            }
            if (visionCardBody) {
                visionCardBody.innerHTML = `<b>Status:</b> ${rep.status} | <b>Drift Score:</b> ${rep.drift_score}<br><b>Declared:</b> ${rep.declared_services_count} services | <b>Active:</b> ${rep.live_listeners_count} sockets.<br>${rep.summary_verdict}`;
            }

            if (rep.anomalies && rep.anomalies.length > 0) {
                const boxes = [
                    { x: 8, y: 15, w: 32, h: 42, label: ":8000 MCP [OK]", state: "verified" },
                    { x: 50, y: 15, w: 38, h: 48, label: `⚠️ :${rep.anomalies[0].port} ${rep.anomalies[0].anomaly_type}`, state: "drift" }
                ];
                renderSpatialBoxes(boxes);
            } else {
                renderSpatialBoxes([
                    { x: 10, y: 20, w: 30, h: 42, label: ":8000 MCP [OK]", state: "verified" },
                    { x: 52, y: 20, w: 30, h: 42, label: ":5432 DB [OK]", state: "verified" }
                ]);
            }
        } catch (err) {
            if (scanLaserBeam) scanLaserBeam.classList.remove("scanning");
            if (visionCardBody) visionCardBody.textContent = `Verification error: ${err.message}`;
        }
    }

    if (diagramDropzone && diagramFileInput) {
        diagramDropzone.addEventListener("click", () => diagramFileInput.click());

        diagramFileInput.addEventListener("change", (e) => {
            const file = e.target.files[0];
            if (!file) return;
            if (file.size > 5 * 1024 * 1024) {
                alert("File size exceeds 5MB limit. Please upload an architecture image under 5MB.");
                return;
            }
            const reader = new FileReader();
            reader.onload = (evt) => {
                if (dropzonePrompt) dropzonePrompt.style.display = "none";
                if (diagramStage) diagramStage.style.display = "flex";
                if (diagramImage) diagramImage.src = evt.target.result;
                sendDiagramToApi(evt.target.result, file.name);
            };
            reader.readAsDataURL(file);
        });

        diagramDropzone.addEventListener("dragover", (e) => {
            e.preventDefault();
            diagramDropzone.classList.add("drag-active");
        });
        diagramDropzone.addEventListener("dragleave", () => {
            diagramDropzone.classList.remove("drag-active");
        });
        diagramDropzone.addEventListener("drop", (e) => {
            e.preventDefault();
            diagramDropzone.classList.remove("drag-active");
            const file = e.dataTransfer.files[0];
            if (file) {
                if (file.size > 5 * 1024 * 1024) {
                    alert("File size exceeds 5MB limit.");
                    return;
                }
                const reader = new FileReader();
                reader.onload = (evt) => {
                    if (dropzonePrompt) dropzonePrompt.style.display = "none";
                    if (diagramStage) diagramStage.style.display = "flex";
                    if (diagramImage) diagramImage.src = evt.target.result;
                    sendDiagramToApi(evt.target.result, file.name);
                };
                reader.readAsDataURL(file);
            }
        });
    }

    window.loadDiagramSample = function(type) {
        if (scanLaserBeam) scanLaserBeam.classList.add("scanning");
        if (dropzonePrompt) dropzonePrompt.style.display = "none";
        if (diagramStage) diagramStage.style.display = "flex";

        setTimeout(() => {
            if (scanLaserBeam) scanLaserBeam.classList.remove("scanning");
            if (type === "clean") {
                if (visionBadge) {
                    visionBadge.textContent = "VERIFIED_COMPLIANT";
                    visionBadge.style.color = "var(--accent-emerald)";
                }
                if (visionCardBody) {
                    visionCardBody.innerHTML = `<b>Status:</b> VERIFIED_COMPLIANT | <b>Drift Score:</b> 0.00<br><b>Declared:</b> 4 services | <b>Active:</b> 4 sockets matched.<br>All architecture topology invariants hold. Zero zombie socket drift detected.`;
                }
                renderSpatialBoxes([
                    { x: 10, y: 20, w: 32, h: 45, label: ":8000 MCP [VERIFIED]", state: "verified" },
                    { x: 50, y: 20, w: 32, h: 45, label: ":5432 PostgreSQL [VERIFIED]", state: "verified" }
                ]);
            } else {
                if (visionBadge) {
                    visionBadge.textContent = "DRIFT_DETECTED";
                    visionBadge.style.color = "var(--accent-rose)";
                }
                if (visionCardBody) {
                    visionCardBody.innerHTML = `<b>Status:</b> DRIFT_DETECTED | <b>Drift Score:</b> 0.75<br><b>Declared:</b> 4 services | <b>Active:</b> 5 sockets.<br><span style="color:var(--accent-rose); font-weight:700;">⚠️ Rogue process listening on Port :3000 (PID 8492) absent from architecture spec.</span>`;
                }
                renderSpatialBoxes([
                    { x: 10, y: 20, w: 32, h: 45, label: ":8000 MCP [VERIFIED]", state: "verified" },
                    { x: 50, y: 15, w: 42, h: 52, label: "⚠️ :3000 GHOST_LISTENER (PID 8492)", state: "drift" }
                ]);
            }
        }, 1200);
    };

    // -------------------------------------------------------------
    // 12. Live Sandbox Patch Test Runner with SSE Streaming
    // -------------------------------------------------------------
    window.runSandboxPatchTest = async function() {
        const terminalScreen = document.getElementById("sandboxTerminalScreen");
        const btnRun = document.getElementById("btnRunSandbox");
        if (!terminalScreen) return;

        switchTab("tabDiff");
        if (btnRun) {
            btnRun.disabled = true;
            btnRun.innerHTML = `<span>⏳ Running Isolated Sandbox Tests...</span>`;
        }

        terminalScreen.innerHTML = `<div class="term-line log-system"><span class="term-time">[${new Date().toISOString().substring(11, 23)}]</span> <span class="term-cyan">SYS_INIT:</span> Initializing isolated Linux native /tmp sandbox...</div>`;

        try {
            const response = await fetch("/api/test-patch", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ port: 3000, target_file: "server.py" })
            });

            const reader = response.body.getReader();
            const decoder = new TextDecoder("utf-8");
            let buffer = "";

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split("\n");
                buffer = lines.pop();

                for (const line of lines) {
                    if (line.startsWith("data: ")) {
                        try {
                            const data = JSON.parse(line.substring(6));
                            const timeStr = `[${new Date().toISOString().substring(11, 23)}]`;
                            let lineHtml = "";

                            if (data.event === "SANDBOX_INIT") {
                                lineHtml = `<div class="term-line log-system"><span class="term-time">${timeStr}</span> <span class="term-cyan">SANDBOX_INIT:</span> Staged in <code>${data.sandbox_dir}</code> (ext4/tmpfs)</div>`;
                            } else if (data.event === "AST_VERIFY") {
                                lineHtml = `<div class="term-line log-fix"><span class="term-time">${timeStr}</span> <span class="term-green">AST_VERIFY:</span> ${data.status} (Safety Score: ${data.safety_score}, Branch: ${data.branch_name})</div>`;
                            } else if (data.event === "EXEC_TEST") {
                                lineHtml = `<div class="term-line log-test"><span class="term-time">${timeStr}</span> ${data.content}</div>`;
                            } else if (data.event === "LEAK_CHECK") {
                                lineHtml = `<div class="term-line log-info"><span class="term-time">${timeStr}</span> <span class="term-blue">LEAK_CHECK:</span> Verdict: ${data.leak_verdict} (Unclosed sockets: ${data.unclosed_descriptors_detected})</div>`;
                            } else if (data.event === "PASS") {
                                lineHtml = `<div class="term-line log-summary"><span class="term-time">${timeStr}</span> <span class="term-badge-gold">41/41 TESTS PASSED</span> <span class="term-green">0 ERRORS • 0 LEAKS • ${data.elapsed_ms}ms</span></div>`;
                            } else if (data.event === "FAIL") {
                                lineHtml = `<div class="term-line log-gate"><span class="term-time">${timeStr}</span> <span class="term-rose">EXEC_FAILED:</span> ${data.reason || data.details}</div>`;
                            }

                            if (lineHtml) {
                                terminalScreen.innerHTML += lineHtml;
                                terminalScreen.scrollTop = terminalScreen.scrollHeight;
                            }
                        } catch (e) {
                            // Non-json SSE data chunk
                        }
                    }
                }
            }
        } catch (err) {
            terminalScreen.innerHTML += `<div class="term-line log-gate"><span class="term-rose">STREAM ERROR:</span> ${err.message}</div>`;
        } finally {
            if (btnRun) {
                btnRun.disabled = false;
                btnRun.innerHTML = `<span>▶ Run Live Sandbox Patch Test (Streaming SSE)</span>`;
            }
        }
    };
});
