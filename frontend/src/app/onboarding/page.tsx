"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Bot, MessagesSquare, Plug, Workflow } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

import { Wordmark } from "@/components/logo";
import { Alert, Button, ButtonLink, Card, Input, Select, Spinner } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { fieldErrors, workspaceSchema, type FieldErrors } from "@/lib/schemas";
import { selectWorkspace, useHydrated, useMe, useSession } from "@/lib/session";
import type { Workspace } from "@/lib/types";

const TOUR = [
  {
    icon: Workflow,
    title: "1. Describe a process",
    text: "Chat with the Flow Mapper in English, Urdu or Roman Urdu. It draws your process and times every step.",
  },
  {
    icon: Bot,
    title: "2. Automate the top tasks",
    text: "Pick one of the three best opportunities. IntelliFlow builds the automation from tested blocks.",
  },
  {
    icon: Plug,
    title: "3. Connect your apps",
    text: "WhatsApp, Gmail, Google Sheets or a website form. Start in sandbox mode — nothing reaches customers.",
  },
  {
    icon: MessagesSquare,
    title: "4. Approve from your phone",
    text: "Replies to customers and big orders wait for your one-tap approval.",
  },
];

export default function OnboardingPage() {
  const hydrated = useHydrated();
  const session = useSession();
  const me = useMe();
  const router = useRouter();
  const client = useQueryClient();
  const [errors, setErrors] = useState<FieldErrors>({});
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [created, setCreated] = useState<Workspace | null>(null);

  useEffect(() => {
    if (hydrated && !session) router.replace("/login?next=/onboarding");
  }, [hydrated, session, router]);

  if (!hydrated || !session || me.isLoading) return <Spinner />;

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = Object.fromEntries(new FormData(event.currentTarget)) as Record<string, string>;
    const parsed = workspaceSchema.safeParse(form);
    if (!parsed.success) return setErrors(fieldErrors(parsed.error));
    setErrors({});
    setLoading(true);
    try {
      const workspace = await api.post<Workspace>("/workspaces", {
        ...parsed.data,
        business_type: parsed.data.business_type || null,
      });
      selectWorkspace(workspace.id);
      await client.invalidateQueries({ queryKey: ["me"] });
      setCreated(workspace);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl px-4 py-10">
      <Wordmark />
      {!created ? (
        <Card className="mt-8 p-6 sm:p-8">
          <h1 className="text-2xl font-bold text-slate-900">Set up your business</h1>
          <p className="mt-1 text-slate-600">
            Salaam {me.data?.full_name?.split(" ")[0]}! A workspace holds your processes, automations and
            team.
          </p>
          <form onSubmit={onSubmit} className="mt-6 grid gap-4 sm:grid-cols-2" noValidate>
            {error ? (
              <Alert tone="error" className="sm:col-span-2">
                {error}
              </Alert>
            ) : null}
            <div className="sm:col-span-2">
              <Input
                label="Business name"
                name="name"
                placeholder="e.g. Ayesha Boutique"
                error={errors.name}
                required
              />
            </div>
            <Input
              label="Type of business"
              name="business_type"
              placeholder="e.g. Online clothing seller"
              error={errors.business_type}
            />
            <Select
              label="Preferred language"
              name="language_pref"
              defaultValue="roman-ur"
              hint="You can always answer in any of these."
            >
              <option value="roman-ur">Roman Urdu</option>
              <option value="ur">اردو (Urdu)</option>
              <option value="en">English</option>
            </Select>
            <Select label="Timezone" name="timezone" defaultValue="Asia/Karachi">
              <option value="Asia/Karachi">Pakistan (Asia/Karachi)</option>
              <option value="Asia/Dubai">UAE (Asia/Dubai)</option>
              <option value="Europe/London">UK (Europe/London)</option>
              <option value="UTC">UTC</option>
            </Select>
            <div className="flex items-end sm:col-span-2">
              <Button type="submit" loading={loading} className="w-full sm:w-auto">
                Create workspace
              </Button>
            </div>
          </form>
        </Card>
      ) : (
        <div className="mt-8">
          <h1 className="text-2xl font-bold text-slate-900">{created.name} is ready 🎉</h1>
          <p className="mt-1 text-slate-600">
            Here is how IntelliFlow works — it takes about 15 minutes to your first automation.
          </p>
          <ol className="mt-6 grid gap-4 sm:grid-cols-2">
            {TOUR.map(({ icon: Icon, title, text }) => (
              <li key={title}>
                <Card className="h-full p-5">
                  <Icon className="size-6 text-brand-600" aria-hidden />
                  <h2 className="mt-3 font-semibold text-slate-900">{title}</h2>
                  <p className="mt-1 text-sm text-slate-600">{text}</p>
                </Card>
              </li>
            ))}
          </ol>
          <div className="mt-6 flex flex-wrap gap-2">
            <ButtonLink href="/flow-mapper?new=1" size="lg">
              Start my first interview
            </ButtonLink>
            <ButtonLink href="/dashboard" variant="secondary" size="lg">
              Go to the dashboard
            </ButtonLink>
          </div>
        </div>
      )}
    </div>
  );
}
