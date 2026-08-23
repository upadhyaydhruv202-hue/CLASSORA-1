import { useEffect, useMemo, useState } from "react";
import { api } from "./api";
import { EmptyState, Field, Notice } from "./ui";

const FILTER_KEYS = ["year", "semester", "subject", "type", "source", "search", "sort", "page"];

function readFilters() {
  const q = new URLSearchParams(window.location.search);
  return {
    year: q.get("year") || "",
    semester: q.get("semester") || "",
    subject: q.get("subject") || "",
    type: q.get("type") || "",
    source: q.get("source") || "",
    search: q.get("search") || "",
    sort: q.get("sort") || "recent",
    page: q.get("page") || "1",
  };
}

function writeFilters(next) {
  const url = new URL(window.location.href);
  FILTER_KEYS.forEach((key) => {
    const value = String(next[key] || "").trim();
    if (!value || (key === "sort" && value === "recent") || (key === "page" && value === "1")) {
      url.searchParams.delete(key);
    } else {
      url.searchParams.set(key, value);
    }
  });
  window.history.replaceState({}, "", url.pathname + url.search);
}

function safeHttpsUrl(raw) {
  try {
    const parsed = new URL(String(raw || "").trim());
    if (parsed.protocol !== "https:") return "";
    return parsed.href;
  } catch {
    return "";
  }
}

function formatWhen(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

const emptyForm = {
  title: "",
  description: "",
  year_id: "",
  semester_id: "",
  subject_id: "",
  resource_type_id: "",
  source_id: "",
  original_url: "",
  resource_format: "",
  tags: "",
  display_order: "0",
};

export default function AcademicResources({ session }) {
  const isAdmin = session?.user_role === "administrator";
  const isStudent = session?.user_role === "student";
  const [filters, setFilters] = useState(() => readFilters());
  const [searchInput, setSearchInput] = useState(() => readFilters().search);
  const [catalog, setCatalog] = useState(null);
  const [list, setList] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [manage, setManage] = useState("browse");
  const [form, setForm] = useState(emptyForm);
  const [formErrors, setFormErrors] = useState({});
  const [subjectForm, setSubjectForm] = useState({ name: "", code: "", description: "", year_id: "", semester_id: "" });
  const [sourceForm, setSourceForm] = useState({ name: "", website_url: "", description: "" });
  const [typeForm, setTypeForm] = useState({ name: "", code: "" });
  const [reports, setReports] = useState([]);
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(null);

  const yearOptions = catalog?.years || [];
  const semesterOptions = useMemo(() => {
    const rows = catalog?.semesters || [];
    if (!filters.year) return rows;
    return rows.filter((row) => row.year_id === filters.year);
  }, [catalog, filters.year]);
  const subjectOptions = useMemo(() => {
    const rows = catalog?.subjects || [];
    return rows.filter((row) => {
      if (filters.year && row.year_id !== filters.year) return false;
      if (filters.semester && row.semester_id !== filters.semester) return false;
      return true;
    });
  }, [catalog, filters.year, filters.semester]);

  const loadCatalog = async (next = filters) => {
    const data = await api.academicCatalog({ year: next.year, semester: next.semester });
    setCatalog(data);
    return data;
  };

  const loadList = async (next = filters) => {
    const data = await api.academicResources({
      year: next.year,
      semester: next.semester,
      subject: next.subject,
      type: next.type,
      source: next.source,
      search: next.search,
      sort: next.sort,
      page: next.page,
      limit: 12,
    });
    setList(data);
    return data;
  };

  const refresh = async (next = filters) => {
    setLoading(true);
    setError("");
    try {
      await Promise.all([loadCatalog(next), loadList(next)]);
      if (isAdmin && manage === "reports") {
        const payload = await api.academicReports();
        setReports(payload.reports || []);
      }
    } catch (err) {
      setError(err.message || "Unable to load academic resources. Please try again.");
      setList(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh(filters);
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => {
      if (searchInput === filters.search) return;
      changeFilter("search", searchInput);
    }, 350);
    return () => clearTimeout(timer);
  }, [searchInput]);

  const changeFilter = (key, value) => {
    const next = { ...filters, [key]: value, page: key === "page" ? value : "1" };
    if (key === "year") {
      const stillValid = (catalog?.semesters || []).some((row) => row.id === filters.semester && row.year_id === value);
      if (!stillValid) next.semester = "";
      next.subject = "";
    }
    if (key === "semester") next.subject = "";
    setFilters(next);
    writeFilters(next);
    refresh(next);
  };

  const clearFilters = () => {
    const next = { year: "", semester: "", subject: "", type: "", source: "", search: "", sort: "recent", page: "1" };
    setSearchInput("");
    setFilters(next);
    writeFilters(next);
    refresh(next);
  };

  const hasFilters = Boolean(filters.year || filters.semester || filters.subject || filters.type || filters.source || filters.search);

  const validateResource = () => {
    const errors = {};
    if (!form.title.trim()) errors.title = "Title is required.";
    if (!form.year_id) errors.year_id = "Please select a year.";
    if (!form.semester_id) errors.semester_id = "Please select a semester.";
    if (!form.subject_id) errors.subject_id = "Please select a subject.";
    if (!form.resource_type_id) errors.resource_type_id = "Please select a resource type.";
    if (!form.source_id) errors.source_id = "Please select a source.";
    if (!safeHttpsUrl(form.original_url)) errors.original_url = "Please enter a valid HTTPS URL.";
    setFormErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const submitResource = async (event) => {
    event.preventDefault();
    if (!validateResource()) return;
    setBusy(true);
    setNotice("");
    try {
      const payload = {
        title: form.title,
        description: form.description,
        year_id: form.year_id,
        semester_id: form.semester_id,
        subject_id: form.subject_id,
        resource_type_id: form.resource_type_id,
        source_id: form.source_id,
        original_url: form.original_url,
        resource_format: form.resource_format,
        tags: form.tags,
        display_order: form.display_order,
      };
      if (editing) await api.updateAcademicResource(editing, payload);
      else await api.createAcademicResource(payload);
      setForm(emptyForm);
      setEditing(null);
      setFormErrors({});
      setNotice(editing ? "Resource updated." : "Resource added. Students can open the original URL.");
      setManage("browse");
      await refresh(filters);
    } catch (err) {
      setFormErrors((current) => ({ ...current, form: err.message }));
    } finally {
      setBusy(false);
    }
  };

  const startEdit = (item) => {
    setEditing(item.id);
    setForm({
      title: item.title || "",
      description: item.description || "",
      year_id: item.yearId || "",
      semester_id: item.semesterId || "",
      subject_id: String(item.subjectId || ""),
      resource_type_id: String(item.resourceTypeId || ""),
      source_id: String(item.sourceId || ""),
      original_url: item.originalUrl || "",
      resource_format: item.resourceFormat || "",
      tags: item.tags || "",
      display_order: String(item.displayOrder || 0),
    });
    setManage("resource");
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const runAdmin = async (fn, okMessage) => {
    setBusy(true);
    setNotice("");
    try {
      await fn();
      if (okMessage) setNotice(okMessage);
      await refresh(filters);
      if (isAdmin) {
        const payload = await api.academicReports();
        setReports(payload.reports || []);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const formSemesters = (catalog?.semesters || []).filter((row) => !form.year_id || row.year_id === form.year_id);
  const formSubjects = (catalog?.subjects || []).filter((row) => {
    if (form.year_id && row.year_id !== form.year_id) return false;
    if (form.semester_id && row.semester_id !== form.semester_id) return false;
    return true;
  });
  const subjectSemesters = (catalog?.semesters || []).filter((row) => !subjectForm.year_id || row.year_id === subjectForm.year_id);

  return (
    <div className="co-resources">
      <p className="co-caption">Directory</p>
      <h2 className="mb-2 text-[1.4rem] font-bold">Academic Resources</h2>
      <p className="mb-4 text-sm text-[#64748B]">
        Find notes, PYQs, assignments, practicals and question banks shared through senior academic resources.
      </p>

      {notice && <Notice tone="ok" title={notice} />}
      {error && (
        <Notice
          tone="warn"
          title="Unable to load academic resources. Please try again."
          body={error}
        />
      )}
      {error && (
        <button type="button" className="co-btn co-btn-secondary mb-4" onClick={() => refresh(filters)}>
          Retry
        </button>
      )}
      {catalog && catalog.installed === false && (
        <Notice tone="warn" title="Catalog not installed" body={catalog.detail} />
      )}

      {isAdmin && (
        <div className="mb-4">
          <button
            type="button"
            className="co-btn"
            disabled={busy}
            onClick={() => runAdmin(
              async () => {
                const payload = await api.syncAcademicResources();
                const report = payload.report || {};
                setNotice(
                  `Academic Resource Sync Complete. Sources scanned: ${report.sourcesScanned ?? 0}. Pages: ${report.pagesDiscovered ?? 0}. Discovered: ${report.resourcesDiscovered ?? 0}. New: ${report.newResources ?? 0}. Duplicates: ${report.duplicatesSkipped ?? 0}. Needs review: ${report.needsReview ?? 0}. Failed: ${report.failed ?? 0}.`,
                );
              },
            )}
          >
            Sync registered sources
          </button>
          <p className="mt-2 text-sm text-[#64748B]">Discovers public PDFs and subject pages from The Brain Spot, LDRP, and ColleGPT. Students never trigger this.</p>
        </div>
      )}

      {isAdmin && (
        <div className="co-modules" role="tablist" aria-label="Academic resource management">
          {[
            ["browse", "Browse"],
            ["resource", editing ? "Edit resource" : "Add resource"],
            ["subjects", "Subjects"],
            ["sources", "Sources"],
            ["types", "Types"],
            ["reports", "Broken links"],
          ].map(([id, label]) => (
            <button
              key={id}
              type="button"
              className={`co-btn ${manage === id ? "" : "co-btn-secondary"}`}
              onClick={() => {
                setManage(id);
                if (id === "reports") {
                  api.academicReports().then((payload) => setReports(payload.reports || [])).catch((err) => setError(err.message));
                }
              }}
            >
              {label}
            </button>
          ))}
        </div>
      )}

      {(!isAdmin || manage === "browse") && (
        <>
          <label className="co-field">
            <span>Search academic resources</span>
            <input
              className="co-input"
              type="search"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              placeholder="Search subjects, notes, PYQs, assignments..."
              aria-label="Search subjects, notes, PYQs, assignments"
            />
          </label>

          <div className="co-resource-filters">
            <Field label="Year">
              <select value={filters.year} onChange={(e) => changeFilter("year", e.target.value)}>
                <option value="">All</option>
                {yearOptions.map((row) => <option key={row.id} value={row.id}>{row.label}</option>)}
              </select>
            </Field>
            <Field label="Semester">
              <select value={filters.semester} onChange={(e) => changeFilter("semester", e.target.value)}>
                <option value="">All</option>
                {semesterOptions.map((row) => <option key={row.id} value={row.id}>{row.label}</option>)}
              </select>
            </Field>
            <Field label="Subject">
              <select value={filters.subject} onChange={(e) => changeFilter("subject", e.target.value)}>
                <option value="">All</option>
                {subjectOptions.map((row) => (
                  <option key={row.id} value={row.id}>{row.name}{row.code ? ` (${row.code})` : ""}</option>
                ))}
              </select>
            </Field>
            <Field label="Resource type">
              <select value={filters.type} onChange={(e) => changeFilter("type", e.target.value)}>
                <option value="">All</option>
                {(catalog?.types || []).map((row) => <option key={row.id} value={row.code}>{row.name}</option>)}
              </select>
            </Field>
            <Field label="Source">
              <select value={filters.source} onChange={(e) => changeFilter("source", e.target.value)}>
                <option value="">All</option>
                {(catalog?.sources || []).map((row) => <option key={row.id} value={row.code}>{row.name}</option>)}
              </select>
            </Field>
            <Field label="Sort">
              <select value={filters.sort} onChange={(e) => changeFilter("sort", e.target.value)}>
                <option value="recent">Recently Added</option>
                <option value="updated">Recently Updated</option>
                <option value="alpha">Alphabetical</option>
              </select>
            </Field>
          </div>

          <div className="mb-4 flex flex-wrap items-center gap-3">
            {hasFilters && (
              <button type="button" className="co-btn co-btn-tertiary" onClick={clearFilters}>
                Clear Filters
              </button>
            )}
            {list && (
              <p className="text-sm text-[#64748B]" aria-live="polite">
                {list.total} resource{list.total === 1 ? "" : "s"}
                {list.total > 0 ? ` · page ${list.page}` : ""}
              </p>
            )}
          </div>

          {loading && !list && (
            <div className="co-resource-grid" aria-busy="true" aria-label="Loading academic resources">
              {[1, 2, 3].map((key) => <div key={key} className="co-resource-skel" />)}
            </div>
          )}

          {!loading && list && !(list.items || []).length && (
            <EmptyState
              title={hasFilters ? "No resources match your selected filters." : "No academic resources found."}
              body={hasFilters
                ? "These filters may be too narrow — for example Assignment will not show notes PDFs. Clear Filters to see every imported resource."
                : "No individual resources have been imported yet. An administrator can sync the registered senior websites."}
            />
          )}

          <div className="co-resource-grid">
            {(list?.items || []).map((item) => {
              const href = safeHttpsUrl(item.originalUrl);
              return (
                <article key={item.id} className="co-card co-resource-card">
                  <p className="co-resource-type">{item.resourceType || "Resource"}</p>
                  <h3>{item.title}</h3>
                  <p className="text-sm text-[#64748B]">
                    {item.semesterLabel} · {item.subjectName || "Subject"}
                    {item.subjectCode ? ` (${item.subjectCode})` : ""}
                    {item.yearLabel ? ` · ${item.yearLabel}` : ""}
                  </p>
                  <p className="text-sm text-[#64748B]">
                    Source: {item.sourceName || "Unknown source"}
                    {item.sourceSection ? ` · ${item.sourceSection}` : ""}
                  </p>
                  <p className="text-sm text-[#64748B]">Format: {item.resourceFormat || "WEBPAGE"}</p>
                  {item.description ? <p className="mt-2 text-sm">{item.description}</p> : null}
                  {item.lastVerifiedAt ? (
                    <p className="mt-2 text-xs text-[#64748B]">Last verified {formatWhen(item.lastVerifiedAt)}</p>
                  ) : (
                    <p className="mt-2 text-xs text-[#64748B]">External links can change. Report the resource if it no longer opens.</p>
                  )}
                  <div className="co-resource-actions">
                    {href ? (
                      <a className="co-btn" href={href} target="_blank" rel="noopener noreferrer">
                        {item.resourceFormat === "PDF" ? "Open PDF ↗" : "Open Resource ↗"}
                      </a>
                    ) : (
                      <span className="text-sm text-[#64748B]">This resource URL is not available.</span>
                    )}
                    {isStudent && (
                      <button
                        type="button"
                        className="co-btn co-btn-tertiary"
                        disabled={busy}
                        onClick={() => runAdmin(
                          () => api.reportAcademicResource(item.id, { reason: "Resource link is not working" }),
                          "Report received. An administrator can review this broken link.",
                        )}
                      >
                        Report Broken Link
                      </button>
                    )}
                    {isAdmin && (
                      <>
                        <button type="button" className="co-btn co-btn-secondary" onClick={() => startEdit(item)}>
                          Edit
                        </button>
                        <button
                          type="button"
                          className="co-btn co-btn-tertiary"
                          disabled={busy}
                          onClick={() => runAdmin(() => api.verifyAcademicResource(item.id), "Resource marked as verified.")}
                        >
                          Verify
                        </button>
                        {item.isActive !== false ? (
                          <button
                            type="button"
                            className="co-btn co-btn-tertiary"
                            disabled={busy}
                            onClick={() => runAdmin(() => api.deactivateAcademicResource(item.id), "Resource hidden from students.")}
                          >
                            Deactivate
                          </button>
                        ) : (
                          <button
                            type="button"
                            className="co-btn co-btn-tertiary"
                            disabled={busy}
                            onClick={() => runAdmin(() => api.updateAcademicResource(item.id, { is_active: true }), "Resource is visible again.")}
                          >
                            Activate
                          </button>
                        )}
                      </>
                    )}
                  </div>
                  {isAdmin && item.isActive === false && <p className="mt-2 text-xs text-[#64748B]">Inactive — hidden from students.</p>}
                </article>
              );
            })}
          </div>

          {list && list.total > list.limit && (
            <div className="mt-4 flex flex-wrap items-center gap-3">
              <button
                type="button"
                className="co-btn co-btn-secondary"
                disabled={Number(list.page) <= 1}
                onClick={() => changeFilter("page", String(Number(list.page) - 1))}
              >
                Previous
              </button>
              <p className="text-sm text-[#64748B]">
                Page {list.page} of {Math.max(1, Math.ceil(list.total / list.limit))}
              </p>
              <button
                type="button"
                className="co-btn co-btn-secondary"
                disabled={Number(list.page) * Number(list.limit) >= Number(list.total)}
                onClick={() => changeFilter("page", String(Number(list.page) + 1))}
              >
                Next
              </button>
            </div>
          )}
        </>
      )}

      {isAdmin && manage === "resource" && (
        <form className="co-card space-y-3" onSubmit={submitResource} noValidate>
          <h3 className="font-semibold">{editing ? "Edit resource" : "Add resource"}</h3>
          <p className="text-sm text-[#64748B]">Store metadata and the original source URL. Do not replace the URL with an internal page.</p>
          {formErrors.form && <Notice tone="warn" title={formErrors.form} />}
          <Field label="Title" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} required />
          {formErrors.title && <p className="co-field-error">{formErrors.title}</p>}
          <Field label="Description" as="textarea" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
          <div className="co-resource-filters">
            <Field label="Year">
              <select value={form.year_id} onChange={(e) => setForm({ ...form, year_id: e.target.value, semester_id: "", subject_id: "" })}>
                <option value="">Select year</option>
                {yearOptions.map((row) => <option key={row.id} value={row.id}>{row.label}</option>)}
              </select>
            </Field>
            <Field label="Semester">
              <select value={form.semester_id} onChange={(e) => setForm({ ...form, semester_id: e.target.value, subject_id: "" })}>
                <option value="">Select semester</option>
                {formSemesters.map((row) => <option key={row.id} value={row.id}>{row.label}</option>)}
              </select>
            </Field>
            <Field label="Subject">
              <select value={form.subject_id} onChange={(e) => setForm({ ...form, subject_id: e.target.value })}>
                <option value="">Select subject</option>
                {formSubjects.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}
              </select>
            </Field>
            <Field label="Resource type">
              <select value={form.resource_type_id} onChange={(e) => setForm({ ...form, resource_type_id: e.target.value })}>
                <option value="">Select type</option>
                {(catalog?.types || []).map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}
              </select>
            </Field>
            <Field label="Source">
              <select value={form.source_id} onChange={(e) => setForm({ ...form, source_id: e.target.value })}>
                <option value="">Select source</option>
                {(catalog?.sources || []).map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}
              </select>
            </Field>
            <Field label="Format">
              <select value={form.resource_format} onChange={(e) => setForm({ ...form, resource_format: e.target.value })}>
                <option value="">Auto from URL</option>
                {(catalog?.formats || []).map((row) => <option key={row} value={row}>{row}</option>)}
              </select>
            </Field>
          </div>
          {formErrors.year_id && <p className="co-field-error">{formErrors.year_id}</p>}
          {formErrors.semester_id && <p className="co-field-error">{formErrors.semester_id}</p>}
          {formErrors.subject_id && <p className="co-field-error">{formErrors.subject_id}</p>}
          {formErrors.resource_type_id && <p className="co-field-error">{formErrors.resource_type_id}</p>}
          {formErrors.source_id && <p className="co-field-error">{formErrors.source_id}</p>}
          <Field label="Original URL" type="url" value={form.original_url} onChange={(e) => setForm({ ...form, original_url: e.target.value })} placeholder="https://" required />
          {formErrors.original_url && <p className="co-field-error">{formErrors.original_url}</p>}
          <Field label="Tags" value={form.tags} onChange={(e) => setForm({ ...form, tags: e.target.value })} placeholder="optional, comma separated" />
          <Field label="Display order" type="number" value={form.display_order} onChange={(e) => setForm({ ...form, display_order: e.target.value })} />
          <div className="flex flex-wrap gap-3">
            <button className="co-btn" disabled={busy}>{editing ? "Save resource" : "Add resource"}</button>
            {editing && (
              <button type="button" className="co-btn co-btn-secondary" onClick={() => { setEditing(null); setForm(emptyForm); }}>
                Cancel edit
              </button>
            )}
          </div>
        </form>
      )}

      {isAdmin && manage === "subjects" && (
        <div className="space-y-4">
          <form
            className="co-card space-y-3"
            onSubmit={(e) => {
              e.preventDefault();
              runAdmin(
                () => api.createAcademicSubject(subjectForm),
                "Subject added. It will appear in the subject filter.",
              ).then(() => setSubjectForm({ name: "", code: "", description: "", year_id: "", semester_id: "" }));
            }}
          >
            <h3 className="font-semibold">Add subject</h3>
            <Field label="Name" value={subjectForm.name} onChange={(e) => setSubjectForm({ ...subjectForm, name: e.target.value })} required />
            <Field label="Code" value={subjectForm.code} onChange={(e) => setSubjectForm({ ...subjectForm, code: e.target.value })} placeholder="optional" />
            <Field label="Description" value={subjectForm.description} onChange={(e) => setSubjectForm({ ...subjectForm, description: e.target.value })} />
            <div className="co-resource-filters">
              <Field label="Year">
                <select value={subjectForm.year_id} onChange={(e) => setSubjectForm({ ...subjectForm, year_id: e.target.value, semester_id: "" })}>
                  <option value="">Select year</option>
                  {yearOptions.map((row) => <option key={row.id} value={row.id}>{row.label}</option>)}
                </select>
              </Field>
              <Field label="Semester">
                <select value={subjectForm.semester_id} onChange={(e) => setSubjectForm({ ...subjectForm, semester_id: e.target.value })}>
                  <option value="">Select semester</option>
                  {subjectSemesters.map((row) => <option key={row.id} value={row.id}>{row.label}</option>)}
                </select>
              </Field>
            </div>
            <button className="co-btn" disabled={busy}>Add subject</button>
          </form>
          <div className="co-card">
            <h3 className="mb-3 font-semibold">Subjects</h3>
            <ul className="space-y-2">
              {(catalog?.subjects || []).map((row) => (
                <li key={row.id} className="flex flex-wrap items-center justify-between gap-2">
                  <span>{row.name}{row.code ? ` (${row.code})` : ""} · {row.year_id} · {row.semester_id}</span>
                  <button
                    type="button"
                    className="co-btn co-btn-tertiary"
                    disabled={busy}
                    onClick={() => runAdmin(
                      () => api.updateAcademicSubject(row.id, { status: String(row.status || "ACTIVE").toUpperCase() === "ACTIVE" ? "INACTIVE" : "ACTIVE" }),
                      "Subject status updated.",
                    )}
                  >
                    {String(row.status || "ACTIVE").toUpperCase() === "ACTIVE" ? "Deactivate" : "Activate"}
                  </button>
                </li>
              ))}
              {!(catalog?.subjects || []).length && <li className="text-sm text-[#64748B]">No subjects yet. Add DBMS, OS, or any later subject here.</li>}
            </ul>
          </div>
        </div>
      )}

      {isAdmin && manage === "sources" && (
        <div className="space-y-4">
          <form
            className="co-card space-y-3"
            onSubmit={(e) => {
              e.preventDefault();
              runAdmin(() => api.createAcademicSource(sourceForm), "Source added.").then(() => setSourceForm({ name: "", website_url: "", description: "" }));
            }}
          >
            <h3 className="font-semibold">Add source</h3>
            <Field label="Name" value={sourceForm.name} onChange={(e) => setSourceForm({ ...sourceForm, name: e.target.value })} required />
            <Field label="Website URL" type="url" value={sourceForm.website_url} onChange={(e) => setSourceForm({ ...sourceForm, website_url: e.target.value })} placeholder="https://" required />
            <Field label="Description" value={sourceForm.description} onChange={(e) => setSourceForm({ ...sourceForm, description: e.target.value })} />
            <button className="co-btn" disabled={busy}>Add source</button>
          </form>
          <div className="co-card">
            <h3 className="mb-3 font-semibold">Registered sources</h3>
            <ul className="space-y-3">
              {(catalog?.sources || []).map((row) => {
                const href = safeHttpsUrl(row.website_url || row.websiteUrl);
                return (
                  <li key={row.id}>
                    <strong>{row.name}</strong>
                    <p className="text-sm text-[#64748B]">{row.description}</p>
                    {href && <a className="text-sm" href={href} target="_blank" rel="noopener noreferrer">{href} ↗</a>}
                    <div className="mt-2">
                      <button
                        type="button"
                        className="co-btn co-btn-tertiary"
                        disabled={busy}
                        onClick={() => runAdmin(
                          () => api.updateAcademicSource(row.id, { is_active: row.is_active === false }),
                          "Source status updated.",
                        )}
                      >
                        {row.is_active === false ? "Activate" : "Deactivate"}
                      </button>
                    </div>
                  </li>
                );
              })}
            </ul>
          </div>
        </div>
      )}

      {isAdmin && manage === "types" && (
        <div className="space-y-4">
          <form
            className="co-card space-y-3"
            onSubmit={(e) => {
              e.preventDefault();
              runAdmin(() => api.createAcademicType(typeForm), "Resource type added.").then(() => setTypeForm({ name: "", code: "" }));
            }}
          >
            <h3 className="font-semibold">Add resource type</h3>
            <Field label="Name" value={typeForm.name} onChange={(e) => setTypeForm({ ...typeForm, name: e.target.value })} required />
            <Field label="Code" value={typeForm.code} onChange={(e) => setTypeForm({ ...typeForm, code: e.target.value })} placeholder="optional, e.g. VIDEO" />
            <button className="co-btn" disabled={busy}>Add type</button>
          </form>
          <div className="co-card">
            <h3 className="mb-3 font-semibold">Types</h3>
            <p className="mb-3 text-sm text-[#64748B]">Students see these in the type filter. Adding a type does not require a frontend code change.</p>
            <ul className="space-y-2">
              {(catalog?.types || []).map((row) => <li key={row.id}>{row.name} · {row.code}</li>)}
            </ul>
          </div>
        </div>
      )}

      {isAdmin && manage === "reports" && (
        <div className="co-card">
          <h3 className="mb-3 font-semibold">Reported broken links</h3>
          {!(reports || []).length && <EmptyState title="No broken-link reports yet." />}
          <ul className="space-y-4">
            {reports.map((row) => (
              <li key={row.id} className="border-b border-[var(--co-border)] pb-3 last:border-0">
                <p><strong>{row.resource?.title || `Resource ${row.resourceId}`}</strong></p>
                <p className="text-sm text-[#64748B]">{row.reason} · {row.status} · student {row.studentId}</p>
                {row.resource?.originalUrl && (
                  <a className="text-sm" href={safeHttpsUrl(row.resource.originalUrl) || undefined} target="_blank" rel="noopener noreferrer">
                    {row.resource.originalUrl}
                  </a>
                )}
                {row.status === "PENDING" && (
                  <div className="mt-2 flex flex-wrap gap-2">
                    {["REVIEWED", "RESOLVED", "DISMISSED"].map((status) => (
                      <button
                        key={status}
                        type="button"
                        className="co-btn co-btn-secondary"
                        disabled={busy}
                        onClick={() => runAdmin(() => api.reviewAcademicReport(row.id, { decision: status }), `Report marked ${status.toLowerCase()}.`)}
                      >
                        {status}
                      </button>
                    ))}
                  </div>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
