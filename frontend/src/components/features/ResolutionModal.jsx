import React, { useState, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Camera, Upload, X, CheckCircle2, ClipboardCheck } from 'lucide-react';
import { Button } from '../ui/Button';
import { Card } from '../ui/Card';
import { resolveIssue } from '../../services/api';

export const ResolutionModal = ({ isOpen, onClose }) => {
  const [step, setStep] = useState('input'); // input, uploading, result
  const [image, setImage] = useState(null);
  const [file, setFile] = useState(null);
  const [issueId, setIssueId] = useState('');
  const [notes, setNotes] = useState('');
  const [result, setResult] = useState(null);

  const handleImageUpload = (e) => {
    const selectedFile = e.target.files[0];
    if (selectedFile) {
      setFile(selectedFile);
      const reader = new FileReader();
      reader.onloadend = () => {
        setImage(reader.result);
      };
      reader.readAsDataURL(selectedFile);
    }
  };

  const handleSubmit = async () => {
    if (!file || !issueId) {
      alert('Please provide both Issue ID and Resolution Image.');
      return;
    }

    setStep('uploading');
    
    try {
      const apiResult = await resolveIssue(file, issueId, notes);
      console.log("✅ Resolution Success:", apiResult);
      setResult(apiResult);
      setStep('result');
    } catch (error) {
      console.error("❌ Resolution Error:", error);
      alert(`Failed to resolve issue: ${error.message}`);
      setStep('input');
    }
  };

  const reset = () => {
    setImage(null);
    setFile(null);
    setIssueId('');
    setNotes('');
    setStep('input');
    setResult(null);
  };

  const handleClose = () => {
    reset();
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

            <div className="p-4 text-center border-b border-slate-100 bg-green-50">
              <div className="inline-flex items-center justify-center w-12 h-12 bg-green-100 rounded-full mb-2">
                <ClipboardCheck className="w-6 h-6 text-green-600" />
              </div>
              <h2 className="text-2xl font-bold text-slate-900 mb-1">
                Resolve Issue
              </h2>
              <p className="text-slate-500 text-sm">
                Upload the 'After' photo to close the issue
              </p>
            </div>

            <div className="p-6">
              {step === 'input' && (
                <div className="space-y-4">
                  {/* Issue ID Input */}
                  <div>
                    <label className="block text-sm font-bold text-slate-700 mb-1">
                      Issue ID <span className="text-red-500">*</span>
                    </label>
                    <input
                      type="text"
                      placeholder="e.g., VMC-1234"
                      value={issueId}
                      onChange={(e) => setIssueId(e.target.value)}
                      className="w-full px-4 py-2 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-transparent"
                    />
                  </div>

                  {/* Image Upload */}
                  <div>
                    <label className="block text-sm font-bold text-slate-700 mb-1">
                      Resolution Image <span className="text-red-500">*</span>
                    </label>
                    {image ? (
                      <div className="relative rounded-xl overflow-hidden border border-slate-200">
                        <img src={image} alt="Preview" className="w-full h-48 object-cover" />
                        <button 
                          onClick={() => { setImage(null); setFile(null); }}
                          className="absolute top-2 right-2 p-1 bg-red-500 text-white rounded-full hover:bg-red-600"
                        >
                          <X className="w-4 h-4" />
                        </button>
                      </div>
                    ) : (
                      <label className="flex flex-col items-center gap-3 p-8 border-2 border-dashed border-green-200 rounded-xl bg-green-50/50 hover:bg-green-50 transition-all cursor-pointer">
                        <input 
                          type="file" 
                          accept="image/jpeg,image/png,image/webp"
                          onChange={handleImageUpload}
                          className="hidden" 
                        />
                        <div className="p-4 bg-green-600 rounded-full text-white">
                          <Upload className="w-8 h-8" />
                        </div>
                        <span className="font-bold text-green-700">Upload After Photo</span>
                      </label>
                    )}
                  </div>

                  {/* Engineer Notes */}
                  <div>
                    <label className="block text-sm font-bold text-slate-700 mb-1">
                      Engineer Notes (Optional)
                    </label>
                    <textarea
                      placeholder="e.g., Pothole filled with asphalt. Road is now safe."
                      value={notes}
                      onChange={(e) => setNotes(e.target.value)}
                      rows={3}
                      className="w-full px-4 py-2 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-transparent resize-none"
                    />
                  </div>

                  <Button 
                    className="w-full bg-green-600 hover:bg-green-700" 
                    onClick={handleSubmit}
                    disabled={!file || !issueId}
                  >
                    <CheckCircle2 className="w-5 h-5 mr-2" />
                    Mark as Resolved
                  </Button>
                </div>
              )}

              {step === 'uploading' && (
                <div className="py-10 text-center space-y-6">
                  <div className="relative w-24 h-24 mx-auto">
                    <div className="absolute inset-0 border-4 border-slate-100 rounded-full"></div>
                    <div className="absolute inset-0 border-4 border-green-600 rounded-full border-t-transparent animate-spin"></div>
                  </div>
                  <div>
                    <h3 className="text-lg font-bold text-slate-900">Submitting Resolution...</h3>
                    <p className="text-slate-500 text-sm">Uploading image and closing issue</p>
                  </div>
                </div>
              )}

              {step === 'result' && result && (
                <div className="space-y-6 text-center">
                  <div className="inline-flex items-center justify-center w-20 h-20 bg-green-100 rounded-full">
                    <CheckCircle2 className="w-10 h-10 text-green-600" />
                  </div>
                  
                  <div>
                    <h3 className="text-2xl font-bold text-slate-900">Issue Resolved!</h3>
                    <p className="text-slate-500 mt-2">{result.resolution_message}</p>
                  </div>

                  <div className="bg-slate-50 p-4 rounded-xl border border-slate-200">
                    <p className="text-xs text-slate-500 uppercase font-semibold mb-1">Issue ID</p>
                    <p className="text-lg font-bold text-slate-900">{result.issue_id}</p>
                  </div>

                  <div className="flex gap-3">
                    <Button variant="secondary" className="w-full" onClick={reset}>Resolve Another</Button>
                    <Button className="w-full bg-green-600 hover:bg-green-700" onClick={handleClose}>Done</Button>
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
