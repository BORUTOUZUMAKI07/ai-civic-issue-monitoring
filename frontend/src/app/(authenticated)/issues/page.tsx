"use client";

import { useIssues, useUploadIssueMutation } from "@/queries/index";
import { useWebSocket } from "@/hooks/useWebSocket";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
import { Plus, Camera, Wifi, WifiOff, Search, Filter, ChevronRight, MapPin } from "lucide-react";
import { useState, useRef, useCallback } from "react";
import Link from "next/link";

const TYPE_ICONS: Record<string, string> = {
  pothole: "🕳️",
  garbage: "🗑️",
  broken_streetlight: "💡",
  waterlogging: "🌊",
  debris: "🧱",
  sewage: "🚰",
  road_damage: "🚧",
};

const severityBadge = (s: number) => {
  const labels = ["", "Minimal", "Low", "Medium", "High", "Critical"];
  const colors = ["", "bg-green-100 text-green-700", "bg-yellow-100 text-yellow-700", "bg-orange-100 text-orange-700", "bg-red-100 text-red-700", "bg-red-600 text-white"];
  return <Badge className={`${colors[s] || ""} border-0`}>{labels[s] || s}</Badge>;
};

const statusBadge = (s: string) => {
  const colors: Record<string, string> = {
    reported: "bg-blue-100 text-blue-700",
    assigned: "bg-purple-100 text-purple-700",
    in_progress: "bg-amber-100 text-amber-700",
    resolved: "bg-green-100 text-green-700",
  };
  return <Badge className={`${colors[s] || "bg-gray-100 text-gray-700"} border-0`}>{s.replace("_", " ")}</Badge>;
};

export default function IssuesPage() {
  const { data, isLoading, refetch } = useIssues({ limit: 50 });
  const uploadMutation = useUploadIssueMutation();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [search, setSearch] = useState("");
  const [filterStatus, setFilterStatus] = useState<string>("all");
  const [filterType, setFilterType] = useState<string>("all");
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [description, setDescription] = useState("");
  const [lat, setLat] = useState("22.3072");
  const [lon, setLon] = useState("73.1812");
  const modalFileRef = useRef<HTMLInputElement>(null);

  const wsBase = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  const wsUrl = wsBase.replace(/^http/, "ws") + "/api/v1/ws/issues";

  const onWsMessage = useCallback(
    (msg: { type: string; payload: Record<string, unknown> }) => {
      if (msg.type === "issue_created" || msg.type === "issue_updated") {
        refetch();
        toast.info(`Issue ${msg.type === "issue_created" ? "reported" : "updated"} — real-time update`);
      }
    },
    [refetch]
  );

  const { isConnected } = useWebSocket({ url: wsUrl, onMessage: onWsMessage, reconnectAttempts: 3, reconnectInterval: 5000 });

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setSelectedFile(file);
    setPreviewUrl(URL.createObjectURL(file));
    setShowUploadModal(true);
  };

  const handleUpload = async () => {
    if (!selectedFile) return;
    setUploading(true);
    try {
      let uploadLat = parseFloat(lat);
      let uploadLon = parseFloat(lon);
      try {
        const pos = await new Promise<GeolocationPosition>((resolve, reject) => {
          navigator.geolocation.getCurrentPosition(resolve, reject, { timeout: 5000 });
        });
        uploadLat = pos.coords.latitude;
        uploadLon = pos.coords.longitude;
        setLat(String(uploadLat.toFixed(6)));
        setLon(String(uploadLon.toFixed(6)));
      } catch { /* use manual values */ }

      await uploadMutation.mutateAsync({ file: selectedFile, latitude: uploadLat, longitude: uploadLon, description });
      toast.success("Issue reported! AI classification in progress...");
      setShowUploadModal(false);
      setSelectedFile(null);
      setPreviewUrl(null);
      setDescription("");
    } catch (error: unknown) {
      toast.error(error instanceof Error ? error.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  const items = data?.items || [];
  const filtered = items.filter((i) => {
    if (filterStatus !== "all" && i.status !== filterStatus) return false;
    if (filterType !== "all" && i.issue_type !== filterType) return false;
    if (search) {
      const q = search.toLowerCase();
      return i.description?.toLowerCase().includes(q) || i.issue_type.replace("_", " ").includes(q);
    }
    return true;
  });

  return (
    <div className="space-y-6 p-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold">Issues</h1>
            <span className="flex items-center gap-1 text-xs text-muted-foreground">
              {isConnected ? <><Wifi className="h-3 w-3 text-green-500" /> Live</> : <><WifiOff className="h-3 w-3 text-gray-400" /> Offline</>}
            </span>
          </div>
          <p className="text-sm text-muted-foreground mt-1">{items.length} total issues</p>
        </div>
        <div>
          <input ref={fileInputRef} type="file" accept="image/*" capture="environment" className="hidden" onChange={handleFileSelect} />
          <Button onClick={() => fileInputRef.current?.click()} className="gap-2">
            <Plus className="h-4 w-4" /> Report Issue
          </Button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input placeholder="Search issues..." value={search} onChange={(e) => setSearch(e.target.value)} className="pl-9" />
        </div>
        <select value={filterStatus} onChange={(e) => setFilterStatus(e.target.value)} className="px-3 py-2 rounded-md border border-border bg-background text-sm">
          <option value="all">All Status</option>
          <option value="reported">Reported</option>
          <option value="assigned">Assigned</option>
          <option value="in_progress">In Progress</option>
          <option value="resolved">Resolved</option>
        </select>
        <select value={filterType} onChange={(e) => setFilterType(e.target.value)} className="px-3 py-2 rounded-md border border-border bg-background text-sm">
          <option value="all">All Types</option>
          <option value="pothole">Pothole</option>
          <option value="garbage">Garbage</option>
          <option value="broken_streetlight">Street Light</option>
          <option value="waterlogging">Waterlogging</option>
          <option value="debris">Debris</option>
          <option value="sewage">Sewage</option>
          <option value="road_damage">Road Damage</option>
        </select>
      </div>

      {/* Upload Modal */}
      {showUploadModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <Card className="w-full max-w-lg mx-4 max-h-[90vh] overflow-y-auto">
            <CardContent className="p-6 space-y-4">
              <h2 className="text-lg font-bold">Report New Issue</h2>
              {previewUrl && (
                <div className="relative rounded-lg overflow-hidden border border-border">
                  <img src={previewUrl} alt="Preview" className="w-full h-48 object-cover" />
                  <button onClick={() => { setShowUploadModal(false); setSelectedFile(null); setPreviewUrl(null); }} className="absolute top-2 right-2 h-6 w-6 rounded-full bg-black/50 text-white flex items-center justify-center text-xs">×</button>
                </div>
              )}
              <div>
                <label className="text-sm font-medium">Description</label>
                <Input placeholder="Describe the issue (e.g., large pothole near bus stop)" value={description} onChange={(e) => setDescription(e.target.value)} className="mt-1" />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-sm font-medium">Latitude</label>
                  <Input value={lat} onChange={(e) => setLat(e.target.value)} className="mt-1" />
                </div>
                <div>
                  <label className="text-sm font-medium">Longitude</label>
                  <Input value={lon} onChange={(e) => setLon(e.target.value)} className="mt-1" />
                </div>
              </div>
              <div className="flex gap-3 justify-end">
                <Button variant="outline" onClick={() => { setShowUploadModal(false); setSelectedFile(null); setPreviewUrl(null); }}>Cancel</Button>
                <Button onClick={handleUpload} disabled={uploading || !selectedFile}>
                  {uploading ? "Classifying..." : "Submit Report"}
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Issue List */}
      {isLoading ? (
        <div className="space-y-4">
          {[1, 2, 3, 4].map((i) => (
            <Card key={i}>
              <CardContent className="p-5">
                <div className="space-y-3">
                  <div className="h-5 bg-muted rounded animate-pulse w-1/3" />
                  <div className="h-4 bg-muted rounded animate-pulse w-1/2" />
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-16">
          <div className="text-4xl mb-4">📭</div>
          <p className="text-muted-foreground">
            {items.length === 0 ? "No issues reported yet. Click Report Issue to get started." : "No issues match your filters."}
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map((issue) => (
            <Link key={issue.id} href={`/issues/${issue.id}`}>
              <Card className="hover:shadow-md hover:border-primary/30 transition-all cursor-pointer">
                <CardContent className="p-4">
                  <div className="flex items-center gap-4">
                    <div className="h-12 w-12 rounded-lg bg-muted flex items-center justify-center text-xl shrink-0">
                      {TYPE_ICONS[issue.issue_type] || "📋"}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-medium capitalize">{issue.issue_type.replace("_", " ")}</span>
                        {severityBadge(issue.severity)}
                        {statusBadge(issue.status)}
                        {issue.review_required && <Badge className="bg-orange-100 text-orange-700 border-0 text-xs">Review</Badge>}
                      </div>
                      {issue.description && (
                        <p className="text-sm text-muted-foreground mt-1 truncate">{issue.description}</p>
                      )}
                      <div className="flex items-center gap-4 mt-1 text-xs text-muted-foreground">
                        <span className="flex items-center gap-1"><MapPin className="h-3 w-3" /> Ward {issue.ward_id}</span>
                        <span>Confidence: {(issue.confidence * 100).toFixed(0)}%</span>
                        <span>{new Date(issue.created_at).toLocaleDateString()}</span>
                      </div>
                    </div>
                    <ChevronRight className="h-4 w-4 text-muted-foreground shrink-0" />
                  </div>
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
