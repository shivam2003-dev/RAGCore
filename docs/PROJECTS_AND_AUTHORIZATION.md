# Projects and source authorization

Projects are relevance lenses, not permission grants. Every retrieval surface, including Ask,
workflow APIs, REST evidence tools, and MCP, uses the same server-side scope:

```text
organization sources
INTERSECT sources authorized for the user
INTERSECT sources mapped to the selected project
INTERSECT any request source-family filter
```

The browser, prompt, planner, and caller-supplied source IDs cannot widen that scope. Organization
admins may configure a restricted source but still need an explicit source grant to retrieve it.

## First-run and migration behavior

- Registration creates an active `All Knowledge` project, adds the user as its manager, and makes it
  the default project.
- Migration `0003` creates one `All Knowledge` project per existing organization, maps existing
  knowledge bases and users, and sets missing user/conversation defaults.
- Existing organization-scoped knowledge bases remain visible after the migration.
- Restricted knowledge bases require rows in `source_access_grants`; project membership alone is
  insufficient.

## Operator onboarding

1. Open `/projects` as an administrator or editor.
2. Create or select a Project.
3. Map only the knowledge bases relevant to that team or system.
4. Add members. Use `manager` only for editors who should maintain the lens.
5. For each restricted knowledge base, grant individual users access through Access Control.
6. Set the user's default Project.
7. Verify the Project selector in Ask, Incident Copilot, and Content Health.
8. Test a user without a restricted-source grant and confirm the source is absent from results,
   citations, direct search, cached answers, and MCP output.

## Role model

- `viewer`: select and use Projects where they are a member.
- `editor`: create Projects; maintain details/source mappings only when a Project manager.
- `admin`: administer Projects, memberships, and restricted-source grants.

Cross-organization IDs return a denied/not-found result without disclosing whether the object
exists. Authorization-changing mutations invalidate authorization-aware cache versions.

## API surface

```text
GET/POST           /api/v1/projects
GET/PATCH/DELETE   /api/v1/projects/{project_id}
GET/PUT            /api/v1/projects/{project_id}/sources
GET/PUT            /api/v1/projects/{project_id}/members
PUT                /api/v1/users/me/default-project
GET/PUT            /api/v1/knowledge-bases/{knowledge_base_id}/permissions
```

All changes are audit logged using identifiers and counts; source content and credentials are not
included in audit details.
