import React, { useState, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Camera, Upload, X, Loader2, CheckCircle2, AlertTriangle, MapPin, RefreshCw, Smartphone } from 'lucide-react';
import { Button } from '../ui/Button';
import { Card } from '../ui/Card';
import { cn } from '../../utils/class-names';
import { reportIssue } from '../../services/api';

export const IssueReportModal = ({ isOpen, onClose }) => {
  const [step, setStep] = useState('upload'); // upload, camera, analyzing, result
  const [image, setImage] = useState(null);
  const [file, setFile] = useState(null);
  const [result, setResult] = useState(null);
  const [coords, setCoords] = useState({ lat: 22.3072, lng: 73.1812 });
  const [isCapturing, setIsCapturing] = useState(false);
  
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const streamRef = useRef(null);

  const requestLocation = () => {
    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          setCoords({ lat: pos.coords.latitude, lng: pos.coords.longitude });
          console.log("📍 Location Updated:", pos.coords.latitude, pos.coords.longitude);
        },
        (err) => console.warn("📍 Geolocation failed, using default:", err)
      );
    }
  };

  const startCamera = async () => {
    setStep('camera');
    requestLocation();
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ 
        video: { facingMode: 'environment' }, 
        audio: false 
      });
      videoRef.current.srcObject = stream;
      streamRef.current = stream;
    } catch (err) {
      console.error("📷 Camera Access Denied:", err);
      alert("Camera access denied. Please use file upload.");
      setStep('upload');
    }
  };

  const stopCamera = () => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(track => track.stop());
    }
  };

  const captureImage = () => {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (video && canvas) {
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      const ctx = canvas.getContext('2d');
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
      
      canvas.toBlob((blob) => {
        const capturedFile = new File([blob], "capture.jpg", { type: "image/jpeg" });
        setFile(capturedFile);
        setImage(canvas.toDataURL('image/jpeg'));
        stopCamera();
        analyzeImage(capturedFile);
      }, 'image/jpeg');
    }
  };

  const handleImageUpload = (e) => {
    const selectedFile = e.target.files[0];
    if (selectedFile) {
      requestLocation();
      setFile(selectedFile);
      const reader = new FileReader();
      reader.onloadend = () => {
        setImage(reader.result);
        analyzeImage(selectedFile);
      };
      reader.readAsDataURL(selectedFile);
    }
  };

  const analyzeImage = async (imageFile) => {
    setStep('analyzing');
    
    console.log("🚀 Sending image to backend...");
    try {
        const apiResult = await reportIssue(imageFile, coords.lat, coords.lng);
        console.log("✅ API Success:", apiResult);
        
        setStep('result');
        setResult({
            class: apiResult.issue_type,
            confidence: apiResult.confidence,
            severity: apiResult.severity,
            ward: apiResult.ward,
            engineer: apiResult.engineer_name, 
            email: apiResult.engineer_email,
            reported_lat: coords.lat,
            reported_lng: coords.lng
        });
    } catch (error) {
        console.error("❌ Frontend API Error:", error);
        alert(`Failed to route issue: ${error.message}`);
        setStep('upload');
    }
  };

  const reset = () => {
    stopCamera();
    setImage(null);
    setFile(null);
    setStep('upload');
    setResult(null);
  };

  const handleClose = () => {
    stopCamera();
    onClose();
  };

  if (!isOpen) return null;

  return (
    <AnimatePresence>
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/50 backdrop-blur-sm">
        <motion.div 
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0, scale: 0.95 }}
          className="w-full max-w-lg"
        >
          <Card className="relative overflow-hidden border-slate-200 bg-white">
            <button 
              onClick={handleClose}
              className="absolute top-4 right-4 z-10 text-slate-400 hover:text-slate-600 bg-white/80 p-1 rounded-full backdrop-blur"
            >
              <X className="w-6 h-6" />
            </button>

            <div className="p-4 text-center border-b border-slate-100">
              <h2 className="text-2xl font-bold text-slate-900 mb-1">
                {step === 'camera' ? 'Capture Issue' : 'New Issue Report'}
              </h2>
              <p className="text-slate-500 text-sm">
                {step === 'camera' ? 'Point at the problem area' : 'Automated Verification'}
              </p>
            </div>

            <div className="p-6">
              {step === 'upload' && (
                <div className="space-y-4">
                  <div className="grid grid-cols-2 gap-4">
                    <button 
                        onClick={startCamera}
                        className="flex flex-col items-center gap-3 p-8 border-2 border-blue-100 rounded-2xl bg-blue-50/50 hover:bg-blue-50 transition-all group"
                    >
                        <div className="p-4 bg-blue-600 rounded-full text-white group-hover:scale-110 transition-transform shadow-lg shadow-blue-200">
                            <Camera className="w-8 h-8" />
                        </div>
                        <span className="font-bold text-blue-700">Capture Live</span>
                    </button>

                    <label className="flex flex-col items-center gap-3 p-8 border-2 border-slate-100 rounded-2xl bg-slate-50/50 hover:bg-slate-50 transition-all group cursor-pointer">
                        <input 
                            type="file" 
                            accept="image/jpeg,image/png,image/webp,image/heic"
                            onChange={handleImageUpload}
                            className="hidden" 
                        />
                        <div className="p-4 bg-slate-600 rounded-full text-white group-hover:scale-110 transition-transform shadow-lg shadow-slate-200">
                            <Upload className="w-8 h-8" />
                        </div>
                        <span className="font-bold text-slate-700">Upload File</span>
                    </label>
                  </div>
                  
                  <div className="flex items-center gap-2 px-4 py-2 bg-amber-50 rounded-lg text-amber-700 text-xs font-medium border border-amber-100">
                      <MapPin className="w-3.5 h-3.5" />
                      <span>The app will automatically detect your location for routing.</span>
                  </div>
                </div>
              )}

              {step === 'camera' && (
                <div className="relative rounded-2xl overflow-hidden bg-black aspect-square shadow-inner">
                    <video 
                        ref={videoRef} 
                        autoPlay 
                        playsInline 
                        className="w-full h-full object-cover"
                    />
                    <canvas ref={canvasRef} className="hidden" />
                    
                    <div className="absolute bottom-6 left-0 right-0 flex justify-center items-center gap-8">
                        <button 
                            onClick={() => { stopCamera(); setStep('upload'); }}
                            className="p-3 bg-white/20 backdrop-blur rounded-full text-white hover:bg-white/30 transition-colors"
                        >
                            <X className="w-6 h-6" />
                        </button>
                        
                        <button 
                            onClick={captureImage}
                            className="w-16 h-16 bg-white rounded-full border-4 border-white/30 flex items-center justify-center hover:scale-105 active:scale-95 transition-all shadow-xl"
                        >
                            <div className="w-12 h-12 bg-blue-600 rounded-full"></div>
                        </button>

                        <button 
                            onClick={requestLocation}
                            className="p-3 bg-white/20 backdrop-blur rounded-full text-white hover:bg-white/30 transition-colors"
                        >
                            <RefreshCw className="w-6 h-6" />
                        </button>
                    </div>

                    <div className="absolute top-4 left-4 bg-black/40 backdrop-blur px-3 py-1.5 rounded-full flex items-center gap-2 text-[10px] text-white font-mono border border-white/10 uppercase tracking-widest">
                        <div className="w-1.5 h-1.5 bg-red-500 rounded-full animate-pulse"></div>
                        Live View: {coords.lat.toFixed(4)}, {coords.lng.toFixed(4)}
                    </div>
                </div>
              )}

              {step === 'analyzing' && (
                <div className="py-10 text-center space-y-6">
                    <div className="relative w-24 h-24 mx-auto">
                        <div className="absolute inset-0 border-4 border-slate-100 rounded-full"></div>
                        <div className="absolute inset-0 border-4 border-blue-600 rounded-full border-t-transparent animate-spin"></div>
                        {image && (
                            <img src={image} alt="Preview" className="absolute inset-2 w-20 h-20 object-cover rounded-full opacity-50" />
                        )}
                    </div>
                    <div>
                        <h3 className="text-lg font-bold text-slate-900">Processing Image...</h3>
                        <p className="text-slate-500 text-sm">Checking against civic issue classes</p>
                    </div>
                </div>
              )}

              {step === 'result' && result && (
                <div className="space-y-6">
                    {/* Result Header - Prediction Focus */}
                    <div className="text-center space-y-2 mb-4">
                        <div className={cn(
                            "inline-flex items-center gap-2 px-4 py-1.5 rounded-full text-sm font-bold uppercase tracking-wider",
                            result.class.toLowerCase() === 'non_civic' 
                                ? "bg-red-100 text-red-700 border border-red-200" 
                                : "bg-blue-100 text-blue-700 border border-blue-200"
                        )}>
                            {result.class.replace('_', ' ')}
                        </div>
                        <h3 className="text-3xl font-extrabold text-slate-900">
                            {(result.confidence * 100).toFixed(1)}% <span className="text-slate-400 font-medium text-lg">Confidence</span>
                        </h3>
                    </div>

                    {/* Status Banner */}
                    <div className={cn(
                        "p-4 rounded-xl border flex items-center justify-between mb-4",
                        result.class.toLowerCase() === 'non_civic' ? "bg-red-50 border-red-100" : "bg-green-50 border-green-100"
                    )}>
                        <div className="flex items-center gap-3">
                            <div className={cn(
                                "p-2 rounded-full",
                                result.class.toLowerCase() === 'non_civic' ? "bg-red-100 text-red-600" : "bg-green-100 text-green-600"
                            )}>
                                {result.class.toLowerCase() === 'non_civic' ? <X className="w-4 h-4" /> : <CheckCircle2 className="w-4 h-4" />}
                            </div>
                            <p className="font-bold text-slate-800">
                                {result.class.toLowerCase() === 'non_civic' ? 'Issue Rejected' : 'Issue Registered'}
                            </p>
                        </div>
                        <div className="text-right">
                             <p className="text-[10px] text-slate-400 font-mono uppercase">Ref ID</p>
                             <p className="text-xs text-slate-500 font-mono font-bold">VMC-{Math.floor(Math.random() * 9000) + 1000}</p>
                        </div>
                    </div>

                    {/* Technical Coordinates Section */}
                    <div className="bg-slate-900 rounded-xl p-4 border border-slate-800 shadow-inner">
                        <div className="flex items-center gap-2 text-blue-400 text-[10px] font-bold uppercase tracking-widest mb-3">
                            <Smartphone className="w-3 h-3" />
                            <span>Geo-Reporting Data</span>
                        </div>
                        <div className="grid grid-cols-2 gap-4">
                            <div>
                                <p className="text-slate-500 text-[9px] uppercase font-bold mb-1">Incident Latitude</p>
                                <p className="text-white font-mono text-xs">{result.reported_lat.toFixed(6)}° N</p>
                            </div>
                            <div>
                                <p className="text-slate-500 text-[9px] uppercase font-bold mb-1">Incident Longitude</p>
                                <p className="text-white font-mono text-xs">{result.reported_lng.toFixed(6)}° E</p>
                            </div>
                            <div className="col-span-2 pt-2 border-t border-slate-800 flex items-center justify-between">
                                <p className="text-slate-400 text-[9px] uppercase font-bold">Smart-Routed Ward</p>
                                <p className="text-blue-400 font-bold text-xs">{result.ward}</p>
                            </div>
                        </div>
                    </div>

                    {/* Engineer Details */}
                     <div className="bg-slate-50 p-4 rounded-xl border border-slate-200">
                        <p className="text-xs text-slate-500 uppercase font-semibold mb-2">Assigned Official</p>
                         <div className="flex items-center gap-3">
                            <div className="w-10 h-10 bg-blue-100 rounded-full flex items-center justify-center text-blue-600 font-bold">
                                {result.engineer.split(' ').map(n => n[0]).join('')}
                            </div>
                            <div>
                                <p className="text-sm font-bold text-slate-900">{result.engineer}</p>
                                <p className="text-xs text-slate-500">{result.email}</p>
                            </div>
                         </div>
                    </div>

                    <div className="flex gap-3">
                        <Button variant="secondary" className="w-full" onClick={reset}>Scan Another</Button>
                        <Button className="w-full" onClick={onClose}>Done</Button>
                    </div>
                </div>
              )}
            </div>
          </Card>
        </motion.div>
      </div>
    </AnimatePresence>
  );
};
