"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import dynamic from "next/dynamic";
import exifr from "exifr";
import { useIssues, useUploadIssueMutation, useWards, useMe } from "@/queries/index";
import { useNotifications } from "@/lib/notifications";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { IssueTypeIcon } from "@/components/shared/issue-icon";
import { QueryError } from "@/components/shared/query-error";
import { SortHeaders } from "@/components/shared/sort-headers";
import { ListPager } from "@/components/shared/list-pager";
import { useInfiniteScroll } from "@/hooks/use-infinite-scroll";
import { toast } from "sonner";
import {
  ChevronRight,
  ArrowDownToLine,
  Inbox,
  LocateFixed,
  MapPin,
  Plus,
  Rows3,
  Search,
  Wifi,
  WifiOff,
} from "lucide-react";
import {
  formatDate,
  humanize,
  severityMeta,
  STATUS_META,
  STATUS_ORDER,
} from "@/lib/format";
import type { Issue } from "@/lib/api";

const LocationPicker = dynamic(
  () => import("@/components/maps/LocationPicker").then((m) => m.LocationPicker),
  {
    ssr: false,
    loading: () => <div className="h-[260px] animate-pulse rounded-lg bg-muted" />,
  }
);

const TYPE_OPTIONS = [
  "pothole",
  "garbage",
  "debris",
];

const PAGE_SIZE = 10;

function newIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `k-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function StatusBadge({ status }: { status: string }) {
  const meta = STATUS_META[status] ?? {
    label: humanize(status),
    pill: "bg-muted text-muted-foreground ring-muted",
  };
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset ${meta.pill}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${meta.dot ?? "bg-current"}`} />
      {meta.label}
    </span>
  );
}

function IssueRow({ issue, wardName }: { issue: Issue; wardName: string }) {
  const sev = severityMeta(issue.severity);
  return (
    <Link
      href={`/issues/${issue.id}`}
      className="group flex items-center gap-4 px-5 py-4 transition-colors hover:bg-muted/40"
    >
      <IssueTypeIcon type={issue.issue_type} />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-medium">{humanize(issue.issue_type)}</span>
          {issue.review_required && (
            <Badge variant="outline" className="border-orange-200 bg-orange-50 text-orange-700">
              Review required
            </Badge>
          )}
        </div>
        {issue.description && (
          <p className="mt-0.5 truncate text-sm text-muted-foreground">
            {issue.description}
          </p>
        )}
        <div className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
          <span className="inline-flex items-center gap-1">
            <MapPin className="h-3 w-3" />
            {wardName}
          </span>
          <span>{formatDate(issue.created_at)}</span>
          <span className="text-muted-foreground/70">
            Confidence {(issue.confidence * 100).toFixed(0)}%
          </span>
        </div>
      </div>
      <div className="hidden shrink-0 items-center gap-2 sm:flex">
        <StatusBadge status={issue.status} />
        <span
          className={`rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset ${sev.pill}`}
        >
          {sev.label}
        </span>
      </div>
      <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5" />
    </Link>
  );
}

export default function IssuesPage() {
  const { data: currentUser } = useMe();

  // Filter / sort / page state lives here and is pushed to the server: the
  // list pages over the *whole* table rather than slicing whatever first page
  // happened to be fetched, so filters and totals stay correct past page one.
  const [search, setSearch] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [filterStatus, setFilterStatus] = useState<string>("all");
  const [filterType, setFilterType] = useState<string>("all");
  const [sort, setSort] = useState("created_at");
  const [order, setOrder] = useState<"asc" | "desc">("desc");
  const [page, setPage] = useState(1);
  // "pages" = classic numbered pager; "scroll" = append the next page as the
  // sentinel scrolls into view and drop the pager. Both drive the same
  // server-side query; only the accumulation differs.
  const [loadMode, setLoadMode] = useState<"pages" | "scroll">("pages");

  const queryParams = useMemo(
    () => ({
      skip: (page - 1) * PAGE_SIZE,
      limit: PAGE_SIZE,
      search: search || undefined,
      status: filterStatus !== "all" ? filterStatus : undefined,
      issue_type: filterType !== "all" ? filterType : undefined,
      sort,
      order,
    }),
    [page, search, filterStatus, filterType, sort, order]
  );

  const { data, isLoading, isError, error, refetch, isFetching } = useIssues(queryParams);
  const uploadMutation = useUploadIssueMutation();
  const { data: wards } = useWards();

  // Accumulated rows for scroll mode. Reset whenever the filter/sort identity
  // changes (a new result set must start from scratch), and append each newly
  // fetched page otherwise. Keyed on the serialized filter set so a page-2
  // fetch appends but a new search replaces.
  const filterKey = `${search}|${filterStatus}|${filterType}|${sort}|${order}|${loadMode}`;
  const [accumulated, setAccumulated] = useState<Issue[]>([]);
  useEffect(() => {
    setAccumulated([]);
    setPage(1);
  }, [filterKey]);
  useEffect(() => {
    if (loadMode !== "scroll" || !data) return;
    setAccumulated((prev) => {
      const base = page === 1 ? [] : prev;
      const seen = new Set(base.map((i) => i.id));
      return [...base, ...data.items.filter((i) => !seen.has(i.id))];
    });
  }, [data, loadMode, page]);

  const wardName = useCallback(
    (id: number) => wards?.find((w) => w.id === id)?.name ?? `Ward ${id}`,
    [wards]
  );

  // Debounce the search box so each keystroke does not fire a request; the
  // committed `search` is what the query key depends on.
  useEffect(() => {
    const t = setTimeout(() => {
      setSearch(searchInput);
      setPage(1);
    }, 300);
    return () => clearTimeout(t);
  }, [searchInput]);

  const [showUploadModal, setShowUploadModal] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [description, setDescription] = useState("");
  const [lat, setLat] = useState("");
  const [lon, setLon] = useState("");
  const [locationSource, setLocationSource] = useState<"photo" | "device" | "pin" | null>(null);
  const [locating, setLocating] = useState(false);
  const [uploading, setUploading] = useState(false);

  const [showRejectionDialog, setShowRejectionDialog] = useState(false);
  const [rejectionReason, setRejectionReason] = useState("");
  const [forceSubmitting, setForceSubmitting] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  // Idempotency identity of the in-flight upload: stable across retries of the
  // same logical request (so a flaky-network retry dedupes) but rotated when
  // the file changes or when the submit mode flips to the forced override
  // (that is a different request and must not collide with the rejected one).
  const idempotencyRef = useRef<{ key: string; force: boolean } | null>(null);

  // Live-feed status comes from the single app-wide socket owned by
  // <IssueStream /> in the shell, so this page no longer opens its own
  // connection just to know whether updates are flowing.
  const { connected: isConnected } = useNotifications();

  useEffect(() => {
    if (typeof window === "undefined") return;
    const q = new URLSearchParams(window.location.search).get("q");
    if (q) setSearch(q);
  }, []);

  const extractGpsFromPhoto = async (
    file: File
  ): Promise<{ latitude: number; longitude: number } | null> => {
    try {
      const gps = await exifr.gps(file);
      if (gps && typeof gps.latitude === "number" && typeof gps.longitude === "number") {
        return { latitude: gps.latitude, longitude: gps.longitude };
      }
    } catch {
      /* no GPS in EXIF */
    }
    return null;
  };

  const getDeviceLocation = async (): Promise<{ latitude: number; longitude: number } | null> => {
    try {
      const pos = await new Promise<GeolocationPosition>((resolve, reject) => {
        navigator.geolocation.getCurrentPosition(resolve, reject, {
          timeout: 8000,
          maximumAge: 30000,
        });
      });
      return { latitude: pos.coords.latitude, longitude: pos.coords.longitude };
    } catch {
      return null;
    }
  };

  const parseLatLon = (): { lat: number; lon: number } | null => {
    const latNum = parseFloat(lat);
    const lonNum = parseFloat(lon);
    if (Number.isNaN(latNum) || Number.isNaN(lonNum)) return null;
    if (latNum < -90 || latNum > 90 || lonNum < -180 || lonNum > 180) return null;
    return { lat: latNum, lon: lonNum };
  };

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    idempotencyRef.current = null;
    setSelectedFile(file);
    setPreviewUrl(URL.createObjectURL(file));
    setLat("");
    setLon("");
    setLocationSource(null);
    setShowUploadModal(true);

    const gps = await extractGpsFromPhoto(file);
    if (gps) {
      setLat(gps.latitude.toFixed(6));
      setLon(gps.longitude.toFixed(6));
      setLocationSource("photo");
    }
  };

  const handleUseDeviceLocation = async () => {
    setLocating(true);
    const loc = await getDeviceLocation();
    setLocating(false);
    if (loc) {
      setLat(loc.latitude.toFixed(6));
      setLon(loc.longitude.toFixed(6));
      setLocationSource("device");
      toast.success("Location set from your device GPS");
    } else {
      toast.error("Could not get your location. Place a pin on the map instead.");
    }
  };

  const currentIdempotencyKey = (force: boolean): string => {
    if (!idempotencyRef.current || idempotencyRef.current.force !== force) {
      idempotencyRef.current = { key: newIdempotencyKey(), force };
    }
    return idempotencyRef.current.key;
  };

  const handleUpload = async (force = false) => {
    if (!selectedFile) return;
    setUploading(true);
    try {
      let loc = parseLatLon();
      if (!loc) {
        const device = await getDeviceLocation();
        if (device) {
          loc = { lat: device.latitude, lon: device.longitude };
          setLat(device.latitude.toFixed(6));
          setLon(device.longitude.toFixed(6));
          setLocationSource("device");
        }
      }
      if (!loc) {
        toast.error("Location is required. Use 'Use my location' or place a pin on the map.");
        setUploading(false);
        return;
      }

      await uploadMutation.mutateAsync({
        file: selectedFile,
        latitude: loc.lat,
        longitude: loc.lon,
        description,
        force_submit: force,
        idempotencyKey: currentIdempotencyKey(force),
      });
      toast.success(force ? "Issue submitted for review!" : "Issue reported! AI classification in progress...");
      resetModal();
    } catch (error: unknown) {
      const msg = error instanceof Error ? error.message : "Upload failed";
      if (msg.includes("does not appear to be a civic issue")) {
        setRejectionReason(msg);
        setShowRejectionDialog(true);
      } else {
        toast.error(msg);
      }
    } finally {
      setUploading(false);
    }
  };

  const resetModal = () => {
    setShowUploadModal(false);
    setSelectedFile(null);
    setPreviewUrl(null);
    setDescription("");
    setLat("");
    setLon("");
    setLocationSource(null);
    idempotencyRef.current = null;
  };

  const resetRejection = () => {
    setShowRejectionDialog(false);
    setRejectionReason("");
  };

  const items = useMemo(() => data?.items ?? [], [data]);
  const total = data?.total ?? 0;

  // Scroll mode renders the accumulated set; pages mode renders the last page.
  const displayItems = loadMode === "scroll" ? accumulated : items;
  const hasMore = loadMode === "scroll" && displayItems.length < total;

  const sentinelRef = useInfiniteScroll(
    () => setPage((p) => p + 1),
    { disabled: !hasMore || isFetching }
  );

  const filtersActive = Boolean(search || filterStatus !== "all" || filterType !== "all");

  const clearFilters = () => {
    setSearchInput("");
    setSearch("");
    setFilterStatus("all");
    setFilterType("all");
    setPage(1);
  };

  return (
    <div className="space-y-6">
      {/* Toolbar */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <div>
            <p className="text-sm text-muted-foreground">
              {filtersActive ? `${total} matching issues` : `${total} total issues`}
            </p>
          </div>
          <span
            className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset ${
              isConnected
                ? "bg-emerald-50 text-emerald-700 ring-emerald-600/20"
                : "bg-muted text-muted-foreground ring-border"
            }`}
          >
            {isConnected ? (
              <>
                <Wifi className="h-3 w-3" /> Live
              </>
            ) : (
              <>
                <WifiOff className="h-3 w-3" /> Offline
              </>
            )}
          </span>
        </div>

        <div className="flex items-center gap-3">
          <div className="relative flex-1 sm:w-64 sm:flex-none">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              placeholder="Search issues…"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              className="pl-9"
            />
          </div>
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            capture="environment"
            className="hidden"
            onChange={handleFileSelect}
          />
          {currentUser?.role !== "viewer" && (
            <Button
              onClick={() => fileInputRef.current?.click()}
              className="gap-2"
            >
              <Plus className="h-4 w-4" />
              Report Issue
            </Button>
          )}
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <Select
          value={filterStatus}
          onValueChange={(v) => {
            setFilterStatus(v);
            setPage(1);
          }}
        >
          <SelectTrigger className="w-[180px]">
            <SelectValue placeholder="All statuses" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All statuses</SelectItem>
            {STATUS_ORDER.map((s) => (
              <SelectItem key={s} value={s}>
                {STATUS_META[s].label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select
          value={filterType}
          onValueChange={(v) => {
            setFilterType(v);
            setPage(1);
          }}
        >
          <SelectTrigger className="w-[180px]">
            <SelectValue placeholder="All types" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All types</SelectItem>
            {TYPE_OPTIONS.map((t) => (
              <SelectItem key={t} value={t}>
                {humanize(t)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        {filtersActive && (
          <Button variant="ghost" size="sm" onClick={clearFilters}>
            Clear filters
          </Button>
        )}

        <SortHeaders
          className="ml-auto"
          sort={sort}
          order={order}
          onChange={(s, o) => {
            setSort(s);
            setOrder(o);
            setPage(1);
          }}
          options={[
            { key: "created_at", label: "Newest" },
            { key: "severity", label: "Severity" },
            { key: "confidence", label: "Confidence" },
          ]}
        />

        <Button
          variant="outline"
          size="sm"
          className="gap-1.5"
          onClick={() => {
            setLoadMode((m) => (m === "pages" ? "scroll" : "pages"));
            setPage(1);
          }}
          title="Toggle between page numbers and load-on-scroll"
        >
          {loadMode === "pages" ? (
            <>
              <ArrowDownToLine className="h-3.5 w-3.5" />
              Load on scroll
            </>
          ) : (
            <>
              <Rows3 className="h-3.5 w-3.5" />
              Page numbers
            </>
          )}
        </Button>
      </div>

      {/* List */}
      <Card>
        {isError ? (
          <QueryError
            error={error}
            onRetry={() => refetch()}
            title="Could not load issues"
            className="border-0 bg-transparent"
          />
        ) : isLoading ? (
          <div className="space-y-1 p-2">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="flex items-center gap-4 px-4 py-4">
                <Skeleton className="h-10 w-10 rounded-xl" />
                <div className="flex-1 space-y-2">
                  <Skeleton className="h-4 w-1/3" />
                  <Skeleton className="h-3 w-1/2" />
                </div>
                <Skeleton className="hidden h-5 w-24 rounded-full sm:block" />
              </div>
            ))}
          </div>
        ) : displayItems.length === 0 ? (
          <div className="flex flex-col items-center justify-center px-6 py-16 text-center">
            <div className="flex h-14 w-14 items-center justify-center rounded-full bg-muted">
              <Inbox className="h-7 w-7 text-muted-foreground" />
            </div>
            <h3 className="mt-4 text-base font-semibold">
              {total === 0 && !filtersActive ? "No issues reported yet" : "No issues match your filters"}
            </h3>
            <p className="mt-1 max-w-sm text-sm text-muted-foreground">
              {total === 0 && !filtersActive
                ? "Click 'Report Issue' to submit the first report from the field."
                : "Try adjusting your search or clearing the active filters."}
            </p>
            {filtersActive && (
              <Button variant="outline" size="sm" className="mt-4" onClick={clearFilters}>
                Clear filters
              </Button>
            )}
          </div>
        ) : (
          <>
            <div className={`divide-y transition-opacity ${isFetching && loadMode === "pages" ? "opacity-60" : ""}`}>
              {displayItems.map((issue) => (
                <IssueRow
                  key={issue.id}
                  issue={issue}
                  wardName={wardName(issue.ward_id)}
                />
              ))}
            </div>
            {loadMode === "scroll" ? (
              <div className="flex flex-col items-center gap-3 py-6">
                {isFetching && (
                  <div className="flex items-center gap-2 text-sm text-muted-foreground">
                    <span className="size-4 animate-spin rounded-full border-2 border-primary border-t-transparent" />
                    Loading more…
                  </div>
                )}
                {hasMore ? (
                  <div ref={sentinelRef} className="h-1 w-full" aria-hidden />
                ) : (
                  <p className="text-xs text-muted-foreground">You&apos;ve reached the end · {total} issues</p>
                )}
              </div>
            ) : (
              <ListPager page={page} total={total} pageSize={PAGE_SIZE} onPageChange={setPage} />
            )}
          </>
        )}
      </Card>

      {/* Report dialog */}
      <Dialog open={showUploadModal} onOpenChange={(o) => !o && resetModal()}>
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Report New Issue</DialogTitle>
            <DialogDescription>
              Upload a photo of the issue and set its location.
            </DialogDescription>
          </DialogHeader>

          {previewUrl && (
            <div className="relative overflow-hidden rounded-xl border">
              {/* eslint-disable-next-line @next/next/no-img-element -- previewUrl is a blob: object URL (URL.createObjectURL); next/image cannot render blob: sources. */}
              <img
                src={previewUrl}
                alt="Preview"
                className="h-44 w-full object-cover"
              />
            </div>
          )}

          <div className="space-y-2">
            <Label htmlFor="description">Description</Label>
            <Textarea
              id="description"
              placeholder="Describe the issue (e.g., large pothole near the bus stop)"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
            />
          </div>

          <div className="space-y-3">
            <div className="flex items-center justify-between gap-3">
              <Label>Location</Label>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={handleUseDeviceLocation}
                disabled={locating}
                className="gap-1.5"
              >
                <LocateFixed className="h-3.5 w-3.5" />
                {locating ? "Getting location…" : "Use my location"}
              </Button>
            </div>
            <LocationPicker
              lat={lat ? parseFloat(lat) : null}
              lng={lon ? parseFloat(lon) : null}
              onChange={(l, n) => {
                setLat(l.toFixed(6));
                setLon(n.toFixed(6));
                setLocationSource("pin");
              }}
            />
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="lat">Latitude</Label>
                <Input
                  id="lat"
                  value={lat}
                  onChange={(e) => setLat(e.target.value)}
                  placeholder="22.3072"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="lon">Longitude</Label>
                <Input
                  id="lon"
                  value={lon}
                  onChange={(e) => setLon(e.target.value)}
                  placeholder="73.1812"
                />
              </div>
            </div>
            <p className="text-xs text-muted-foreground">
              {locationSource === "photo"
                ? "Location from GPS embedded in the photo."
                : locationSource === "device"
                  ? "Location from your device GPS."
                  : locationSource === "pin"
                    ? "Location set from the map pin."
                    : "Tap the map to set the exact location. GPS from your photo or device is used automatically when available."}
            </p>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={resetModal}>
              Cancel
            </Button>
            <Button onClick={() => handleUpload()} disabled={uploading || !selectedFile}>
              {uploading ? "Classifying…" : "Submit Report"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Rejection dialog — shown when AI rejects a photo */}
      <Dialog open={showRejectionDialog} onOpenChange={(o) => !o && resetRejection()}>
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="text-orange-600">Image Not Recognised</DialogTitle>
            <DialogDescription>
              Our AI system could not identify a civic issue in this image. This
              can happen with blurry, dark, or unrelated photos.
            </DialogDescription>
          </DialogHeader>

          {previewUrl && (
            <div className="relative overflow-hidden rounded-xl border">
              {/* eslint-disable-next-line @next/next/no-img-element -- previewUrl is a blob: object URL (URL.createObjectURL); next/image cannot render blob: sources. */}
              <img
                src={previewUrl}
                alt="Your upload"
                className="h-40 w-full object-cover opacity-80"
              />
            </div>
          )}

          <p className="text-sm text-muted-foreground">{rejectionReason}</p>

          <DialogFooter className="flex-col gap-2 sm:flex-row">
            <Button
              variant="outline"
              onClick={() => {
                resetRejection();
                resetModal();
              }}
            >
              Discard
            </Button>
            <Button
              variant="default"
              disabled={forceSubmitting}
              onClick={async () => {
                setForceSubmitting(true);
                await handleUpload(true);
                setForceSubmitting(false);
                resetRejection();
              }}
            >
              {forceSubmitting ? "Submitting…" : "Submit anyway (reviewed by admin)"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
