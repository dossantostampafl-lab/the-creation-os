export type SystemTotals = {
  missions: number;
  tasks: number;
  universes: number;
  agents: number;
};

export function systemPageCount(totals: SystemTotals, pageSize: number): number {
  return Math.max(1, Math.ceil(Math.max(totals.missions, totals.tasks) / pageSize));
}
