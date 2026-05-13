import { useQuery } from "@tanstack/react-query";
import { useSkillStore } from "@/store/skillStore";

interface Skill {
  id: string;
  name: string;
  description: string;
}

async function fetchSkills(): Promise<Skill[]> {
  const r = await fetch("/api/skills");
  if (!r.ok) throw new Error(`skills ${r.status}`);
  const j = await r.json();
  return j.skills ?? [];
}

export function SkillSidebar() {
  const { data, isLoading } = useQuery({ queryKey: ["skills"], queryFn: fetchSkills });
  const active = useSkillStore((s) => s.active);
  const toggle = useSkillStore((s) => s.toggle);

  return (
    <aside className="w-64 shrink-0 border-r border-border bg-card/40 p-4">
      <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        Active Skills
      </h2>
      {isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
      <ul className="space-y-3">
        {data?.map((s) => (
          <li key={s.id}>
            <label className="flex cursor-pointer items-start gap-2">
              <input
                type="checkbox"
                className="mt-1 h-4 w-4 accent-emerald-500"
                checked={active.has(s.id)}
                onChange={() => toggle(s.id)}
              />
              <span className="flex-1">
                <span className="block text-sm font-medium">{s.name}</span>
                <span className="block text-xs text-muted-foreground">{s.description}</span>
              </span>
            </label>
          </li>
        ))}
      </ul>
    </aside>
  );
}
