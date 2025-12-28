import React, { useState } from 'react';
import { X, RefreshCw, Zap, Image as ImageIcon, Loader2, CheckCircle2 } from 'lucide-react';
import { reportIssue } from '../../services/api';

export const CameraView = ({ onClose }) => {
  const [analyzing, setAnalyzing] = useState(false);
  const [captured, setCaptured] = useState(null);
  const [result, setResult] = useState(null);

  const handleCapture = async () => {
    // Simulate Image Capture (In real app, use webcam/input)
    // For demo, we will just assume an image is selected/captured
    // In a real implementation: const image = webcamRef.current.getScreenshot();
    
    // Create a dummy blob for testing if no real capture exists
    const dummyBlob = await fetch('https://images.unsplash.com/photo-1515162816999-a0c47dc192f7').then(r => r.blob());
    const file = new File([dummyBlob], "capture.jpg", { type: "image/jpeg" });

    setAnalyzing(true);
    
    try {
        // Use Real Location
        const lat = 22.3072; // Hardcoded Vadodara center for demo
        const lng = 73.1812;

        const apiResult = await reportIssue(file, lat, lng);
        
        console.log("API Result:", apiResult);
        
        setResult({
            class: apiResult.issue_type,
            confidence: apiResult.confidence,
            ward: apiResult.ward,
            severity: apiResult.severity
        });
        setCaptured(true);
    } catch (err) {
        alert("Failed to report issue. Is backend running?");
    } finally {
        setAnalyzing(false);
    }
  };

  if (captured) {
      return (
          <div className="fixed inset-0 z-[60] bg-white flex flex-col items-center justify-center p-6 text-center animate-in fade-in zoom-in duration-300">
              <div className="w-24 h-24 bg-green-100 text-green-600 rounded-full flex items-center justify-center mb-6">
                  <CheckCircle2 className="w-12 h-12" />
              </div>
              <h2 className="text-2xl font-bold text-gray-900 mb-2">Issue Reported!</h2>
              <p className="text-gray-500 mb-8">
                  <b>{result.class}</b> detected with <b>{Math.floor(result.confidence * 100)}%</b> confidence.<br/>
                  Sent to Engineer in <b>{result.ward}</b>.
              </p>
              <button 
                onClick={onClose}
                className="w-full py-4 bg-black text-white rounded-2xl font-bold text-lg active:scale-95 transition-transform"
              >
                  Done
              </button>
          </div>
      )
  }

  return (
    <div className="fixed inset-0 z-50 bg-black flex flex-col">
       {/* Camera Header */}
       <div className="p-6 flex justify-between items-center text-white safe-top">
           <button onClick={onClose} className="p-2 bg-white/20 backdrop-blur rounded-full">
               <X className="w-6 h-6" />
           </button>
           <span className="font-medium bg-black/50 px-3 py-1 rounded-full text-xs">AI MODE ON</span>
           <button className="p-2">
               <Zap className="w-6 h-6" />
           </button>
       </div>

       {/* Camera Viewport (Fake) */}
       <div className="flex-1 relative overflow-hidden bg-gray-900">
            {/* Grid Lines */}
            <div className="absolute inset-0 grid grid-cols-3 grid-rows-3 pointer-events-none opacity-30">
                <div className="border-r border-white/50"></div>
                <div className="border-r border-white/50"></div>
                <div></div>
                <div className="border-t border-white/50 col-span-3"></div>
                <div></div>
                <div></div>
                <div></div>
                <div className="border-t border-white/50 col-span-3"></div>
            </div>

            {/* AI Scanning Overlay */}
            <div className="absolute inset-0 flex items-center justify-center">
                {analyzing ? (
                    <div className="text-center space-y-4">
                        <Loader2 className="w-12 h-12 text-blue-500 animate-spin mx-auto" />
                        <p className="text-blue-400 font-mono text-xs animate-pulse">ANALYZING SCENE...</p>
                    </div>
                ) : (
                    <div className="w-64 h-64 border-2 border-white/30 rounded-3xl relative">
                        <div className="absolute top-0 left-0 w-6 h-6 border-t-4 border-l-4 border-white rounded-tl-xl"></div>
                        <div className="absolute top-0 right-0 w-6 h-6 border-t-4 border-r-4 border-white rounded-tr-xl"></div>
                        <div className="absolute bottom-0 left-0 w-6 h-6 border-b-4 border-l-4 border-white rounded-bl-xl"></div>
                        <div className="absolute bottom-0 right-0 w-6 h-6 border-b-4 border-r-4 border-white rounded-br-xl"></div>
                    </div>
                )}
            </div>
       </div>

       {/* Camera Controls */}
       <div className="h-40 bg-black safe-bottom flex items-center justify-around px-10">
           <button className="p-4 rounded-full bg-white/10 text-white hover:bg-white/20">
               <ImageIcon className="w-6 h-6" />
           </button>
           
           <button 
             onClick={handleCapture}
             disabled={analyzing}
             className="w-20 h-20 rounded-full border-4 border-white flex items-center justify-center p-1"
           >
               <div className="w-full h-full bg-white rounded-full transition-transform active:scale-90"></div>
           </button>

           <button className="p-4 rounded-full bg-white/10 text-white hover:bg-white/20">
               <RefreshCw className="w-6 h-6" />
           </button>
       </div>
    </div>
  );
};
