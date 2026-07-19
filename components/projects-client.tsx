"use client";

import { type FormEvent, useEffect, useMemo, useState } from "react";
import {
  Check,
  FolderKanban,
  Loader2,
  LockKeyhole,
  Plus,
  Save,
  ShieldCheck,
  Trash2,
  Users,
} from "lucide-react";
import { Badge, Card, GhostButton, PageHeader, PrimaryButton, cx } from "@/components/ui";
import {
  cvumApi,
  type KnowledgeBase,
  type Project,
  type ProjectMember,
  type UserOut,
} from "@/lib/cvum-api";

export function ProjectsClient() {
  const [user, setUser] = useState<UserOut | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [organizationUsers, setOrganizationUsers] = useState<UserOut[]>([]);
  const [members, setMembers] = useState<ProjectMember[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [selectedSources, setSelectedSources] = useState<string[]>([]);
  const [selectedMembers, setSelectedMembers] = useState<Record<string, "member" | "manager">>({});
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [newName, setNewName] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [status, setStatus] = useState("Loading projects...");
  const [saving, setSaving] = useState(false);

  const selectedProject = projects.find((project) => project.id === selectedId) ?? null;
  const defaultProject = projects.find((project) => project.id === user?.default_project_id) ?? null;
  const canManage = Boolean(
    user && selectedProject && (
      user.role === "admin" ||
      (user.role === "editor" && selectedProject.user_project_role === "manager")
    )
  );

  async function refresh(preferredId?: string) {
    const [currentUser, projectRows, sourceRows] = await Promise.all([
      cvumApi.ensureSession(),
      cvumApi.listProjects(),
      cvumApi.listKnowledgeBases(),
    ]);
    let userRows: UserOut[] = [];
    if (currentUser.role === "admin") {
      userRows = await cvumApi.listUsers();
    }
    setUser(currentUser);
    setProjects(projectRows);
    setKnowledgeBases(sourceRows);
    setOrganizationUsers(userRows);
    const nextId = preferredId && projectRows.some((project) => project.id === preferredId)
      ? preferredId
      : currentUser.default_project_id && projectRows.some((project) => project.id === currentUser.default_project_id)
        ? currentUser.default_project_id
        : projectRows[0]?.id ?? "";
    setSelectedId(nextId);
    setStatus(projectRows.length ? `${projectRows.length} active projects` : "No active projects");
  }

  useEffect(() => {
    let cancelled = false;
    const timer = window.setTimeout(() => {
      void refresh().catch((error) => {
        if (!cancelled) setStatus(error instanceof Error ? error.message : "Could not load projects");
      });
    }, 0);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    const timer = window.setTimeout(() => {
      if (!selectedProject) {
        setName("");
        setDescription("");
        setSelectedSources([]);
        setMembers([]);
        setSelectedMembers({});
        return;
      }
      setName(selectedProject.name);
      setDescription(selectedProject.description);
      setSelectedSources(selectedProject.source_ids);
      void cvumApi.listProjectMembers(selectedProject.id)
        .then((rows) => {
          if (cancelled) return;
          setMembers(rows);
          setSelectedMembers(Object.fromEntries(rows.map((member) => [member.user_id, member.project_role])));
        })
        .catch((error) => {
          if (!cancelled) setStatus(error instanceof Error ? error.message : "Could not load members");
        });
    }, 0);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [selectedProject]);

  const availableSources = useMemo(
    () => knowledgeBases.slice().sort((left, right) => left.name.localeCompare(right.name)),
    [knowledgeBases]
  );

  async function createProject(event: FormEvent) {
    event.preventDefault();
    if (!newName.trim() || saving) return;
    setSaving(true);
    setStatus("Creating project...");
    try {
      const created = await cvumApi.createProject({
        name: newName.trim(),
        description: newDescription.trim(),
      });
      setNewName("");
      setNewDescription("");
      await refresh(created.id);
      setStatus(`${created.name} created`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Project creation failed");
    } finally {
      setSaving(false);
    }
  }

  async function saveDetails() {
    if (!selectedProject || !canManage || saving) return;
    setSaving(true);
    setStatus(`Saving ${selectedProject.name}...`);
    try {
      const updated = await cvumApi.updateProject(selectedProject.id, {
        name: name.trim(),
        description: description.trim(),
      });
      await refresh(updated.id);
      setStatus(`${updated.name} details saved`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Project update failed");
    } finally {
      setSaving(false);
    }
  }

  async function saveSources() {
    if (!selectedProject || !canManage || saving) return;
    setSaving(true);
    setStatus(`Updating sources for ${selectedProject.name}...`);
    try {
      const updated = await cvumApi.updateProjectSources(selectedProject.id, selectedSources);
      await refresh(updated.id);
      setStatus(`${updated.source_ids.length} sources mapped to ${updated.name}`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Source mapping failed");
    } finally {
      setSaving(false);
    }
  }

  async function saveMembers() {
    if (!selectedProject || user?.role !== "admin" || saving) return;
    setSaving(true);
    setStatus(`Updating members for ${selectedProject.name}...`);
    try {
      const rows = await cvumApi.updateProjectMembers(
        selectedProject.id,
        Object.entries(selectedMembers).map(([user_id, project_role]) => ({ user_id, project_role }))
      );
      setMembers(rows);
      await refresh(selectedProject.id);
      setStatus(`${rows.length} members assigned to ${selectedProject.name}`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Membership update failed");
    } finally {
      setSaving(false);
    }
  }

  async function makeDefault() {
    if (!selectedProject || saving) return;
    setSaving(true);
    try {
      await cvumApi.setDefaultProject(selectedProject.id);
      setUser((current) => current ? { ...current, default_project_id: selectedProject.id } : current);
      setStatus(`${selectedProject.name} is now your default project`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Default project update failed");
    } finally {
      setSaving(false);
    }
  }

  async function deactivateProject() {
    if (!selectedProject || !canManage || selectedProject.slug === "all-knowledge" || saving) return;
    setSaving(true);
    try {
      await cvumApi.deleteProject(selectedProject.id);
      await refresh();
      setStatus(`${selectedProject.name} deactivated; its sources were not deleted`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Project deactivation failed");
    } finally {
      setSaving(false);
    }
  }

  function toggleSource(sourceId: string) {
    setSelectedSources((current) => current.includes(sourceId)
      ? current.filter((id) => id !== sourceId)
      : [...current, sourceId]);
  }

  function toggleMember(userId: string) {
    setSelectedMembers((current) => {
      const next = { ...current };
      if (next[userId]) delete next[userId];
      else next[userId] = "member";
      return next;
    });
  }

  return (
    <div>
      <PageHeader
        title="Projects"
        subtitle="Project Lens narrows relevance while source ACLs remain an independent security boundary."
        actions={saving ? <span className="flex items-center gap-2 text-[13px] text-ink-500"><Loader2 size={15} className="animate-spin" /> Saving</span> : undefined}
      />

      <p role="status" className="mb-5 rounded-[12px] border border-line bg-white px-4 py-3 text-[12.5px] text-ink-600">
        {status}
      </p>

      <Card className="mb-5 p-4">
        <div className="grid gap-3 sm:grid-cols-3">
          {[
            ["1. Choose", selectedProject?.name ?? "Select a project", "This lens controls relevance for Ask and workflows."],
            ["2. Default", defaultProject?.name ?? "Not selected", "Your default opens automatically on desktop and mobile."],
            ["3. Verify", `${selectedProject?.authorized_source_ids.length ?? 0} authorized sources`, "Restricted sources still require an explicit grant."],
          ].map(([step, value, detail]) => (
            <div key={step} className="rounded-[11px] bg-canvas px-3 py-3">
              <p className="text-[10.5px] font-bold uppercase tracking-[0.08em] text-brand-500">{step}</p>
              <p className="mt-1 truncate text-[13px] font-semibold text-ink-900">{value}</p>
              <p className="mt-1 text-[11px] leading-4 text-ink-500">{detail}</p>
            </div>
          ))}
        </div>
      </Card>

      <div className="grid gap-5 lg:grid-cols-[300px_minmax(0,1fr)]">
        <div className="space-y-5">
          <Card className="overflow-hidden">
            <div className="border-b border-line p-4">
              <div className="flex items-center gap-2 text-[14px] font-semibold text-ink-900"><FolderKanban size={16} /> Active projects</div>
            </div>
            <div className="max-h-[420px] overflow-y-auto p-2">
              {projects.map((project) => (
                <button
                  type="button"
                  key={project.id}
                  onClick={() => setSelectedId(project.id)}
                  aria-pressed={project.id === selectedId}
                  className={cx(
                    "mb-1 w-full rounded-[12px] border px-3 py-3 text-left transition",
                    project.id === selectedId
                      ? "border-brand-200 bg-brand-50"
                      : "border-transparent hover:border-line hover:bg-canvas"
                  )}
                >
                  <span className="flex items-center gap-2">
                    <span className="truncate text-[13px] font-semibold text-ink-900">{project.name}</span>
                    {user?.default_project_id === project.id && <Badge tone="green">Default</Badge>}
                  </span>
                  <span className="mt-1 block text-[11.5px] text-ink-500">{project.source_ids.length} sources · {project.member_count} members</span>
                </button>
              ))}
              {!projects.length && <p className="px-3 py-8 text-center text-[13px] text-ink-500">No projects available.</p>}
            </div>
          </Card>

          {user?.role !== "viewer" && (
            <Card className="p-4">
              <form onSubmit={createProject} className="space-y-3">
                <div className="flex items-center gap-2 text-[14px] font-semibold text-ink-900"><Plus size={16} /> New project</div>
                <input value={newName} onChange={(event) => setNewName(event.target.value)} placeholder="Project name" maxLength={255} className="h-10 w-full rounded-[9px] border border-line px-3 text-[13px] outline-none focus:border-brand-300" />
                <textarea value={newDescription} onChange={(event) => setNewDescription(event.target.value)} placeholder="Short description" rows={3} maxLength={2000} className="w-full resize-none rounded-[9px] border border-line px-3 py-2 text-[13px] outline-none focus:border-brand-300" />
                <PrimaryButton type="submit" disabled={!newName.trim() || saving} className="w-full justify-center"><Plus size={15} /> Create project</PrimaryButton>
              </form>
            </Card>
          )}
        </div>

        {selectedProject ? (
          <div className="space-y-5">
            <Card className="p-5">
              <div className="flex flex-wrap items-center gap-2">
                <FolderKanban size={18} className="text-brand-500" />
                <h2 className="text-[17px] font-semibold text-ink-900">Project details</h2>
                <Badge tone={canManage ? "blue" : "gray"}>{canManage ? "Manage" : "Member"}</Badge>
                <div className="ml-auto flex gap-2">
                  {user?.default_project_id !== selectedProject.id && <GhostButton onClick={() => void makeDefault()} disabled={saving}><Check size={14} /> Make default</GhostButton>}
                  {canManage && selectedProject.slug !== "all-knowledge" && <GhostButton onClick={() => void deactivateProject()} disabled={saving} className="text-rose-600"><Trash2 size={14} /> Deactivate</GhostButton>}
                </div>
              </div>
              <div className="mt-5 grid gap-3 sm:grid-cols-2">
                <label className="text-[11px] font-bold uppercase tracking-[0.08em] text-ink-400">Name<input value={name} onChange={(event) => setName(event.target.value)} disabled={!canManage} className="mt-1 h-10 w-full rounded-[9px] border border-line px-3 text-[13px] font-normal normal-case tracking-normal text-ink-900 outline-none focus:border-brand-300 disabled:bg-canvas" /></label>
                <label className="text-[11px] font-bold uppercase tracking-[0.08em] text-ink-400">Slug<input value={selectedProject.slug} disabled className="mt-1 h-10 w-full rounded-[9px] border border-line bg-canvas px-3 text-[13px] font-normal normal-case tracking-normal text-ink-500" /></label>
                <label className="sm:col-span-2 text-[11px] font-bold uppercase tracking-[0.08em] text-ink-400">Description<textarea value={description} onChange={(event) => setDescription(event.target.value)} disabled={!canManage} rows={3} className="mt-1 w-full resize-none rounded-[9px] border border-line px-3 py-2 text-[13px] font-normal normal-case tracking-normal text-ink-900 outline-none focus:border-brand-300 disabled:bg-canvas" /></label>
              </div>
              {canManage && <PrimaryButton onClick={() => void saveDetails()} disabled={saving || !name.trim()} className="mt-4"><Save size={15} /> Save details</PrimaryButton>}
            </Card>

            <div className="grid gap-5 xl:grid-cols-2">
              <Card className="p-5">
                <div className="flex items-center gap-2"><ShieldCheck size={17} className="text-emerald-500" /><h2 className="text-[15px] font-semibold text-ink-900">Knowledge sources</h2><span className="ml-auto text-[11px] text-ink-500">{selectedSources.length} selected</span></div>
                <p className="mt-2 text-[11.5px] leading-5 text-ink-500">Mapping controls relevance only. Restricted sources still require explicit user grants.</p>
                <div className="mt-4 max-h-[310px] space-y-2 overflow-y-auto pr-1">
                  {availableSources.map((source) => {
                    const checked = selectedSources.includes(source.id);
                    return (
                      <label key={source.id} className={cx("flex cursor-pointer items-start gap-3 rounded-[11px] border p-3", checked ? "border-brand-200 bg-brand-50" : "border-line")}>
                        <input type="checkbox" checked={checked} disabled={!canManage} onChange={() => toggleSource(source.id)} className="mt-0.5 h-4 w-4 accent-[#5b5ceb]" />
                        <span className="min-w-0 flex-1"><span className="block truncate text-[12.5px] font-semibold text-ink-900">{source.name}</span><span className="mt-1 flex items-center gap-1 text-[10.5px] text-ink-500">{source.access_scope === "restricted" && <LockKeyhole size={11} />} {source.access_scope}</span></span>
                      </label>
                    );
                  })}
                  {!availableSources.length && <p className="py-6 text-center text-[12px] text-ink-500">No authorized sources available.</p>}
                </div>
                {canManage && <PrimaryButton onClick={() => void saveSources()} disabled={saving} className="mt-4"><Save size={15} /> Save source mapping</PrimaryButton>}
              </Card>

              <Card className="p-5">
                <div className="flex items-center gap-2"><Users size={17} className="text-sky-500" /><h2 className="text-[15px] font-semibold text-ink-900">Members</h2><span className="ml-auto text-[11px] text-ink-500">{members.length} assigned</span></div>
                <p className="mt-2 text-[11.5px] leading-5 text-ink-500">Membership allows project selection. It never grants access to a restricted source.</p>
                <div className="mt-4 max-h-[310px] space-y-2 overflow-y-auto pr-1">
                  {user?.role === "admin" ? organizationUsers.map((member) => {
                    const memberRole = selectedMembers[member.id];
                    return (
                      <div key={member.id} className={cx("flex items-center gap-3 rounded-[11px] border p-3", memberRole ? "border-sky-200 bg-sky-50/60" : "border-line")}>
                        <input type="checkbox" checked={Boolean(memberRole)} onChange={() => toggleMember(member.id)} className="h-4 w-4 accent-[#5b5ceb]" aria-label={`Project membership for ${member.full_name}`} />
                        <span className="min-w-0 flex-1"><span className="block truncate text-[12.5px] font-semibold text-ink-900">{member.full_name}</span><span className="block truncate text-[10.5px] text-ink-500">{member.email}</span></span>
                        {memberRole && <select value={memberRole} onChange={(event) => setSelectedMembers((current) => ({ ...current, [member.id]: event.target.value as "member" | "manager" }))} className="h-8 rounded-[8px] border border-line bg-white px-2 text-[11.5px] outline-none"><option value="member">member</option><option value="manager">manager</option></select>}
                      </div>
                    );
                  }) : members.map((member) => (
                    <div key={member.user_id} className="flex items-center gap-3 rounded-[11px] border border-line p-3"><span className="min-w-0 flex-1"><span className="block truncate text-[12.5px] font-semibold text-ink-900">{member.full_name}</span><span className="block truncate text-[10.5px] text-ink-500">{member.email}</span></span><Badge tone={member.project_role === "manager" ? "blue" : "gray"}>{member.project_role}</Badge></div>
                  ))}
                </div>
                {user?.role === "admin" && <PrimaryButton onClick={() => void saveMembers()} disabled={saving} className="mt-4"><Save size={15} /> Save membership</PrimaryButton>}
              </Card>
            </div>
          </div>
        ) : (
          <Card className="flex min-h-[320px] items-center justify-center p-8 text-center text-[13px] text-ink-500">Select or create a project to configure Project Lens.</Card>
        )}
      </div>
    </div>
  );
}
