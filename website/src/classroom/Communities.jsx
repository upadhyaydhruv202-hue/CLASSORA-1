import { useEffect, useState } from "react";
import { api } from "./api";
import { EmptyState, Field, Notice } from "./ui";

function identityLabel(author) {
  if (author?.name) return author.name;
  if (author?.studentId != null) return `Student ID ${author.studentId}`;
  return "Member";
}

function CommunityCard({ item, onOpen, onJoin, busy }) {
  return (
    <article className="co-comm-card">
      <p className="co-section-kicker">{item.category || "Community"}</p>
      <h3>{item.name}</h3>
      <p className="text-sm text-[#64748B]">{item.description}</p>
      <p className="co-comm-meta">{item.memberCount ?? 0} members · {item.status}</p>
      <div className="mt-3 flex flex-wrap gap-2">
        <button type="button" className="co-btn" onClick={() => onOpen(item)}>{item.joined ? "Open" : "View"}</button>
        {!item.joined && item.status === "ACTIVE" && (
          <button type="button" className="co-btn co-btn-secondary" disabled={busy} onClick={() => onJoin(item.id)}>Join</button>
        )}
      </div>
    </article>
  );
}

export function CommunityHealthSummary({ summary, onOpen }) {
  if (!summary?.available) {
    return <EmptyState title="You haven't joined any communities yet." body="Find peers who share your interests." />;
  }
  return (
    <div className="space-y-3">
      <div className="co-chips">
        <div><em>Joined</em><strong>{summary.joinedCount ?? 0}</strong></div>
      </div>
      {onOpen && <button type="button" className="co-btn" onClick={onOpen}>Open Communities</button>}
    </div>
  );
}

export default function Communities({ session }) {
  const isStudent = session?.user_role === "student";
  const isAdmin = session?.user_role === "administrator";
  const [tab, setTab] = useState("discover");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [overview, setOverview] = useState(null);
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");
  const [results, setResults] = useState([]);
  const [current, setCurrent] = useState(null);
  const [page, setPage] = useState("about");
  const [posts, setPosts] = useState([]);
  const [comments, setComments] = useState({});
  const [events, setEvents] = useState([]);
  const [resources, setResources] = useState([]);
  const [members, setMembers] = useState([]);
  const [feed, setFeed] = useState([]);
  const [postText, setPostText] = useState("");
  const [commentFor, setCommentFor] = useState({});
  const [privacy, setPrivacy] = useState(null);
  const [request, setRequest] = useState({ name: "", category: "SPORTS", description: "", purpose: "", reason: "", expectedMembers: "", rules: "" });
  const [matches, setMatches] = useState([]);
  const [requests, setRequests] = useState([]);
  const [reports, setReports] = useState([]);
  const [eventForm, setEventForm] = useState({ title: "", description: "", startAt: "", location: "" });
  const [resourceForm, setResourceForm] = useState({ title: "", url: "", category: "Reference" });

  const loadOverview = async () => {
    const data = await api.communityOverview();
    setOverview(data);
    setResults(data.popular || []);
  };

  useEffect(() => {
    let alive = true;
    setLoading(true);
    loadOverview()
      .catch((err) => { if (alive) setError(err.message || "Communities could not be loaded."); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, []);

  const run = async (fn, ok) => {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await fn();
      if (ok) setNotice(ok);
      return result;
    } catch (err) {
      setError(err.message || "That request failed.");
      return null;
    } finally {
      setBusy(false);
    }
  };

  const openCommunity = async (item) => {
    const detail = await run(() => api.community(item.id || item.slug || item));
    if (!detail) return;
    setCurrent(detail);
    setTab("community");
    setPage("feed");
    const [feedData, ev, res, mem] = await Promise.all([
      api.communityPosts(detail.id),
      api.communityEvents(detail.id),
      api.communityResources(detail.id),
      api.communityMembers(detail.id),
    ]);
    const nextPosts = feedData.posts || [];
    setPosts(nextPosts);
    setEvents(ev.events || []);
    setResources(res.resources || []);
    setMembers(mem.members || []);
    const loaded = {};
    await Promise.all(nextPosts.slice(0, 20).map(async (post) => {
      const data = await api.communityComments(detail.id, post.id);
      loaded[post.id] = data.comments || [];
    }));
    setComments(loaded);
  };

  const searchNow = async () => {
    const data = await run(() => api.communities({ q: search, category }));
    setResults(data?.communities || []);
    setTab("discover");
  };

  return (
    <div className="space-y-4">
      <div>
        <p className="co-section-kicker">Communities</p>
        <h2 className="text-xl font-semibold">Find people who share your interests</h2>
        <p className="text-sm text-[#64748B]">
          Student ID is the default identity. Names and profile details appear only when a student chooses to share them.
          New communities need administrator approval.
        </p>
      </div>
      {error && <Notice title="Communities" body={error} tone="danger" />}
      {notice && <Notice title="Updated" body={notice} tone="ok" />}
      {loading && <p className="text-sm text-[#64748B]">Loading communities…</p>}

      <div className="co-modules" role="tablist" aria-label="Community sections">
        {[["discover", "Discover"], ["mine", "My communities"], isStudent && ["request", "Request"], isStudent && ["privacy", "Privacy"], isAdmin && ["admin", "Admin"]].filter(Boolean).map(([id, label]) => (
          <button key={id} type="button" className={`co-btn ${tab === id ? "" : "co-btn-secondary"}`} onClick={() => setTab(id)}>
            {label}
          </button>
        ))}
      </div>

      {(tab === "discover" || tab === "mine") && (
        <div className="space-y-4">
          <div className="grid gap-3 md:grid-cols-[1fr_auto_auto]">
            <Field label="Search communities" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Cricket, AI, Dance…" />
            <Field label="Category" as="select" value={category} onChange={(e) => setCategory(e.target.value)}>
              <option value="">All</option>
              {(overview?.categories || []).map((item) => <option key={item.code} value={item.code}>{item.name}</option>)}
            </Field>
            <button type="button" className="co-btn self-end" disabled={busy} onClick={searchNow}>Search</button>
          </div>
          <div className="flex flex-wrap gap-2">
            {(overview?.categories || []).map((item) => (
              <button key={item.code} type="button" className={`co-btn ${category === item.code ? "" : "co-btn-tertiary"}`} onClick={() => { const next = category === item.code ? "" : item.code; setCategory(next); setSearch(""); run(() => api.communities({ q: "", category: next }).then((data) => { setResults(data?.communities || []); setTab("discover"); })); }}>
                {item.name}
              </button>
            ))}
          </div>
          {tab === "discover" && (
            <>
              <h3 className="font-semibold">Recommended for you</h3>
              <div className="co-comm-grid">
                {(overview?.recommended || []).map((item) => (
                  <CommunityCard key={item.id} item={item} busy={busy} onOpen={openCommunity} onJoin={(id) => run(() => api.joinCommunity(id).then(loadOverview), "Joined.")} />
                ))}
              </div>
              {!(overview?.recommended || []).length && <EmptyState title="No recommendations yet." body="Select interests in Privacy, or browse all communities." />}
              <h3 className="font-semibold">All communities</h3>
            </>
          )}
          {tab === "mine" && <h3 className="font-semibold">My communities</h3>}
          {tab === "mine" && (
            <div className="space-y-2">
              <button type="button" className="co-btn co-btn-secondary" disabled={busy} onClick={async () => {
                const data = await run(() => api.communityFeed());
                setFeed(data?.posts || []);
              }}>Load my feed</button>
              {feed.map((post) => (
                <article key={post.id} className="co-card">
                  <p className="co-section-kicker">{post.communityName || "Community"} · {identityLabel(post.author)}</p>
                  <p>{post.content}</p>
                </article>
              ))}
            </div>
          )}
          <div className="co-comm-grid">
            {(tab === "mine" ? (overview?.mine || []) : results).map((item) => (
              <CommunityCard key={item.id} item={item} busy={busy} onOpen={openCommunity} onJoin={(id) => run(() => api.joinCommunity(id).then(loadOverview), "Joined.")} />
            ))}
          </div>
          {tab === "mine" && !(overview?.mine || []).length && <EmptyState title="You haven't joined any communities yet." body="Browse Discover and join an approved community." />}
          {tab === "discover" && !results.length && <EmptyState title="No communities match your search." body="Try another keyword, or request a new community." />}
        </div>
      )}

      {tab === "request" && isStudent && (
        <div className="co-card space-y-3">
          <h3 className="font-semibold">Request a new community</h3>
          <p className="text-sm text-[#64748B]">If a similar community exists, join it instead of creating a duplicate.</p>
          <Field label="Community name" value={request.name} onChange={(e) => setRequest({ ...request, name: e.target.value })} />
          <Field label="Category" as="select" value={request.category} onChange={(e) => setRequest({ ...request, category: e.target.value })}>
            {(overview?.categories || []).map((item) => <option key={item.code} value={item.code}>{item.name}</option>)}
          </Field>
          <Field label="Description" as="textarea" rows={3} value={request.description} onChange={(e) => setRequest({ ...request, description: e.target.value })} />
          <Field label="Purpose" as="textarea" rows={2} value={request.purpose} onChange={(e) => setRequest({ ...request, purpose: e.target.value })} />
          <Field label="Why is this needed?" as="textarea" rows={2} value={request.reason} onChange={(e) => setRequest({ ...request, reason: e.target.value })} />
          <Field label="Expected members (optional)" value={request.expectedMembers} onChange={(e) => setRequest({ ...request, expectedMembers: e.target.value })} />
          <Field label="Proposed rules (optional)" as="textarea" rows={2} value={request.rules} onChange={(e) => setRequest({ ...request, rules: e.target.value })} />
          <div className="flex flex-wrap gap-2">
            <button type="button" className="co-btn co-btn-secondary" disabled={busy} onClick={async () => {
              const result = await run(() => api.similarCommunities(request));
              setMatches(result?.matches || []);
            }}>Check similar</button>
            <button type="button" className="co-btn" disabled={busy} onClick={async () => {
              const result = await run(() => api.createCommunityRequest(request));
              if (result?.matches) {
                setMatches(result.matches);
                setNotice(result.message || "A similar community already exists.");
                return;
              }
              if (result?.ok) {
                setNotice("Request sent for administrator review.");
                setRequest({ name: "", category: "SPORTS", description: "", purpose: "", reason: "", expectedMembers: "", rules: "" });
              }
            }}>Submit request</button>
            {matches.length > 0 && (
              <button type="button" className="co-btn co-btn-tertiary" disabled={busy} onClick={async () => {
                const result = await run(() => api.createCommunityRequest({ ...request, continueDespiteDuplicates: true }), "Submitted with a potential-duplicate flag for admin review.");
                if (result?.ok) setMatches([]);
              }}>Continue request anyway</button>
            )}
          </div>
          {matches.map((item) => (
            <div key={item.id} className="co-notice co-notice-warn">
              <strong>Similar community found: {item.name}</strong>
              <p>{item.description} · {item.flag.replaceAll("_", " ")}</p>
              <button type="button" className="co-btn mt-2" onClick={() => openCommunity(item)}>View {item.name}</button>
            </div>
          ))}
          {(overview?.myRequests || []).map((item) => (
            <div key={item.id} className="text-sm">
              <p>{item.name} · {item.status}{item.reviewReason ? ` · ${item.reviewReason}` : ""}</p>
              {item.status === "CHANGES_REQUESTED" && (
                <button type="button" className="co-btn co-btn-secondary mt-2" disabled={busy} onClick={() => run(async () => {
                  await api.updateCommunityRequest(item.id, request);
                  await loadOverview();
                }, "Request updated and sent back for review.")}>Resubmit with the form above</button>
              )}
            </div>
          ))}
        </div>
      )}

      {tab === "privacy" && isStudent && (
        <div className="co-card space-y-3">
          <h3 className="font-semibold">Community identity</h3>
          <p className="text-sm text-[#64748B]">Student ID is always shown. Optional fields stay off until you enable them.</p>
          <button type="button" className="co-btn co-btn-secondary" disabled={busy} onClick={async () => setPrivacy(await run(() => api.communityPrivacy()))}>
            Load my settings
          </button>
          {privacy && (
            <>
              <p>Preview others see: <strong>{identityLabel(privacy.preview)}</strong></p>
              {[
                ["showName", "Show display name"],
                ["showBio", "Show bio"],
                ["showSkills", "Show skills"],
                ["showDepartment", "Show course"],
                ["showSemester", "Show semester"],
                ["showPortfolio", "Show portfolio link"],
              ].map(([key, label]) => (
                <label key={key} className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={!!privacy[key]} onChange={(e) => setPrivacy({ ...privacy, [key]: e.target.checked })} />
                  {label}
                </label>
              ))}
              <Field label="Display name" value={privacy.displayName || ""} onChange={(e) => setPrivacy({ ...privacy, displayName: e.target.value })} />
              <Field label="Bio" value={privacy.bio || ""} onChange={(e) => setPrivacy({ ...privacy, bio: e.target.value })} />
              <Field label="Skills" value={privacy.skills || ""} onChange={(e) => setPrivacy({ ...privacy, skills: e.target.value })} />
              <Field label="Interests (comma separated)" value={(privacy.interests || []).join(", ")} onChange={(e) => setPrivacy({ ...privacy, interests: e.target.value.split(",").map((item) => item.trim()).filter(Boolean) })} />
              <Field label="Notifications" as="select" value={privacy.notifyPref || "ALL"} onChange={(e) => setPrivacy({ ...privacy, notifyPref: e.target.value })}>
                <option value="ALL">All</option>
                <option value="ANNOUNCEMENTS">Announcements only</option>
                <option value="EVENTS">Events only</option>
                <option value="NONE">None</option>
              </Field>
              <button type="button" className="co-btn" disabled={busy} onClick={() => run(() => api.saveCommunityPrivacy(privacy), "Privacy saved.")}>Save privacy</button>
            </>
          )}
        </div>
      )}

      {tab === "admin" && isAdmin && (
        <div className="space-y-4">
          <button type="button" className="co-btn" disabled={busy} onClick={async () => {
            setRequests((await run(() => api.communityRequests()))?.requests || []);
            setReports((await api.communityReports())?.reports || []);
          }}>Refresh requests and reports</button>
          {(requests || []).map((item) => (
            <article key={item.id} className="co-card">
              <h3>{item.name} · {item.status}</h3>
              <p className="text-sm">Requester student ID: {item.requestedBy ?? "—"}</p>
              <p className="text-sm">{item.description}</p>
              <p className="text-sm">Reason: {item.reason}</p>
              {item.duplicateFlag && <Notice title="Potential duplicate" body={(item.matches || []).map((m) => m.name).join(", ") || "Similar community flagged."} tone="warn" />}
              {item.status === "PENDING" && (
                <div className="mt-2 flex flex-wrap gap-2">
                  <button type="button" className="co-btn" disabled={busy} onClick={() => run(() => api.reviewCommunityRequest(item.id, { decision: "APPROVE" }).then(() => api.communityRequests().then((d) => setRequests(d.requests || []))), "Approved.")}>Approve</button>
                  <button type="button" className="co-btn co-btn-secondary" disabled={busy} onClick={() => run(() => api.reviewCommunityRequest(item.id, { decision: "REJECT", reason: "Does not meet community guidelines." }).then(() => api.communityRequests().then((d) => setRequests(d.requests || []))), "Rejected.")}>Reject</button>
                  <button type="button" className="co-btn co-btn-tertiary" disabled={busy} onClick={() => run(() => api.reviewCommunityRequest(item.id, { decision: "CHANGES", reason: "Please clarify how this differs from existing communities." }).then(() => api.communityRequests().then((d) => setRequests(d.requests || []))), "Changes requested.")}>Request changes</button>
                </div>
              )}
            </article>
          ))}
          {(reports || []).map((item) => (
            <article key={item.id} className="co-card">
              <p>{item.reason} · {item.status}</p>
              <p className="text-sm">{item.description}</p>
              {item.status === "OPEN" && (
                <button type="button" className="co-btn mt-2" disabled={busy} onClick={() => run(() => api.resolveCommunityReport(item.id, { action: "CONTENT_REMOVED", reason: "Removed after review." }).then(() => api.communityReports().then((d) => setReports(d.reports || []))), "Report resolved.")}>Remove content</button>
              )}
            </article>
          ))}
        </div>
      )}

      {tab === "community" && current && (
        <div className="space-y-4">
          <div className="co-card">
            <p className="co-section-kicker">{current.category}</p>
            <h2 className="text-xl font-semibold">{current.name}</h2>
            <p>{current.description}</p>
            <p className="co-comm-meta">{current.memberCount} members · {current.status}</p>
            {current.status === "SUSPENDED" && <Notice title="This community is currently suspended." body="New posts and joins are paused." tone="warn" />}
            <div className="mt-3 flex flex-wrap gap-2">
              {!current.joined && current.status === "ACTIVE" && <button type="button" className="co-btn" disabled={busy} onClick={() => run(() => api.joinCommunity(current.id).then(() => openCommunity(current)), "Joined.")}>Join</button>}
              {current.joined && <button type="button" className="co-btn co-btn-secondary" disabled={busy} onClick={() => run(() => api.leaveCommunity(current.id).then(loadOverview), "Left.").then(() => setTab("discover"))}>Leave</button>}
              <button type="button" className="co-btn co-btn-tertiary" onClick={() => run(() => api.createCommunityReport({ communityId: current.id, targetType: "COMMUNITY", reason: "Other", description: "Reported from community page." }), "Report submitted.")}>Report</button>
            </div>
          </div>
          <div className="co-modules">
            {["feed", "events", "resources", "about"].map((id) => (
              <button key={id} type="button" className={`co-btn ${page === id ? "" : "co-btn-secondary"}`} onClick={() => setPage(id)}>{id[0].toUpperCase() + id.slice(1)}</button>
            ))}
          </div>
          {page === "feed" && (
            <div className="space-y-3">
              {current.canPost && (
                <div className="co-card space-y-2">
                  <Field label="Start a discussion" as="textarea" rows={3} value={postText} onChange={(e) => setPostText(e.target.value)} />
                  <button type="button" className="co-btn" disabled={busy || !postText.trim()} onClick={() => run(async () => {
                    await api.createCommunityPost(current.id, { content: postText, kind: current.canModerate && postText.toLowerCase().includes("announce") ? "ANNOUNCEMENT" : "POST" });
                    setPostText("");
                    setPosts((await api.communityPosts(current.id)).posts || []);
                  }, "Posted.")}>Post</button>
                </div>
              )}
              {!posts.length && <EmptyState title="Be the first to start a discussion." />}
              {posts.map((post) => (
                <article key={post.id} className={`co-card ${post.kind === "ANNOUNCEMENT" ? "co-comm-announce" : ""}`}>
                  <p className="co-section-kicker">{post.kind === "ANNOUNCEMENT" ? "Announcement" : identityLabel(post.author)}</p>
                  <p>{post.content}</p>
                  {post.link ? <p className="text-sm"><a href={post.link} target="_blank" rel="noreferrer noopener">{post.link}</a></p> : null}
                  <div className="mt-2 flex flex-wrap gap-2">
                    {["LIKE", "INTERESTED", "HELPFUL"].map((kind) => (
                      <button key={kind} type="button" className="co-btn co-btn-tertiary" disabled={busy} onClick={() => run(async () => {
                        await api.reactCommunityPost(current.id, post.id, { kind });
                        setPosts((await api.communityPosts(current.id)).posts || []);
                      })}>{kind[0] + kind.slice(1).toLowerCase()} {post.reactions?.[kind] || 0}</button>
                    ))}
                    {current.canModerate && <button type="button" className="co-btn co-btn-tertiary" onClick={() => run(async () => { await api.removeCommunityPost(current.id, post.id); setPosts((await api.communityPosts(current.id)).posts || []); }, "Removed.")}>Remove</button>}
                  </div>
                  <ul className="mt-2 space-y-1 text-sm">
                    {(comments[post.id] || []).map((item) => (
                      <li key={item.id}><strong>{identityLabel(item.author)}</strong>: {item.content}</li>
                    ))}
                  </ul>
                  <Field label="Comment" value={commentFor[post.id] || ""} onChange={(e) => setCommentFor({ ...commentFor, [post.id]: e.target.value })} />
                  <button type="button" className="co-btn co-btn-secondary" disabled={busy} onClick={() => run(async () => {
                    await api.createCommunityComment(current.id, post.id, { content: commentFor[post.id] });
                    setCommentFor({ ...commentFor, [post.id]: "" });
                    const data = await api.communityComments(current.id, post.id);
                    setComments((prev) => ({ ...prev, [post.id]: data.comments || [] }));
                  }, "Comment added.")}>Comment</button>
                </article>
              ))}
            </div>
          )}
          {page === "events" && (
            <div className="space-y-3">
              {current.canModerate && (
                <div className="co-card space-y-2">
                  <Field label="Event title" value={eventForm.title} onChange={(e) => setEventForm({ ...eventForm, title: e.target.value })} />
                  <Field label="Description" value={eventForm.description} onChange={(e) => setEventForm({ ...eventForm, description: e.target.value })} />
                  <Field label="Start" value={eventForm.startAt} onChange={(e) => setEventForm({ ...eventForm, startAt: e.target.value })} placeholder="2026-08-24 17:00" />
                  <Field label="Location" value={eventForm.location} onChange={(e) => setEventForm({ ...eventForm, location: e.target.value })} />
                  <button type="button" className="co-btn" disabled={busy} onClick={() => run(async () => {
                    await api.createCommunityEvent(current.id, eventForm);
                    setEvents((await api.communityEvents(current.id)).events || []);
                  }, "Event created.")}>Create event</button>
                </div>
              )}
              {!events.length && <EmptyState title="No events yet." />}
              {events.map((item) => (
                <article key={item.id} className="co-card">
                  <h3>{item.title}</h3>
                  <p className="text-sm">{item.description}</p>
                  <p className="co-comm-meta">{item.startAt || "Time TBA"} · {item.location || "Location TBA"} · {item.registeredCount} registered</p>
                  {current.joined && !item.registered && <button type="button" className="co-btn mt-2" disabled={busy} onClick={() => run(async () => { await api.registerCommunityEvent(current.id, item.id); setEvents((await api.communityEvents(current.id)).events || []); }, "Registered.")}>Register</button>}
                  {item.registered && <button type="button" className="co-btn co-btn-secondary mt-2" disabled={busy} onClick={() => run(async () => { await api.cancelCommunityEvent(current.id, item.id); setEvents((await api.communityEvents(current.id)).events || []); }, "Registration cancelled.")}>Cancel registration</button>}
                </article>
              ))}
            </div>
          )}
          {page === "resources" && (
            <div className="space-y-3">
              {current.canPost && (
                <div className="co-card space-y-2">
                  <Field label="Title" value={resourceForm.title} onChange={(e) => setResourceForm({ ...resourceForm, title: e.target.value })} />
                  <Field label="https link" value={resourceForm.url} onChange={(e) => setResourceForm({ ...resourceForm, url: e.target.value })} />
                  <button type="button" className="co-btn" disabled={busy} onClick={() => run(async () => {
                    await api.createCommunityResource(current.id, resourceForm);
                    setResources((await api.communityResources(current.id)).resources || []);
                  }, "Resource added.")}>Share resource</button>
                </div>
              )}
              {!resources.length && <EmptyState title="No shared resources yet." />}
              {resources.map((item) => (
                <article key={item.id} className="co-card">
                  <h3>{item.title}</h3>
                  {item.url ? <a href={item.url} target="_blank" rel="noreferrer noopener">{item.url}</a> : <p>{item.note}</p>}
                </article>
              ))}
            </div>
          )}
          {page === "about" && (
            <div className="space-y-3">
              <div className="co-card">
                <h3 className="font-semibold">Rules</h3>
                <pre className="whitespace-pre-wrap text-sm">{current.rules}</pre>
              </div>
              <div className="co-card">
                <h3 className="mb-2 font-semibold">Members</h3>
                <ul className="space-y-1 text-sm">
                  {members.map((item) => <li key={item.studentId}>{identityLabel(item)}{item.role && item.role !== "MEMBER" ? ` · ${item.role.replaceAll("_", " ")}` : ""}</li>)}
                </ul>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
