"use client";

import { useEffect, useMemo, useState } from "react";
import { Check, KeyRound, Minus, Search, Shield, UserPlus, Users } from "lucide-react";
import { Badge, Card, CardTitle, GhostButton, PageHeader, PrimaryButton } from "@/components/ui";
import { kimbalApi, type UserOut } from "@/lib/kimbal-api";

const matrix = [
  { perm: "Ask CVUM & search", admin: true, editor: true, viewer: true },
  { perm: "Admin navigation", admin: true, editor: false, viewer: false },
  { perm: "Upload and reindex documents", admin: true, editor: false, viewer: false },
  { perm: "Sync Confluence", admin: true, editor: false, viewer: false },
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

function initials(name: string) {
  return name.split(" ").filter(Boolean).map((part) => part[0]).join("").slice(0, 2).toUpperCase() || "U";
}

function roleTone(role: string) {
  if (role === "admin") return "brand" as const;
  if (role === "editor") return "blue" as const;
  return "gray" as const;
}

export function AccessControlClient() {
  const [users, setUsers] = useState<UserOut[]>([]);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("Loading users");
  const [loading, setLoading] = useState(true);
  const [newEmail, setNewEmail] = useState("");
  const [newName, setNewName] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newRole, setNewRole] = useState<"admin" | "editor" | "viewer">("viewer");
  const [creating, setCreating] = useState(false);

  async function refresh() {
    setLoading(true);
    try {
      await kimbalApi.ensureSession();
      const rows = await kimbalApi.listUsers();
      setUsers(rows);
      setStatus(`${rows.length} users loaded`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Failed to load users");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void refresh();
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return users;
    return users.filter((user) => `${user.full_name} ${user.email} ${user.role}`.toLowerCase().includes(needle));
  }, [users, query]);

  const roleCounts = ["admin", "editor", "viewer"].map((role) => ({
    role,
    members: users.filter((user) => user.role === role).length,
  }));

  async function changeRole(user: UserOut, role: "admin" | "editor" | "viewer") {
    if (user.role === role) return;
    setStatus(`Updating ${user.full_name}`);
    try {
      const updated = await kimbalApi.updateUserRole(user.id, role);
      setUsers((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      setStatus(`${updated.full_name} is now ${updated.role}`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Role update failed");
    }
  }

  async function createMember() {
    const email = newEmail.trim().toLowerCase();
    if (!email.endsWith("@cvum.io")) {
      setStatus("Use a cvum.io email address");
      return;
    }
    if (!newName.trim() || newPassword.length < 10) {
      setStatus("Name and a 10+ character password are required");
      return;
    }
    setCreating(true);
    setStatus(`Creating ${email}`);
    try {
      const created = await kimbalApi.createUser({
        email,
        password: newPassword,
        full_name: newName.trim(),
        role: newRole,
      });
      setUsers((current) => [...current, created]);
      setNewEmail("");
      setNewName("");
      setNewPassword("");
      setNewRole("viewer");
      setStatus(`${created.full_name} created as ${created.role}`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "User creation failed");
    } finally {
      setCreating(false);
    }
  }

  return (
    <div>
      <PageHeader
        title="Access Control"
        subtitle="Live users and RBAC permissions for this organization."
        actions={
          <div className="flex gap-2.5">
            <GhostButton disabled><KeyRound size={15} /> SSO not configured</GhostButton>
            <GhostButton onClick={() => document.getElementById("create-member-email")?.focus()}>
              <UserPlus size={15} /> Create member
            </GhostButton>
          </div>
        }
      />

      <div className="grid grid-cols-3 gap-5 animate-rise-1">
        {roleCounts.map((role) => (
          <Card key={role.role} className="flex items-center gap-4 p-5">
            <span className="flex h-11 w-11 items-center justify-center rounded-[13px] bg-brand-50 text-brand-500">
              <Shield size={19} />
            </span>
            <div className="flex-1">
              <p className="text-[15px] font-bold capitalize text-ink-900">{role.role}</p>
              <p className="text-[12px] text-ink-500">Current live role count</p>
            </div>
            <p className="text-[22px] font-bold text-ink-900">{role.members}</p>
          </Card>
        ))}
      </div>

      <div className="mt-5 grid grid-cols-12 gap-5 animate-rise-2">
        <Card className="col-span-7">
          <div className="flex items-center gap-3 p-5 pb-3">
            <CardTitle icon={Users} title="Members" />
            <span className="text-[12px] font-semibold text-ink-400">{status}</span>
            <label className="ml-auto flex h-9 w-56 cursor-text items-center gap-2 rounded-[9px] border border-line bg-canvas px-3 transition focus-within:border-brand-300 focus-within:bg-white">
              <Search size={14} className="text-ink-400" />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search members..."
                className="min-w-0 flex-1 bg-transparent text-[12.5px] outline-none placeholder:text-ink-400"
              />
            </label>
          </div>
          <ul className="divide-y divide-line">
            {filtered.map((member) => (
              <li key={member.email} className="flex items-center gap-3.5 px-5 py-3">
                <span className="flex h-9 w-9 items-center justify-center rounded-full bg-gradient-to-br from-brand-100 to-brand-200 text-[12px] font-bold text-brand-700">
                  {initials(member.full_name)}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="text-[13.5px] font-semibold text-ink-900">{member.full_name}</p>
                  <p className="truncate text-[12px] text-ink-500">{member.email}</p>
                </div>
                <Badge tone={roleTone(member.role)}>{member.role}</Badge>
                <select
                  value={member.role}
                  disabled={loading}
                  onChange={(event) => void changeRole(member, event.target.value as "admin" | "editor" | "viewer")}
                  className="h-8 rounded-[8px] border border-line bg-white px-2 text-[12px] font-semibold text-ink-700 outline-none transition focus:border-brand-300"
                  aria-label={`Role for ${member.full_name}`}
                >
                  <option value="admin">admin</option>
                  <option value="editor">editor</option>
                  <option value="viewer">viewer</option>
                </select>
              </li>
            ))}
            {!loading && !filtered.length && (
              <li className="px-5 py-6 text-[13px] text-ink-500">No users match this search.</li>
            )}
          </ul>
          <div className="border-t border-line px-5 py-3 text-[12.5px] text-ink-500">
            Showing {filtered.length} of {users.length} users
          </div>
        </Card>

        <Card className="col-span-5 p-5">
          <CardTitle icon={UserPlus} title="Create Member" tint="bg-emerald-50 text-emerald-500" />
          <div className="mt-4 grid gap-3">
            <label className="block">
              <span className="mb-1 block text-[11px] font-bold uppercase tracking-[0.08em] text-ink-400">Email</span>
              <input
                id="create-member-email"
                value={newEmail}
                onChange={(event) => setNewEmail(event.target.value)}
                placeholder="name@cvum.io"
                className="h-9 w-full rounded-[9px] border border-line bg-canvas px-3 text-[12.5px] outline-none transition focus:border-brand-300 focus:bg-white"
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-[11px] font-bold uppercase tracking-[0.08em] text-ink-400">Full name</span>
              <input
                value={newName}
                onChange={(event) => setNewName(event.target.value)}
                placeholder="Member name"
                className="h-9 w-full rounded-[9px] border border-line bg-canvas px-3 text-[12.5px] outline-none transition focus:border-brand-300 focus:bg-white"
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-[11px] font-bold uppercase tracking-[0.08em] text-ink-400">Password</span>
              <input
                value={newPassword}
                onChange={(event) => setNewPassword(event.target.value)}
                type="password"
                placeholder="At least 10 characters"
                className="h-9 w-full rounded-[9px] border border-line bg-canvas px-3 text-[12.5px] outline-none transition focus:border-brand-300 focus:bg-white"
              />
            </label>
            <div className="flex items-end gap-2">
              <label className="block flex-1">
                <span className="mb-1 block text-[11px] font-bold uppercase tracking-[0.08em] text-ink-400">Role</span>
                <select
                  value={newRole}
                  onChange={(event) => setNewRole(event.target.value as "admin" | "editor" | "viewer")}
                  className="h-9 w-full rounded-[9px] border border-line bg-white px-3 text-[12.5px] font-semibold text-ink-700 outline-none transition focus:border-brand-300"
                >
                  <option value="viewer">viewer</option>
                  <option value="editor">editor</option>
                  <option value="admin">admin</option>
                </select>
              </label>
              <PrimaryButton disabled={creating} onClick={() => void createMember()} className="h-9 px-3 py-0 text-[12.5px]">
                Create
              </PrimaryButton>
            </div>
          </div>

          <div className="my-5 h-px bg-line" />
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
            These permissions reflect the backend RBAC gates currently implemented in the API.
          </p>
        </Card>
      </div>
    </div>
  );
}
