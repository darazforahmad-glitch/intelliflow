"use client";

import { ArrowDown, ArrowUp, Plus, Save, Trash2 } from "lucide-react";
import { useState } from "react";

import { errorMessage } from "@/lib/api";
import { APP_LABELS } from "@/lib/format";
import { useSaveMapVersion } from "@/lib/queries";
import type { ProcessMap, StepType } from "@/lib/types";

import { useToast } from "./toast";
import { Alert, Button, Card, CardHeader } from "./ui";

interface EditableStep {
  uid: string;
  title: string;
  actor: string;
  action: string;
  step_type: StepType;
  app: string;
  minutes_per_run: string;
  runs_per_week: string;
  involves_customer_messaging: boolean;
  involves_money: boolean;
}

const TYPES: { value: StepType; label: string }[] = [
  { value: "start", label: "Start" },
  { value: "manual", label: "Manual" },
  { value: "human_only", label: "Human only" },
  { value: "automated", label: "Automated" },
  { value: "end", label: "End" },
];
const cell =
  "min-h-11 w-full rounded-lg border border-slate-300 px-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-200";

/** REQ-FM-6/7: rename, re-type, reorder, add and delete steps; saving creates a new version. */
export function StepEditor({ map, onSaved }: { map: ProcessMap; onSaved: (newMapId: string) => void }) {
  const toast = useToast();
  const save = useSaveMapVersion(map.id);
  const [steps, setSteps] = useState<EditableStep[]>(() =>
    map.steps.map((s) => ({
      uid: s.id,
      title: s.title,
      actor: s.actor ?? "Owner",
      action: s.action ?? "",
      step_type: s.step_type,
      app: s.app ?? "other",
      minutes_per_run: String(Number(s.minutes_per_run ?? 0)),
      runs_per_week: String(s.runs_per_week ?? 0),
      involves_customer_messaging: s.involves_customer_messaging,
      involves_money: s.involves_money,
    })),
  );
  const [note, setNote] = useState("");
  const [problems, setProblems] = useState<string[]>([]);

  const update = (uid: string, patch: Partial<EditableStep>) =>
    setSteps((all) => all.map((s) => (s.uid === uid ? { ...s, ...patch } : s)));
  const move = (index: number, delta: number) =>
    setSteps((all) => {
      const next = [...all];
      const [item] = next.splice(index, 1);
      next.splice(index + delta, 0, item!);
      return next;
    });
  const addStep = () =>
    setSteps((all) => {
      const next = [...all];
      next.splice(Math.max(1, next.length - 1), 0, {
        uid: crypto.randomUUID(),
        title: "New step",
        actor: "Owner",
        action: "",
        step_type: "manual",
        app: "other",
        minutes_per_run: "2",
        runs_per_week: all[1]?.runs_per_week ?? "10",
        involves_customer_messaging: false,
        involves_money: false,
      });
      return next;
    });

  async function onSave() {
    setProblems([]);
    try {
      const saved = await save.mutateAsync({
        note: note || undefined,
        steps: steps.map(({ uid: _uid, ...s }) => ({
          ...s,
          minutes_per_run: Number(s.minutes_per_run) || 0,
          runs_per_week: Number(s.runs_per_week) || 0,
        })),
      });
      toast(`Saved as version ${saved.version}. Opportunities were re-ranked.`);
      onSaved(saved.id);
    } catch (error) {
      const details = (error as { details?: unknown }).details;
      setProblems(Array.isArray(details) ? (details as string[]) : [errorMessage(error)]);
    }
  }

  return (
    <Card>
      <CardHeader
        title="Edit steps"
        description="Fix names, timings and types. Saving keeps the old version and re-ranks opportunities."
        actions={
          <Button variant="secondary" icon={<Plus className="size-4" />} onClick={addStep}>
            Add step
          </Button>
        }
      />
      {problems.length ? (
        <Alert tone="error" className="mx-5 mt-4" title="Please fix these first">
          <ul className="list-disc pl-5">
            {problems.map((p) => (
              <li key={p}>{p}</li>
            ))}
          </ul>
        </Alert>
      ) : null}
      <div className="overflow-x-auto">
        <table className="w-full min-w-[56rem] text-sm">
          <thead className="text-left text-xs uppercase tracking-wide text-slate-600">
            <tr>
              <th className="px-3 py-2">#</th>
              <th className="px-2 py-2">Step</th>
              <th className="px-2 py-2">Who</th>
              <th className="px-2 py-2">Type</th>
              <th className="px-2 py-2">App</th>
              <th className="px-2 py-2">Min/run</th>
              <th className="px-2 py-2">Runs/week</th>
              <th className="px-2 py-2">Risk</th>
              <th className="px-2 py-2 sr-only">Actions</th>
            </tr>
          </thead>
          <tbody>
            {steps.map((step, index) => (
              <tr key={step.uid} className="border-t border-slate-100 align-middle">
                <td className="px-3 py-2 text-slate-500">{index + 1}</td>
                <td className="px-2 py-2">
                  <input
                    aria-label={`Step ${index + 1} title`}
                    className={cell}
                    value={step.title}
                    onChange={(e) => update(step.uid, { title: e.target.value })}
                  />
                </td>
                <td className="w-32 px-2 py-2">
                  <input
                    aria-label={`Step ${index + 1} actor`}
                    className={cell}
                    value={step.actor}
                    onChange={(e) => update(step.uid, { actor: e.target.value })}
                  />
                </td>
                <td className="w-36 px-2 py-2">
                  <select
                    aria-label={`Step ${index + 1} type`}
                    className={cell}
                    value={step.step_type}
                    onChange={(e) => update(step.uid, { step_type: e.target.value as StepType })}
                  >
                    {TYPES.map((t) => (
                      <option key={t.value} value={t.value}>
                        {t.label}
                      </option>
                    ))}
                  </select>
                </td>
                <td className="w-36 px-2 py-2">
                  <select
                    aria-label={`Step ${index + 1} app`}
                    className={cell}
                    value={step.app}
                    onChange={(e) => update(step.uid, { app: e.target.value })}
                  >
                    {Object.entries(APP_LABELS).map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </select>
                </td>
                <td className="w-24 px-2 py-2">
                  <input
                    aria-label={`Step ${index + 1} minutes per run`}
                    type="number"
                    min={0}
                    max={600}
                    step="0.5"
                    className={cell}
                    value={step.minutes_per_run}
                    onChange={(e) => update(step.uid, { minutes_per_run: e.target.value })}
                  />
                </td>
                <td className="w-24 px-2 py-2">
                  <input
                    aria-label={`Step ${index + 1} runs per week`}
                    type="number"
                    min={0}
                    max={10000}
                    className={cell}
                    value={step.runs_per_week}
                    onChange={(e) => update(step.uid, { runs_per_week: e.target.value })}
                  />
                </td>
                <td className="w-40 px-2 py-2">
                  <label className="flex items-center gap-1.5 text-xs">
                    <input
                      type="checkbox"
                      checked={step.involves_customer_messaging}
                      onChange={(e) => update(step.uid, { involves_customer_messaging: e.target.checked })}
                    />
                    Messages customers
                  </label>
                  <label className="mt-1 flex items-center gap-1.5 text-xs">
                    <input
                      type="checkbox"
                      checked={step.involves_money}
                      onChange={(e) => update(step.uid, { involves_money: e.target.checked })}
                    />
                    Involves money
                  </label>
                </td>
                <td className="w-32 px-2 py-2">
                  <div className="flex">
                    <button
                      type="button"
                      className="grid size-9 place-items-center rounded-lg hover:bg-slate-100 disabled:opacity-30"
                      onClick={() => move(index, -1)}
                      disabled={index === 0}
                      aria-label={`Move step ${index + 1} up`}
                    >
                      <ArrowUp className="size-4" />
                    </button>
                    <button
                      type="button"
                      className="grid size-9 place-items-center rounded-lg hover:bg-slate-100 disabled:opacity-30"
                      onClick={() => move(index, 1)}
                      disabled={index === steps.length - 1}
                      aria-label={`Move step ${index + 1} down`}
                    >
                      <ArrowDown className="size-4" />
                    </button>
                    <button
                      type="button"
                      className="grid size-9 place-items-center rounded-lg text-red-600 hover:bg-red-50 disabled:opacity-30"
                      onClick={() => setSteps((all) => all.filter((s) => s.uid !== step.uid))}
                      disabled={steps.length <= 3}
                      aria-label={`Delete step ${index + 1}`}
                    >
                      <Trash2 className="size-4" />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex flex-wrap items-end gap-3 border-t border-slate-100 px-5 py-4">
        <label className="min-w-64 flex-1 text-sm">
          <span className="font-medium text-slate-800">What did you change? (optional)</span>
          <input
            className={`${cell} mt-1`}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="e.g. Corrected packing time"
          />
        </label>
        <Button icon={<Save className="size-4" />} onClick={onSave} loading={save.isPending}>
          Save as version {map.versions.length + 1}
        </Button>
      </div>
    </Card>
  );
}
