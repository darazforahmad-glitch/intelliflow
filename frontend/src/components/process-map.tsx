"use client";

import "@xyflow/react/dist/style.css";

import {
  Background,
  Controls,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import clsx from "clsx";
import { Banknote, MessageCircle, Star } from "lucide-react";
import { useMemo } from "react";

import { APP_LABELS, minutesLabel } from "@/lib/format";
import type { ProcessMap, ProcessStep } from "@/lib/types";

type StepNodeData = { step: ProcessStep; rank: number | null };
type StepNode = Node<StepNodeData, "step">;

const TYPE_STYLE: Record<string, string> = {
  start: "border-slate-300 bg-slate-50",
  end: "border-slate-300 bg-slate-50",
  manual: "border-amber-400 bg-amber-50 ring-2 ring-amber-200",
  automated: "border-emerald-400 bg-emerald-50",
  human_only: "border-purple-300 bg-purple-50",
};
const TYPE_LABEL: Record<string, string> = {
  start: "Start",
  end: "End",
  manual: "Manual · can automate",
  automated: "Automated",
  human_only: "Human only",
};

function StepCard({ data }: NodeProps<StepNode>) {
  const { step, rank } = data;
  const isEvent = step.step_type === "start" || step.step_type === "end";
  const weekly = Number(step.weekly_minutes);
  return (
    <div className={clsx("w-64 rounded-2xl border px-3.5 py-3 shadow-sm", TYPE_STYLE[step.step_type])}>
      <Handle type="target" position={Position.Top} />
      <div className="flex items-center justify-between gap-2">
        <span className="text-[11px] font-semibold uppercase tracking-wide text-slate-600">
          {TYPE_LABEL[step.step_type]}
        </span>
        {rank && rank <= 3 ? (
          <span className="inline-flex items-center gap-1 rounded-full bg-brand-600 px-2 py-0.5 text-[11px] font-bold text-white">
            <Star className="size-3" aria-hidden /> #{rank}
          </span>
        ) : null}
      </div>
      <div className="mt-1 text-sm font-semibold leading-snug text-slate-900">{step.title}</div>
      <div className="mt-1 text-xs text-slate-600">
        {step.actor}
        {step.app && step.app !== "other" && step.app !== "none"
          ? ` · ${APP_LABELS[step.app] ?? step.app}`
          : ""}
      </div>
      {!isEvent ? (
        <div className="mt-2 flex flex-wrap items-center gap-1.5 text-xs">
          <span className="rounded-md bg-white/80 px-1.5 py-0.5 font-medium text-slate-700 ring-1 ring-slate-200">
            {Number(step.minutes_per_run)} min × {step.runs_per_week}/wk ={" "}
            <strong>{minutesLabel(weekly)}/wk</strong>
          </span>
          {step.involves_customer_messaging ? (
            <MessageCircle className="size-3.5 text-sky-600" aria-label="Messages customers" />
          ) : null}
          {step.involves_money ? (
            <Banknote className="size-3.5 text-amber-700" aria-label="Involves money" />
          ) : null}
        </div>
      ) : null}
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}

const nodeTypes = { step: StepCard };

export function ProcessMapFlow({ map, height = 560 }: { map: ProcessMap; height?: number }) {
  const ranks = useMemo(() => {
    const byStep = new Map<string, number>();
    for (const o of [...map.opportunities, ...map.other_opportunities])
      if (o.rank) byStep.set(o.step_id, o.rank);
    return byStep;
  }, [map]);
  const positions = useMemo(() => new Map(map.graph_json.nodes.map((n) => [n.id, n.position])), [map]);

  const nodes: StepNode[] = map.steps.map((step, index) => ({
    id: step.key,
    type: "step",
    position: positions.get(step.key) ?? { x: 0, y: index * 150 },
    data: { step, rank: ranks.get(step.id) ?? null },
    draggable: true,
  }));
  const edges: Edge[] = map.steps
    .filter((s) => s.predecessor_key)
    .map((s) => ({
      id: `e-${s.predecessor_key}-${s.key}`,
      source: s.predecessor_key!,
      target: s.key,
      type: "smoothstep",
      animated: s.step_type === "manual",
      markerEnd: { type: MarkerType.ArrowClosed, color: "#94a3b8" },
      style: { stroke: "#94a3b8", strokeWidth: 1.5 },
    }));

  return (
    <div
      style={{ height }}
      className="overflow-hidden rounded-2xl border border-slate-200 bg-white"
      aria-label={`Process map of ${map.name}`}
    >
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.15 }}
        minZoom={0.3}
        nodesConnectable={false}
        proOptions={{ hideAttribution: true }}
      >
        <Background gap={20} color="#e2e8f0" />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}

export function MapLegend() {
  return (
    <div className="flex flex-wrap gap-3 text-xs text-slate-600">
      {[
        ["border-amber-400 bg-amber-50", "Manual — can be automated"],
        ["border-purple-300 bg-purple-50", "Human only"],
        ["border-emerald-400 bg-emerald-50", "Already automated"],
        ["border-slate-300 bg-slate-50", "Start / end"],
      ].map(([style, label]) => (
        <span key={label} className="flex items-center gap-1.5">
          <span className={clsx("size-3 rounded border", style)} aria-hidden />
          {label}
        </span>
      ))}
    </div>
  );
}
