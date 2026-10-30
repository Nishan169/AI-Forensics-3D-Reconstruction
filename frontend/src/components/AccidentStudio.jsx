import { useState, useRef, useEffect, useCallback } from "react";

const ACCIDENT_PRESETS = [
  {
    label: "Head-On Two-Train Collision (Train vs Train)",
    prompt: "Head-on collision between two freight locomotives on the same rail line at 75 km/h and 65 km/h. Tremendous kinetic impact forces both trains to telescope and derail off the tracks."
  },
  {
    label: "High-Speed Freight Train Derailment",
    prompt: "A 125-ton freight train travelling at 85 km/h derails off the tracks, rolls 45 degrees onto its side into the gravel ballast, plowing through the ground."
  },
  {
    label: "Railroad Level-Crossing (Train vs Stalled SUV)",
    prompt: "A 120-ton freight train moving at 85 km/h obliterates an SUV stalled on a railroad crossing. Train stays on rails with massive impact energy dissipation."
  },
  {
    label: "Highway Head-On (18-Wheeler Semi vs Transit Bus)",
    prompt: "Head-on collision between a city transit bus going 55 km/h and an 18-wheeler semi-truck going 65 km/h on wet asphalt with 45-degree post-impact spin."
  },
  {
    label: "Intersection T-Bone (Sedan vs Delivery Truck)",
    prompt: "A blue sedan traveling 70 km/h east t-bones a heavy delivery truck turning north at an intersection. Sedan attempts emergency braking 1.2s before impact, skids, strikes truck cabin, and spins."
  },
  {
    label: "Pedestrian Crosswalk Strike",
    prompt: "A blue sedan traveling 50 km/h fails to brake and strikes a pedestrian crossing the road."
  }
];

export default function AccidentStudio({
  planData,
  onGeneratePlan,
  isPlanning,
  currentTime,
  onTimeChange,
  isPlaying,
  onTogglePlay,
  onRestart,
  speed,
  onSpeedChange,
  cameraMode,
  onCameraModeChange,
  showRoutes,
  onToggleRoutes,
  showLabels,
  onToggleLabels,
  activeCaption,
  getCanvasElement,
  apiKey,
  onApiKeyChange,
  onScrollTo3D
}) {
  const [prompt, setPrompt] = useState(ACCIDENT_PRESETS[0].prompt);
  const [isKeyModalOpen, setIsKeyModalOpen] = useState(false);
  const [tempKey, setTempKey] = useState(apiKey || "");

  const [isRecording, setIsRecording] = useState(false);
  const [recordedVideoUrl, setRecordedVideoUrl] = useState(null);
  const mediaRecorderRef = useRef(null);
  const recordedChunksRef = useRef([]);

  const duration = planData?.plan?.duration || 7.0;
  const recordProgress = Math.min(100, Math.round((currentTime / duration) * 100));

  const handleGenerate = (e) => {
    e?.preventDefault();
    if (!prompt.trim() || isPlanning) return;
    onGeneratePlan(prompt.trim());
  };

  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA") return;
      if (e.code === "Space") {
        e.preventDefault();
        onTogglePlay();
      } else if (e.code === "KeyR") {
        e.preventDefault();
        onRestart();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onTogglePlay, onRestart]);

  const startRecording = useCallback(() => {
    const canvas = getCanvasElement();
    if (!canvas) {
      alert("3D Canvas not ready for recording");
      return;
    }

    try {
      const stream = canvas.captureStream(30);
      let mimeType = "video/webm;codecs=vp9";
      if (!MediaRecorder.isTypeSupported(mimeType)) mimeType = "video/webm;codecs=vp8";
      if (!MediaRecorder.isTypeSupported(mimeType)) mimeType = "video/webm";

      recordedChunksRef.current = [];
      const recorder = new MediaRecorder(stream, { mimeType, videoBitsPerSecond: 6000000 });

      recorder.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) recordedChunksRef.current.push(e.data);
      };

      recorder.onstop = () => {
        const blob = new Blob(recordedChunksRef.current, { type: mimeType });
        const videoUrl = URL.createObjectURL(blob);
        setRecordedVideoUrl(videoUrl);
        setIsRecording(false);

        const a = document.createElement("a");
        a.href = videoUrl;
        a.download = `accident_reconstruction_${Date.now()}.webm`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
      };

      mediaRecorderRef.current = recorder;
      recorder.start(100);
      setIsRecording(true);

      onRestart();
      if (!isPlaying) onTogglePlay();
    } catch (err) {
      alert(`Recording error: ${err.message}`);
      setIsRecording(false);
    }
  }, [getCanvasElement, isPlaying, onRestart, onTogglePlay]);

  useEffect(() => {
    if (isRecording && currentTime >= duration) {
      if (mediaRecorderRef.current && mediaRecorderRef.current.state === "recording") {
        mediaRecorderRef.current.stop();
      }
    }
  }, [currentTime, duration, isRecording]);

  return (
    <div className="recreation-panel">
      <div className="recreation-input-card">
        <div className="recreation-header-row">
          <div className="rec-title">
            <span className="rec-icon">🚗</span>
            <span>Accident &amp; Rail Collision Reconstruction Studio</span>
            {planData && <span className="rec-status-pill">Physics Verified</span>}
          </div>

          <div className="rec-header-actions">
            <button
              type="button"
              className={`btn-api-key ${apiKey ? "configured" : ""}`}
              onClick={() => {
                setTempKey(apiKey || "");
                setIsKeyModalOpen(true);
              }}
            >
              {apiKey ? "✓ Gemini Key Active" : "🔑 Set Gemini Key"}
            </button>
          </div>
        </div>

        <div className="recreation-card-scrollable">
          <form onSubmit={handleGenerate} className="prompt-form">
            <textarea
              className="prompt-textarea"
              rows={2}
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="Describe the traffic or rail accident (e.g. head-on collision between two freight trains)..."
              disabled={isPlanning || isRecording}
            />

            <div className="prompt-actions-row">
              <div className="preset-chips">
                <span className="preset-label">Presets:</span>
                {ACCIDENT_PRESETS.map((p, idx) => (
                  <button
                    key={idx}
                    type="button"
                    className="preset-chip"
                    onClick={() => setPrompt(p.prompt)}
                    disabled={isPlanning || isRecording}
                  >
                    {p.label}
                  </button>
                ))}
              </div>

              <button type="submit" className="btn-plan-generate" disabled={!prompt.trim() || isPlanning || isRecording}>
                {isPlanning ? (
                  <>
                    <div className="spinner-sm" /> Computing Physics…
                  </>
                ) : (
                  <>
                    <span>⚡</span> Simulate Crash
                  </>
                )}
              </button>
            </div>
          </form>

          {planData?.plan && (
            <div className="plan-source-badge">
              Scenario: <strong>{planData.plan.scenarioTitle}</strong> · Impact: <strong>{planData.plan.crashType?.toUpperCase()}</strong> · Weather: <strong>{planData.plan.weather?.toUpperCase()}</strong>
            </div>
          )}
        </div>
      </div>

      {planData?.plan && (
        <div className="playback-hud">
          <div className="playback-scrub-row">
            <button className="btn-play-pause" onClick={onTogglePlay} disabled={isRecording}>
              {isPlaying ? "❚❚" : "▶"}
            </button>

            <button className="btn-restart" onClick={onRestart} disabled={isRecording}>
              ↺
            </button>

            <input
              type="range"
              className="scrub-slider"
              min={0}
              max={duration}
              step={0.02}
              value={currentTime}
              onChange={(e) => onTimeChange(parseFloat(e.target.value))}
              disabled={isRecording}
            />

            <span className="time-display">
              {currentTime.toFixed(1)} / {duration.toFixed(1)}s
            </span>
          </div>

          <div className="playback-controls-bar">
            <div className="control-group">
              <span className="control-label">Speed</span>
              <select className="select-control" value={speed} onChange={(e) => onSpeedChange(parseFloat(e.target.value))}>
                <option value={0.25}>0.25x (Super Slo-Mo)</option>
                <option value={0.5}>0.5x (Slo-Mo)</option>
                <option value={1.0}>1.0x Real-Time</option>
                <option value={1.5}>1.5x</option>
              </select>
            </div>

            <div className="control-group">
              <span className="control-label">Camera</span>
              <select className="select-control camera-select" value={cameraMode} onChange={(e) => onCameraModeChange(e.target.value)}>
                <option value="orbit">Free Orbit</option>
                <option value="follow_v1">Follow Entity 1</option>
                <option value="follow_v2">Follow Entity 2</option>
                <option value="top_down_cctv">Surveillance CCTV (Top-Down)</option>
              </select>
            </div>

            <div className="control-toggles">
              <label className="toggle-chip">
                <input type="checkbox" checked={showRoutes} onChange={(e) => onToggleRoutes(e.target.checked)} />
                Trajectories
              </label>

              <label className="toggle-chip">
                <input type="checkbox" checked={showLabels} onChange={(e) => onToggleLabels(e.target.checked)} />
                Speed Tags
              </label>
            </div>

            <div className="record-actions">
              {isRecording ? (
                <button className="btn-record recording" onClick={() => setIsRecording(false)}>
                  <span className="rec-dot pulsing" /> Recording {recordProgress}%
                </button>
              ) : (
                <button className="btn-record" onClick={startRecording}>
                  <span className="rec-dot" /> Export Video (WebM)
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {planData?.plan && activeCaption && (
        <div className="narrative-banner">
          <span className="narrative-badge">CRASH FORENSICS</span>
          <span className="narrative-text">{activeCaption}</span>
        </div>
      )}

      {isKeyModalOpen && (
        <div className="modal-backdrop" onClick={() => setIsKeyModalOpen(false)}>
          <div className="modal-card" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <div className="modal-title"><span>🔑</span> Google Gemini API Key</div>
              <button className="modal-close" onClick={() => setIsKeyModalOpen(false)}>✕</button>
            </div>

            <div className="modal-body">
              <p className="modal-desc">
                Enables natural language parsing of complex multi-vehicle crash descriptions using Gemini 2.0 Flash.
              </p>
              <input
                type="password"
                className="modal-input"
                placeholder="AIzaSy..."
                value={tempKey}
                onChange={(e) => setTempKey(e.target.value)}
              />
            </div>

            <div className="modal-footer">
              <button
                className="btn-modal-save"
                onClick={() => {
                  onApiKeyChange(tempKey.trim());
                  setIsKeyModalOpen(false);
                }}
              >
                Save Key
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}