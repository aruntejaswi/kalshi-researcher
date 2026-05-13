import { create } from "zustand";

interface SkillState {
  active: Set<string>;
  toggle: (id: string) => void;
  setActive: (ids: string[]) => void;
}

export const useSkillStore = create<SkillState>((set) => ({
  active: new Set<string>(),
  toggle: (id) =>
    set((s) => {
      const next = new Set(s.active);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return { active: next };
    }),
  setActive: (ids) => set({ active: new Set(ids) }),
}));
