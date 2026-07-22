"use client";

import { useEngineers } from "@/queries/index";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Users, Wrench, Clock } from "lucide-react";

export default function EngineersPage() {
  const { data: engineers, isLoading } = useEngineers();

  return (
    <div className="space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-bold">Engineers</h1>
        <p className="text-sm text-muted-foreground mt-1">Field engineers and their current workload</p>
      </div>

      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[1, 2, 3].map((i) => (
            <Card key={i}>
              <CardContent className="p-6">
                <div className="h-24 bg-muted rounded animate-pulse" />
              </CardContent>
            </Card>
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {engineers?.map((eng) => {
            const workloadPct = eng.max_workload > 0 ? (eng.current_workload / eng.max_workload) * 100 : 0;
            const workloadColor = workloadPct > 80 ? "bg-red-500" : workloadPct > 50 ? "bg-yellow-500" : "bg-green-500";
            
            return (
              <Card key={eng.id} className="hover:shadow-md transition-shadow">
                <CardHeader className="pb-3">
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-base flex items-center gap-2">
                      <div className="h-8 w-8 rounded-full bg-primary/10 flex items-center justify-center">
                        <Users className="h-4 w-4 text-primary" />
                      </div>
                      Engineer #{eng.id}
                    </CardTitle>
                    <Badge variant={eng.is_available ? "default" : "secondary"}>
                      {eng.is_available ? "Available" : "Busy"}
                    </Badge>
                  </div>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="space-y-2">
                    <div className="flex justify-between text-sm">
                      <span className="text-muted-foreground flex items-center gap-1">
                        <Wrench className="h-3 w-3" /> Specialization
                      </span>
                      <span className="capitalize font-medium">{eng.specialization?.replace("_", " ") || "General"}</span>
                    </div>
                    <div className="flex justify-between text-sm">
                      <span className="text-muted-foreground">Ward</span>
                      <span className="font-medium">#{eng.ward_id}</span>
                    </div>
                    <div className="flex justify-between text-sm">
                      <span className="text-muted-foreground flex items-center gap-1">
                        <Clock className="h-3 w-3" /> Avg Resolution
                      </span>
                      <span className="font-medium">{eng.avg_resolution_hours.toFixed(1)}h</span>
                    </div>
                  </div>

                  <div className="space-y-1.5">
                    <div className="flex justify-between text-xs">
                      <span className="text-muted-foreground">Workload</span>
                      <span className="font-medium">{eng.current_workload}/{eng.max_workload} issues</span>
                    </div>
                    <div className="h-2 rounded-full bg-muted overflow-hidden">
                      <div className={`h-full rounded-full transition-all ${workloadColor}`} style={{ width: `${Math.min(workloadPct, 100)}%` }} />
                    </div>
                  </div>
                </CardContent>
              </Card>
            );
          })}
          {engineers?.length === 0 && (
            <div className="col-span-full text-center py-16">
              <div className="text-4xl mb-4">👷</div>
              <p className="text-muted-foreground">No engineers registered yet.</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
