import { UserPlus, Shield, Users, KeyRound, Search, MoreHorizontal, Check, Minus } from "lucide-react";
import { Card, CardTitle, PageHeader, PrimaryButton, GhostButton, Badge, cx } from "@/components/ui";

const members = [
  { name: "Shivam Kumar", email: "s.kumar@kimbal.io", role: "Admin", team: "DevSecOps", active: "Now", tone: "brand" as const },
  { name: "Ananya Rao", email: "a.rao@kimbal.io", role: "Editor", team: "Engineering", active: "5 min ago", tone: "blue" as const },
  { name: "Rahul Mehta", email: "r.mehta@kimbal.io", role: "Viewer", team: "Support", active: "1 hr ago", tone: "gray" as const },
  { name: "Priya Nair", email: "p.nair@kimbal.io", role: "Editor", team: "Product", active: "2 hrs ago", tone: "blue" as const },
  { name: "Dev Sharma", email: "d.sharma@kimbal.io", role: "Admin", team: "SRE", active: "Yesterday", tone: "brand" as const },
  { name: "Meera Iyer", email: "m.iyer@kimbal.io", role: "Viewer", team: "People Ops", active: "2 days ago", tone: "gray" as const },
];

const roles = [
  { role: "Admin", desc: "Full control incl. sources & settings", members: 4 },
  { role: "Editor", desc: "Curate content, manage answers", members: 26 },
  { role: "Viewer", desc: "Ask questions, browse knowledge", members: 582 },
];

const matrix = [
  { perm: "Ask Kimbal & search", admin: true, editor: true, viewer: true },
  { perm: "Save & share answers", admin: true, editor: true, viewer: true },
  { perm: "Curate documents & fix health issues", admin: true, editor: true, viewer: false },
  { perm: "Connect / remove data sources", admin: true, editor: false, viewer: false },
  { perm: "Manage members & roles", admin: true, editor: false, viewer: false },
  { perm: "Change RAG & model settings", admin: true, editor: false, viewer: false },
];

function Mark({ on }: { on: boolean }) {
  return on ? (
    <span className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-emerald-50 text-emerald-500">
      <Check size={12} strokeWidth={3} />
    </span>
  ) : (
    <span className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-canvas text-ink-300">
      <Minus size={12} strokeWidth={3} />
    </span>
  );
}

export default function AccessControlPage() {
  return (
    <div>
      <PageHeader
        title="Access Control"
        subtitle="Manage who can see, curate and administer organizational knowledge."
        actions={
          <div className="flex gap-2.5">
            <GhostButton><KeyRound size={15} /> SSO: Okta connected</GhostButton>
            <PrimaryButton><UserPlus size={15} /> Invite Member</PrimaryButton>
          </div>
        }
      />

      <div className="grid grid-cols-3 gap-5 animate-rise-1">
        {roles.map((r) => (
          <Card key={r.role} className="flex items-center gap-4 p-5">
            <span className="flex h-11 w-11 items-center justify-center rounded-[13px] bg-brand-50 text-brand-500">
              <Shield size={19} />
            </span>
            <div className="flex-1">
              <p className="text-[15px] font-bold text-ink-900">{r.role}</p>
              <p className="text-[12px] text-ink-500">{r.desc}</p>
            </div>
            <p className="text-[22px] font-bold text-ink-900">{r.members}</p>
          </Card>
        ))}
      </div>

      <div className="mt-5 grid grid-cols-12 gap-5 animate-rise-2">
        <Card className="col-span-7">
          <div className="flex items-center gap-3 p-5 pb-3">
            <CardTitle icon={Users} title="Members" />
            <label className="ml-auto flex h-9 w-56 cursor-text items-center gap-2 rounded-[9px] border border-line bg-canvas px-3 transition focus-within:border-brand-300 focus-within:bg-white">
              <Search size={14} className="text-ink-400" />
              <input placeholder="Search members..." className="min-w-0 flex-1 bg-transparent text-[12.5px] outline-none placeholder:text-ink-400" />
            </label>
          </div>
          <ul className="divide-y divide-line">
            {members.map((m) => (
              <li key={m.email} className="flex items-center gap-3.5 px-5 py-3">
                <span className="flex h-9 w-9 items-center justify-center rounded-full bg-gradient-to-br from-brand-100 to-brand-200 text-[12px] font-bold text-brand-700">
                  {m.name.split(" ").map((p) => p[0]).join("")}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="text-[13.5px] font-semibold text-ink-900">{m.name}</p>
                  <p className="truncate text-[12px] text-ink-500">{m.email} • {m.team}</p>
                </div>
                <span className={cx("text-[11.5px]", m.active === "Now" ? "font-semibold text-emerald-500" : "text-ink-400")}>
                  {m.active === "Now" ? "● Online" : m.active}
                </span>
                <Badge tone={m.tone}>{m.role}</Badge>
                <button className="flex h-8 w-8 items-center justify-center rounded-[8px] text-ink-400 transition hover:bg-canvas hover:text-brand-500" aria-label={`Manage ${m.name}`}>
                  <MoreHorizontal size={15} />
                </button>
              </li>
            ))}
          </ul>
          <div className="border-t border-line px-5 py-3 text-[12.5px] text-ink-500">Showing 6 of 612 members</div>
        </Card>

        <Card className="col-span-5 p-5">
          <CardTitle icon={KeyRound} title="Permission Matrix" tint="bg-sky-50 text-sky-500" />
          <table className="mt-4 w-full">
            <thead>
              <tr className="text-[11.5px] font-bold uppercase tracking-[0.08em] text-ink-400">
                <th className="pb-2.5 text-left font-bold">Permission</th>
                <th className="pb-2.5 font-bold">Admin</th>
                <th className="pb-2.5 font-bold">Editor</th>
                <th className="pb-2.5 font-bold">Viewer</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {matrix.map((row) => (
                <tr key={row.perm}>
                  <td className="py-3 pr-3 text-[12.5px] font-medium text-ink-700">{row.perm}</td>
                  <td className="text-center"><Mark on={row.admin} /></td>
                  <td className="text-center"><Mark on={row.editor} /></td>
                  <td className="text-center"><Mark on={row.viewer} /></td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-4 rounded-[12px] bg-canvas px-4 py-3 text-[12px] leading-relaxed text-ink-500">
            Source-level permissions are inherited from each connected system — users only ever see answers built from documents they can already access.
          </p>
        </Card>
      </div>
    </div>
  );
}
