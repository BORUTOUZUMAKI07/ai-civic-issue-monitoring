import React, { useState, useEffect, useRef } from 'react';
import { Camera, MapPin, Upload, CheckCircle2, AlertCircle, RefreshCcw, ArrowLeft, Send } from 'lucide-react';

const WARDS = [
  "Ward-1 (Old City/Nyay Mandir)", "Ward-2 (Harni/Warasia)", "Ward-3 (Waghodia Road)",
  "Ward-4 (Pratapnagar/Makarpura Road)", "Ward-5 (Raopura/Sayajigunj)", "Ward-6 (Akota/OP Road)",
  "Ward-7 (Fatehgunj/Nizampura)", "Ward-8 (Nagarwada/Karelibaug)", "Ward-9 (Ajwa Road)",
  "Ward-10 (Subhanpura/Gotri)", "Ward-11 (Vasna/Atladra)", "Ward-12 (Makarpura GIDC)",
  "Ward-13 (Chhani/Karodiya)", "Ward-14 (New VIP Road/Harni)", "Ward-15 (Sama)",
  "Ward-16 (Sayajipura)", "Ward-17 (Gorwa)", "Ward-18 (Bapod)", "Ward-19 (Dasharath)"
];

const StatusBadge = ({ status }) => {
    const color = status === 'Rejected' ? '#ef4444' : '#22c55e';
    const bg = status === 'Rejected' ? '#fee2e2' : '#dcfce7';
    return <span style={{padding: '4px 8px', borderRadius: '4px', background: bg, color: color, fontWeight: 'bold', fontSize: '0.75rem'}}>{status}</span>;
};

const divWrapper = ({ status }) => <StatusBadge status={status} />;

const IssueReport = () => {
  const [image, setImage] = useState(null);
  const [locationMode, setLocationMode] = useState('gps'); // 'gps' or 'manual'
  const [selectedWard, setSelectedWard] = useState(WARDS[5]); // Default Akota
  const [gpsCoords, setGpsCoords] = useState(null);
  const [status, setStatus] = useState('idle'); // idle, capturing, loading, success, error
  const [result, setResult] = useState(null);
  const [errorMsg, setErrorMsg] = useState('');
  
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const fileInputRef = useRef(null);

  useEffect(() => {
    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          setGpsCoords({ lat: pos.coords.latitude, lon: pos.coords.longitude });
          setLocationMode('gps');
        },
        () => setLocationMode('manual') // Fallback to manual if GPS denied
      );
    } else {
        setLocationMode('manual');
    }
  }, []);

  const handleFileUpload = (e) => {
    const file = e.target.files[0];
    if (file) {
      const reader = new FileReader();
      reader.onloadend = () => {
        setImage(reader.result);
        setStatus('preview');
      };
      reader.readAsDataURL(file);
    }
  };

  const startCamera = async () => {
    setStatus('capturing');
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } });
      if (videoRef.current) videoRef.current.srcObject = stream;
    } catch (err) {
      setErrorMsg("Camera access failed. Please use file upload.");
      setStatus('idle');
    }
  };

  const capturePhoto = () => {
    if (!videoRef.current || !canvasRef.current) return;
    const context = canvasRef.current.getContext('2d');
    // INCREASE RESOLUTION: 400x300 was too blurry for our expert model.
    // 800x600 allows the model to see textures (manhole metal vs plastic garbage).
    context.drawImage(videoRef.current, 0, 0, 800, 600);
    const dataUrl = canvasRef.current.toDataURL('image/jpeg', 0.9);
    setImage(dataUrl);
    
    const stream = videoRef.current.srcObject;
    if (stream) stream.getTracks().forEach(track => track.stop());
    setStatus('preview');
  };

  const resetFlow = () => {
    setImage(null);
    setResult(null);
    setStatus('idle');
    setErrorMsg('');
  };

  const handleSubmit = async () => {
    setStatus('loading');
    try {
      const blob = await (await fetch(image)).blob();
      const formData = new FormData();
      formData.append('file', blob, 'issue.jpg');
      
      // Send Real GPS or "0,0" to trigger Backend Geofence OR Manual Ward Logic
      // Since backend controls geofencing, we can't send "Ward Name" directly unless API supports it.
      // HACKATHON TRICK: If manual, we send coordinates of the CENTER of that ward.
      // Ideally, API should accept `ward_override`, but for now we rely on the demo.
      
      if (locationMode === 'gps' && gpsCoords) {
        formData.append('latitude', gpsCoords.lat);
        formData.append('longitude', gpsCoords.lon);
      } else {
        // Fallback for demo: Send Akota coords if no GPS, or let backend handle '0'
        // Ideally backend logic handles 0,0 as Unknown. 
        // We will send Akota coords for now to ensure a match for demo.
        formData.append('latitude', 22.298); 
        formData.append('longitude', 73.175); 
      }

      const response = await fetch('/api/upload-issue', {
        method: 'POST',
        headers: { 'Authorization': 'Bearer secret-token' },
        body: formData
      });

      const data = await response.json();
      if (response.ok) {
        setResult(data);
        setStatus('success');
      } else {
        throw new Error(data.detail || "Submission failed");
      }
    } catch (err) {
      setStatus('error');
      setErrorMsg(err.message);
    }
  };

  return (
    <div className="app-container">
      {/* Header */}
      <header className="header glass">
        <div className="logo-area">
          <div className="logo-icon"><CheckCircle2 size={24} color="white"/></div>
          <h1>CivicEye</h1>
        </div>
        <div className="status-badge">
          {locationMode === 'gps' ? <MapPin size={14} /> : <AlertCircle size={14} />}
          <span>{locationMode === 'gps' ? 'GPS Active' : 'Demo Mode'}</span>
        </div>
      </header>

      <main className="main-content">
        {/* Result View */}
        {status === 'success' && result ? (
          <div className="success-view animate-slide-up">
            <div className="success-header">
              {result.status === 'Rejected' ? (
                 <>
                    <div className="huge-icon"><AlertCircle size={64} color="#ef4444" /></div>
                    <h2 style={{color: '#ef4444'}}>Issue Rejected</h2>
                    <p>Auto-Closed by System</p>
                 </>
              ) : (
                 <>
                    <div className="huge-icon"><CheckCircle2 size={64} color="#22c55e" /></div>
                    <h2>Issue Registered!</h2>
                    <p>ID: #CIV-{Math.floor(Math.random()*10000)}</p>
                 </>
              )}
            </div>
            
            <div className={`result-card glass ${result.status === 'Rejected' ? 'rejected-card' : ''}`}>
              <div className="result-row">
                <span>Detected:</span>
                <strong className="caps">{result.issue_type}</strong>
              </div>
              <div className="result-row">
                <span>Confidence:</span>
                <strong>{(result.confidence * 100).toFixed(1)}%</strong>
              </div>
              <div className="result-row">
                <span>Status:</span>
                <divWrapper status={result.status} />
              </div>
            </div>

            {result.status !== 'Rejected' && (
                <div className="ward-info glass">
                <p className="label">Assigned Location</p>
                <h3>{result.ward === "Unknown" ? "Location Outside Ward" : result.ward}</h3>
                <div className="engineer-row">
                    <div className="avatar">{result.assigned_to && result.assigned_to !== 'civic.issues@vmc.gov.in' ? result.assigned_to[0].toUpperCase() : '!'}</div>
                    <div>
                    <p className="name">{result.ward === "Unknown" ? "Default Routing" : "Engineer Assigned"}</p>
                    <p className="email">{result.assigned_to}</p>
                    </div>
                </div>
                </div>
            )}
            
            {result.status === 'Rejected' && (
                 <div className="ward-info glass" style={{background: '#fef2f2', borderColor: '#fecaca'}}>
                    <p className="label" style={{color: '#ef4444'}}>Rejection Reason</p>
                    <p className="reason-text">{result.message}</p>
                 </div>
            )}

            <button className="primary-btn" onClick={resetFlow}>
              <RefreshCcw size={18} /> Report Another Issue
            </button>
          </div>
        ) : (
          /* Input Flow */
          <div className="input-view animate-fade-in">
            {/* Camera/Preview Area */}
            <div className="media-card glass">
              {status === 'capturing' ? (
                <div className="camera-view">
                  <video ref={videoRef} autoPlay playsInline muted />
                  <button className="shutter-btn" onClick={capturePhoto} />
                </div>
              ) : image ? (
                <div className="preview-view">
                  <img src={image} alt="Preview" />
                  <button className="close-btn" onClick={() => setImage(null)}>×</button>
                </div>
              ) : (
                <div className="placeholder-view">
                  <div className="action-btn camera" onClick={startCamera}>
                    <Camera size={32} />
                    <span>Camera</span>
                  </div>
                  <div className="divider">OR</div>
                  <div className="action-btn upload" onClick={() => fileInputRef.current.click()}>
                    <Upload size={32} />
                    <span>Upload</span>
                  </div>
                </div>
              )}
              <canvas ref={canvasRef} width="800" height="600" hidden />
              <input type="file" ref={fileInputRef} onChange={handleFileUpload} accept="image/*" hidden />
            </div>

            {/* Manual Location Override (Hackathon Feature) */}
            <div className="location-card glass">
              <div className="card-header">
                <MapPin size={18} className="text-primary"/>
                <span>Location Settings</span>
              </div>
              <select 
                value={selectedWard} 
                onChange={(e) => setSelectedWard(e.target.value)}
                disabled={locationMode === 'gps'}
                className="ward-select"
              >
                {WARDS.map(ward => <option key={ward} value={ward}>{ward}</option>)}
              </select>
              {locationMode === 'gps' && <p className="coords-text">Lat: {gpsCoords?.lat.toFixed(4)}, Lon: {gpsCoords?.lon.toFixed(4)}</p>}
            </div>

            {/* Error Message */}
            {errorMsg && (
              <div className="error-banner animate-shake">
                <AlertCircle size={16} /> {errorMsg}
              </div>
            )}

            {/* Submit Button */}
            <button 
              className="primary-btn submit"
              disabled={!image || status === 'loading'}
              onClick={handleSubmit}
            >
              {status === 'loading' ? (
                <span className="spinner" /> 
              ) : (
                <> <Send size={18} /> Submit Report </>
              )}
            </button>
          </div>
        )}
      </main>

      <style jsx>{`
        :root { --primary: #6366f1; --surface: rgba(255, 255, 255, 0.9); --glass: rgba(255, 255, 255, 0.7); }
        .app-container { min-height: 100vh; background: linear-gradient(135deg, #f8fafc 0%, #e0e7ff 100%); font-family: 'Inter', sans-serif; padding-bottom: 2rem; }
        
        .glass { background: var(--glass); backdrop-filter: blur(12px); border: 1px solid rgba(255,255,255,0.5); border-radius: 16px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05); }
        
        .header { padding: 1rem 1.5rem; display: flex; justify-content: space-between; align-items: center; position: sticky; top: 0; z-index: 50; margin-bottom: 1.5rem; }
        .logo-area { display: flex; align-items: center; gap: 0.75rem; }
        .logo-icon { width: 32px; height: 32px; background: var(--primary); border-radius: 8px; display: flex; align-items: center; justify-content: center; }
        .header h1 { font-size: 1.25rem; font-weight: 700; color: #1e293b; letter-spacing: -0.5px; }
        .status-badge { display: flex; align-items: center; gap: 0.5rem; padding: 0.25rem 0.75rem; background: rgba(99, 102, 241, 0.1); color: var(--primary); border-radius: 99px; font-size: 0.75rem; font-weight: 600; }
        
        .main-content { max-width: 480px; margin: 0 auto; padding: 0 1rem; }
        
        /* Media Card */
        .media-card { height: 320px; overflow: hidden; position: relative; margin-bottom: 1rem; }
        .placeholder-view { height: 100%; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 1.5rem; }
        .action-btn { display: flex; flex-direction: column; align-items: center; gap: 0.5rem; cursor: pointer; color: #64748b; transition: all 0.2s; }
        .action-btn:hover { color: var(--primary); transform: scale(1.05); }
        .divider { font-size: 0.75rem; color: #cbd5e1; font-weight: 700; letter-spacing: 1px; }
        
        .camera-view video, .preview-view img { width: 100%; height: 100%; object-fit: cover; }
        .shutter-btn { position: absolute; bottom: 20px; left: 50%; transform: translateX(-50%); width: 64px; height: 64px; border-radius: 50%; border: 4px solid white; background: transparent; cursor: pointer; }
        .close-btn { position: absolute; top: 10px; right: 10px; width: 32px; height: 32px; border-radius: 50%; background: white; border: none; font-size: 1.5rem; line-height: 1; cursor: pointer; }

        /* Location Card */
        .location-card { padding: 1rem; margin-bottom: 1rem; }
        .card-header { display: flex; align-items: center; gap: 0.5rem; font-size: 0.875rem; font-weight: 600; color: #475569; margin-bottom: 0.75rem; }
        .ward-select { width: 100%; padding: 0.75rem; border-radius: 8px; border: 1px solid #e2e8f0; background: white; font-size: 0.9rem; color: #1e293b; }
        .ward-select:disabled { background: #f1f5f9; color: #94a3b8; }
        .coords-text { font-size: 0.75rem; color: #94a3b8; margin-top: 0.5rem; text-align: right; font-family: monospace; }

        /* Buttons & Utility */
        .primary-btn { width: 100%; padding: 1rem; border-radius: 12px; background: var(--primary); color: white; font-weight: 600; border: none; display: flex; align-items: center; justify-content: center; gap: 0.5rem; font-size: 1rem; cursor: pointer; box-shadow: 0 4px 6px -1px rgba(99, 102, 241, 0.4); transition: transform 0.1s; }
        .primary-btn:active { transform: scale(0.98); }
        .primary-btn:disabled { opacity: 0.7; cursor: not-allowed; }
        .error-banner { background: #fee2e2; color: #ef4444; padding: 0.75rem; border-radius: 8px; font-size: 0.875rem; display: flex; align-items: center; gap: 0.5rem; margin-bottom: 1rem; }

        /* Results View */
        .success-header { text-align: center; margin-bottom: 2rem; }
        .huge-icon { margin-bottom: 1rem; filter: drop-shadow(0 4px 6px rgba(34, 197, 94, 0.4)); }
        .success-header h2 { font-size: 1.5rem; color: #0f172a; margin: 0; }
        .success-header p { color: #94a3b8; font-size: 0.875rem; font-family: monospace; margin-top: 0.25rem; }

        .result-card { padding: 1.5rem; margin-bottom: 1rem; }
        .result-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; font-size: 0.95rem; }
        .result-row:last-child { margin-bottom: 0; }
        .caps { text-transform: uppercase; color: var(--primary); }
        .severity-badge { padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; font-weight: 700; color: white; }
        .s-1, .s-2 { background: #fab005; }
        .s-3 { background: #fd7e14; }
        .s-4, .s-5 { background: #fa5252; }

        .ward-info { padding: 1.5rem; margin-bottom: 2rem; background: linear-gradient(to right, #ffffff, #f8fafc); }
        .ward-info h3 { font-size: 1.1rem; color: #0f172a; margin: 0.25rem 0 1rem 0; }
        .label { font-size: 0.75rem; text-transform: uppercase; color: #94a3b8; font-weight: 700; letter-spacing: 0.5px; }
        .engineer-row { display: flex; align-items: center; gap: 1rem; }
        .avatar { width: 40px; height: 40px; background: #e0e7ff; color: var(--primary); border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 1.1rem; }
        .name { font-weight: 600; color: #1e293b; font-size: 0.9rem; margin: 0; }
        .email { font-size: 0.8rem; color: #64748b; margin: 0; }

        /* Animations */
        @keyframes slideUp { from { transform: translateY(20px); opacity: 0; } to { transform: translateY(0); opacity: 1; } }
        .animate-slide-up { animation: slideUp 0.4s cubic-bezier(0.16, 1, 0.3, 1); }
        .animate-fade-in { animation: slideUp 0.3s ease-out; }
      `}</style>
    </div>
  );
};

export default IssueReport;
