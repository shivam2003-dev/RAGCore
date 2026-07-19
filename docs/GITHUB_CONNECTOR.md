# GitHub Code Connector

The GitHub connector builds a read-only, incremental code index inside KimbalGPT's existing
`KnowledgeBase -> Document -> DocumentVersion -> Chunk` pipeline. Production should use a GitHub App
installation token; a fine-grained read-only personal access token is supported for initial local
verification.

## Safety boundary

- The client exposes GET operations only: branch snapshot, recursive tree, blob, contributors, and
  pull-request listing.
- Connected repositories are never cloned, executed, modified, branched, commented on, or used to
  create issues or pull requests.
- Repository, branch, and path allowlists are explicit. Dependency, vendor, generated, build,
  secret-like, binary, and oversized paths are denied before indexing.
- Tokens remain server-side environment or secret-manager values. Database state and status APIs
  contain only non-secret configuration and health data.
- Each repository/branch maps to a dedicated knowledge base and Project, so the normal server-side
  Project/source ACL intersection applies to semantic search, exact search, PR evidence, and chat.
- Exact code search is a parameterized PostgreSQL literal substring query. It never invokes `grep`,
  `rg`, a shell, or indexed repository code.

## GitHub permissions

For a GitHub App, grant repository `Contents: read`, `Metadata: read`, and `Pull requests: read` only.
A fine-grained PAT used for local verification should be limited to the same repository and read
permissions.

Primary GitHub references:

- [Get a Git tree](https://docs.github.com/en/rest/git/trees#get-a-tree)
- [Get a Git blob](https://docs.github.com/en/rest/git/blobs#get-a-blob)
- [List pull requests](https://docs.github.com/en/rest/pulls/pulls#list-pull-requests)
- [Repository REST endpoints](https://docs.github.com/en/rest/repos/repos)

## Environment

```dotenv
GITHUB_TOKEN=
GITHUB_API_BASE_URL=https://api.github.com
GITHUB_API_VERSION=2026-03-10
GITHUB_DEFAULT_BRANCH=main
GITHUB_REQUEST_TIMEOUT_SECONDS=20
GITHUB_API_MAX_RETRIES=3
GITHUB_MAX_FILES_PER_SYNC=2000
GITHUB_MAX_BLOB_BYTES=1000000
GITHUB_RECENT_PR_LIMIT=20
```

`GITHUB_DEFAULT_PATH_DENYLIST` can override the conservative built-in denylist. Do not weaken the
secret, dependency, vendor, generated, build, or artifact exclusions without a security review.

## Configure and operate

An organization admin supplies a non-secret mapping:

```http
POST /api/v1/github/repositories
Content-Type: application/json

{
  "owner": "example-org",
  "repository": "service-api",
  "branch": "main",
  "project_id": "00000000-0000-0000-0000-000000000000",
  "path_allowlist": ["src/**", "docs/**", "CODEOWNERS"],
  "path_denylist": ["src/generated/**"]
}
```

Operational endpoints:

```text
GET  /api/v1/github/status
POST /api/v1/github/repositories/{mapping_id}/sync
GET  /api/v1/github/repositories/{mapping_id}/recent-prs
POST /api/v1/github/code-search
```

The UI shows repository/branch status, last indexed commit, last index time, and sanitized indexing
errors. Sync is disabled until a server-side credential is configured.

## Incremental algorithm

1. Resolve the configured branch to its head commit and tree SHA.
2. If the tree SHA matches the last successful sync, return without listing blobs or queueing any
   embeddings.
3. Read the recursive tree and apply file-count, size, extension, allowlist, and denylist policies.
4. Compare each allowed path's blob SHA with `github_file_states`.
5. Unchanged path/blob pairs are skipped without downloading or re-embedding.
6. Added/changed files create a new document or document version.
7. A new path with a missing path's blob SHA is treated as a rename; document lineage is retained
   and source/citation metadata is updated to the new path and commit URL.
8. Missing or newly denied files are soft-deleted and their chunks are deactivated.
9. Successful state records the head commit/tree SHA, freshness, counts, and sanitized health data.

Text files are decoded as UTF-8; NUL-containing or undecodable blobs are treated as binary. Oversized
files are reported and skipped before download when the tree supplies a size.

## Code intelligence

Supported source files use symbol-aware chunking at class, function, method, and exported-arrow
function boundaries. Metadata preserves language, symbol, symbol kind, and line boundaries. A single
oversized symbol falls back to bounded recursive chunks while retaining its symbol identity.

Every indexed file preserves:

- owner, repository, branch, and path;
- language and symbol metadata;
- blob SHA and indexed commit SHA;
- stable `github.com/.../blob/{commit_sha}/{path}` citation URL;
- matching CODEOWNERS (last rule wins);
- bounded repository contributor metadata.

Semantic code retrieval uses the normal authorized hybrid search. Exact code search behaves like a
literal `rg -F` against authorized indexed chunks without executing a shell. Recent pull requests are
normalized into number, title/body, state, author, branches, timestamps, labels, and stable URL.

## Verification evidence

Fixture tests prove initial indexing, unchanged-tree short circuit, changed files, rename lineage,
deletion, allow/deny and secret controls, symbol chunking, oversized fallback, exact-search injection
resistance, pull-request normalization, CODEOWNERS precedence, project isolation, contributor
metadata, semantic retrieval, and stable commit citations.

The authenticated read-only CLI smoke against `shivam2003-dev/RAGCore` resolved `main`, read an
untruncated 216-blob tree, confirmed no dependency/vendor paths in that tree, and normalized the
latest pull request. Changed-file behavior stays fixture-proven because the smoke must not modify the
connected source repository.
