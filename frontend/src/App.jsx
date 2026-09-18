import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  BarChart3,
  BookOpen,
  Database,
  FileText,
  LayoutDashboard,
  LogOut,
  MessageSquare,
  RefreshCw,
  Search,
  Send,
  Shield,
  Upload,
} from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ApiError, createApiClient } from "./api";

const STORAGE_KEY = "cmpdi_demo_auth";
const UPLOAD_JOB_POLL_INTERVAL_MS = 1000;
const UPLOAD_JOB_POLL_TIMEOUT_MS = 120000;
const TERMINAL_JOB_STATUSES = new Set(["completed", "failed"]);
const NAV_ITEMS = [
  { id: "dashboard", label: "Dashboard", icon: LayoutDashboard },
  { id: "documents", label: "Documents", icon: FileText },
  { id: "qa", label: "Q&A", icon: MessageSquare },
  { id: "reports", label: "Reports", icon: BookOpen },
  { id: "search", label: "Search", icon: Search },
  { id: "analytics", label: "Analytics", icon: BarChart3 },
];
const COLORS = ["#0f766e", "#2563eb", "#ca8a04", "#dc2626", "#7c3aed", "#0891b2"];

function App() {
  const [auth, setAuth] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem(STORAGE_KEY) || "null");
    } catch {
      return null;
    }
  });
  const [active, setActive] = useState("dashboard");
  const [appError, setAppError] = useState("");

  const logout = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY);
    setAuth(null);
    setActive("dashboard");
  }, []);

  const api = useMemo(() => createApiClient(() => auth?.access_token, logout), [auth, logout]);
  const canWrite = auth?.user?.role === "admin" || auth?.user?.role === "analyst";

  const onLogin = (loginResult) => {
    const nextAuth = {
      access_token: loginResult.access_token,
      user: loginResult.user,
    };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(nextAuth));
    setAuth(nextAuth);
    setAppError("");
  };

  if (!auth?.access_token) {
    return <LoginScreen api={api} onLogin={onLogin} />;
  }

  return (
    <div className="min-h-screen bg-slate-100 text-slate-900">
      <div className="flex min-h-screen">
        <aside className="hidden w-64 shrink-0 border-r border-slate-200 bg-slate-950 text-white lg:block">
          <div className="px-5 py-5">
            <div className="text-sm font-semibold text-cyan-200">CMPDI/CIL</div>
            <div className="mt-1 text-lg font-bold">AI Reporting</div>
          </div>
          <nav className="space-y-1 px-3">
            {NAV_ITEMS.map((item) => (
              <NavButton key={item.id} item={item} active={active === item.id} onClick={() => setActive(item.id)} />
            ))}
          </nav>
        </aside>

        <div className="flex min-w-0 flex-1 flex-col">
          <header className="border-b border-slate-200 bg-white">
            <div className="flex flex-col gap-3 px-4 py-4 lg:flex-row lg:items-center lg:justify-between lg:px-6">
              <div>
                <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Geological reporting workspace</div>
                <h1 className="mt-1 text-xl font-bold text-slate-950">{NAV_ITEMS.find((item) => item.id === active)?.label}</h1>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <div className="flex items-center gap-2 rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm">
                  <Shield className="h-4 w-4 text-teal-700" />
                  <span className="font-medium">{auth.user.email}</span>
                  <RoleBadge role={auth.user.role} />
                </div>
                <button className="inline-flex items-center gap-2 rounded-md bg-slate-900 px-3 py-2 text-sm font-semibold text-white hover:bg-slate-700" onClick={logout}>
                  <LogOut className="h-4 w-4" />
                  Logout
                </button>
              </div>
            </div>
            <div className="flex gap-2 overflow-x-auto border-t border-slate-100 px-4 py-2 lg:hidden">
              {NAV_ITEMS.map((item) => (
                <button
                  key={item.id}
                  onClick={() => setActive(item.id)}
                  className={`whitespace-nowrap rounded-md px-3 py-2 text-sm font-semibold ${active === item.id ? "bg-slate-900 text-white" : "bg-white text-slate-700"}`}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </header>

          <main className="flex-1 overflow-y-auto px-4 py-5 lg:px-6">
            {appError ? <Alert tone="error" title="Session notice" message={appError} /> : null}
            {active === "dashboard" && <Dashboard api={api} />}
            {active === "documents" && <Documents api={api} canWrite={canWrite} />}
            {active === "qa" && <QA api={api} />}
            {active === "reports" && <Reports api={api} canWrite={canWrite} user={auth.user} />}
            {active === "search" && <SemanticSearch api={api} />}
            {active === "analytics" && <Analytics api={api} />}
          </main>
        </div>
      </div>
    </div>
  );
}

function LoginScreen({ api, onLogin }) {
  const [email, setEmail] = useState("analyst@cmpdi.local");
  const [password, setPassword] = useState("AnalystPass123!");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function submit(event) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      onLogin(await api.login(email, password));
    } catch (err) {
      setError(formatError(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="grid min-h-screen place-items-center bg-slate-100 px-4">
      <div className="w-full max-w-md rounded-lg border border-slate-200 bg-white p-6 shadow-panel">
        <div className="mb-6">
          <div className="text-sm font-semibold text-teal-700">CMPDI/CIL</div>
          <h1 className="mt-1 text-2xl font-bold text-slate-950">AI Reporting Platform</h1>
        </div>
        <form className="space-y-4" onSubmit={submit}>
          <Field label="Email">
            <input className="input" value={email} onChange={(event) => setEmail(event.target.value)} type="email" />
          </Field>
          <Field label="Password">
            <input className="input" value={password} onChange={(event) => setPassword(event.target.value)} type="password" />
          </Field>
          {error ? <Alert tone="error" message={error} /> : null}
          <button className="inline-flex w-full items-center justify-center gap-2 rounded-md bg-teal-700 px-4 py-2.5 text-sm font-semibold text-white hover:bg-teal-800 disabled:cursor-not-allowed disabled:opacity-60" disabled={loading}>
            <Shield className="h-4 w-4" />
            {loading ? "Signing in..." : "Sign in"}
          </button>
        </form>
      </div>
    </div>
  );
}

function Dashboard({ api }) {
  const { data, error, loading, reload } = useApiLoad(api.summary);
  const cards = [
    ["Total documents", data?.total_documents, FileText],
    ["Processed", data?.processed_documents, Activity],
    ["Failed", data?.failed_documents, Activity],
    ["Total chunks", data?.total_chunks, Database],
    ["Embedded chunks", data?.chunks_with_embeddings, Database],
    ["Reports", data?.total_reports, BookOpen],
    ["Q&A answers", data?.total_qa_answers, MessageSquare],
  ];

  return (
    <PageSection title="Operations Dashboard" action={<RefreshButton onClick={reload} loading={loading} />}>
      <LoadState loading={loading} error={error} />
      {data ? (
        <>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {cards.map(([label, value, Icon]) => (
              <MetricCard key={label} label={label} value={value} Icon={Icon} />
            ))}
          </div>
          <div className="mt-4 grid gap-4 xl:grid-cols-2">
            <ChartPanel title="Documents by file type" data={objectToRows(data.documents_by_file_type)} kind="bar" />
            <ChartPanel title="Documents by processing status" data={objectToRows(data.documents_by_processing_status)} kind="pie" />
          </div>
        </>
      ) : null}
    </PageSection>
  );
}

function Documents({ api, canWrite }) {
  const { data: documents, error, loading, reload } = useApiLoad(api.listDocuments);
  const [selectedId, setSelectedId] = useState(null);
  const [uploadResult, setUploadResult] = useState(null);
  const [job, setJob] = useState(null);
  const [uploadError, setUploadError] = useState("");
  const [pollTimedOut, setPollTimedOut] = useState(false);
  const [uploading, setUploading] = useState(false);
  const uploadStatus = job?.status || uploadResult?.processing_status;
  const uploadComplete = uploadStatus === "completed";
  const uploadFailed = uploadStatus === "failed";

  async function upload(event) {
    event.preventDefault();
    const file = event.currentTarget.file.files[0];
    if (!file) return;
    setUploading(true);
    setUploadError("");
    setJob(null);
    setPollTimedOut(false);
    try {
      const result = await api.uploadDocument(file);
      setUploadResult(result);
      reload();
    } catch (err) {
      setUploadError(formatError(err));
    } finally {
      setUploading(false);
    }
  }

  const refreshJob = useCallback(async () => {
    if (!uploadResult?.job_id) return;
    try {
      const latestJob = await api.getJob(uploadResult.job_id);
      setJob(latestJob);
      reload();
      if (latestJob.status === "completed") {
        setSelectedId(latestJob.document_id || uploadResult.document_id);
      }
      return latestJob;
    } catch (err) {
      setUploadError(formatError(err));
    }
  }, [api, reload, uploadResult?.document_id, uploadResult?.job_id]);

  useEffect(() => {
    if (!uploadResult?.job_id || !canWrite) return undefined;
    let active = true;
    let inFlight = false;
    let intervalId;
    let timeoutId;

    const stopPolling = () => {
      window.clearInterval(intervalId);
      window.clearTimeout(timeoutId);
    };

    const pollJob = async () => {
      if (!active || inFlight) return;
      inFlight = true;
      try {
        const latestJob = await api.getJob(uploadResult.job_id);
        if (!active) return;
        setJob(latestJob);
        if (TERMINAL_JOB_STATUSES.has(latestJob.status)) {
          stopPolling();
          reload();
          if (latestJob.status === "completed") {
            setSelectedId(latestJob.document_id || uploadResult.document_id);
          }
        }
      } catch (err) {
        if (!active) return;
        stopPolling();
        setUploadError(formatError(err));
      } finally {
        inFlight = false;
      }
    };

    pollJob();
    intervalId = window.setInterval(pollJob, UPLOAD_JOB_POLL_INTERVAL_MS);
    timeoutId = window.setTimeout(() => {
      if (!active) return;
      stopPolling();
      setPollTimedOut(true);
      setUploadError("Timed out waiting for ingestion to finish. Use Refresh job to check the latest status.");
    }, UPLOAD_JOB_POLL_TIMEOUT_MS);

    return () => {
      active = false;
      stopPolling();
    };
  }, [api, canWrite, reload, uploadResult?.document_id, uploadResult?.job_id]);

  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_420px]">
      <PageSection title="Documents" action={<RefreshButton onClick={reload} loading={loading} />}>
        <LoadState loading={loading} error={error} />
        {canWrite ? (
          <form className="mb-4 rounded-lg border border-slate-200 bg-white p-4" onSubmit={upload}>
            <div className="flex flex-col gap-3 md:flex-row md:items-end">
              <Field label="Upload document">
                <input name="file" type="file" className="input file:mr-3 file:rounded-md file:border-0 file:bg-slate-900 file:px-3 file:py-1.5 file:text-sm file:font-semibold file:text-white" />
              </Field>
              <button className="inline-flex items-center justify-center gap-2 rounded-md bg-teal-700 px-4 py-2.5 text-sm font-semibold text-white hover:bg-teal-800 disabled:opacity-60" disabled={uploading}>
                <Upload className="h-4 w-4" />
                {uploading ? "Uploading..." : "Upload"}
              </button>
            </div>
            {uploadError ? <div className="mt-3"><Alert tone="error" message={uploadError} /></div> : null}
            {uploadResult ? (
              <div className={`mt-3 rounded-md p-3 text-sm ${uploadFailed ? "bg-red-50 text-red-900" : uploadComplete ? "bg-emerald-50 text-emerald-900" : "bg-teal-50 text-teal-900"}`}>
                <div className="flex flex-wrap items-center gap-2">
                  <span>document_id={uploadResult.document_id}; job_id={uploadResult.job_id}; status=</span>
                  <StatusBadge status={uploadStatus} />
                </div>
                <button type="button" onClick={refreshJob} className="ml-3 inline-flex items-center gap-1 rounded-md bg-white px-2 py-1 font-semibold text-teal-800">
                  <RefreshCw className="h-3.5 w-3.5" /> Refresh job
                </button>
                {uploadComplete ? (
                  <button type="button" onClick={() => { setSelectedId(uploadResult.document_id); reload(); }} className="ml-2 inline-flex items-center gap-1 rounded-md bg-white px-2 py-1 font-semibold text-emerald-800">
                    <FileText className="h-3.5 w-3.5" /> View document
                  </button>
                ) : null}
                {job ? <div className="mt-2">Job status: <StatusBadge status={job.status} /> {job.error_message || ""}</div> : null}
                {pollTimedOut ? <div className="mt-2 font-semibold">Polling timed out before the job reached a terminal state.</div> : null}
              </div>
            ) : null}
          </form>
        ) : (
          <Alert tone="info" message="Viewer role has read-only document access." />
        )}

        <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
          <div className="grid grid-cols-[80px_minmax(160px,1fr)_100px_120px] gap-3 border-b border-slate-100 px-4 py-3 text-xs font-bold uppercase text-slate-500">
            <span>ID</span><span>Filename</span><span>Type</span><span>Status</span>
          </div>
          {documents?.length ? documents.map((document) => (
            <button key={document.id} onClick={() => setSelectedId(document.id)} className="grid w-full grid-cols-[80px_minmax(160px,1fr)_100px_120px] gap-3 border-b border-slate-100 px-4 py-3 text-left text-sm hover:bg-slate-50">
              <span className="font-semibold">{document.id}</span>
              <span className="truncate">{document.filename}</span>
              <span>{document.file_type}</span>
              <StatusBadge status={document.processing_status} />
            </button>
          )) : <EmptyState label="No documents found" />}
        </div>
      </PageSection>
      <DocumentDetail api={api} documentId={selectedId || documents?.[0]?.id} />
    </div>
  );
}

function DocumentDetail({ api, documentId }) {
  const [document, setDocument] = useState(null);
  const [chunks, setChunks] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!documentId) return;
    let active = true;
    setLoading(true);
    setError("");
    Promise.all([api.getDocument(documentId), api.getDocumentChunks(documentId)])
      .then(([doc, chunkRows]) => {
        if (!active) return;
        setDocument(doc);
        setChunks(chunkRows);
      })
      .catch((err) => active && setError(formatError(err)))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [api, documentId]);

  return (
    <PageSection title="Document Detail">
      <LoadState loading={loading} error={error} />
      {!documentId ? <EmptyState label="Select a document" /> : null}
      {document ? (
        <div className="space-y-3">
          <div className="rounded-lg border border-slate-200 bg-white p-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="text-sm font-bold">{document.filename}</div>
                <div className="mt-1 text-xs text-slate-500">{document.object_path}</div>
              </div>
              <StatusBadge status={document.processing_status} />
            </div>
            {document.processing_error ? <div className="mt-2 text-sm text-red-700">{document.processing_error}</div> : null}
          </div>
          {chunks.length ? chunks.map((chunk) => (
            <div key={chunk.id} className="rounded-lg border border-slate-200 bg-white p-4">
              <div className="mb-2 flex flex-wrap items-center gap-2 text-xs text-slate-500">
                <span>chunk #{chunk.chunk_index}</span>
                <span>chunk_id={chunk.id}</span>
                <span>{chunk.source_reference}</span>
                <span className={`rounded px-2 py-0.5 font-semibold ${chunk.embedding_exists ? "bg-emerald-100 text-emerald-800" : "bg-amber-100 text-amber-800"}`}>
                  embedding={String(chunk.embedding_exists)}
                </span>
              </div>
              <p className="whitespace-pre-wrap text-sm leading-6 text-slate-700">{chunk.text}</p>
            </div>
          )) : <EmptyState label="No chunks for this document" />}
        </div>
      ) : null}
    </PageSection>
  );
}

function QA({ api }) {
  const [question, setQuestion] = useState("What production target or coal seam information is available?");
  const [answer, setAnswer] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const loadHistory = useCallback(() => api.qaHistory(20), [api]);
  const { data: history, reload } = useApiLoad(loadHistory);

  async function submit(event) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      const result = await api.askQuestion(question, 5);
      setAnswer(result);
      reload();
    } catch (err) {
      setError(formatError(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_380px]">
      <PageSection title="Ask Q&A">
        <form onSubmit={submit} className="rounded-lg border border-slate-200 bg-white p-4">
          <Field label="Question">
            <textarea className="input min-h-24" value={question} onChange={(event) => setQuestion(event.target.value)} />
          </Field>
          <div className="mt-3 flex justify-end">
            <button className="inline-flex items-center gap-2 rounded-md bg-teal-700 px-4 py-2 text-sm font-semibold text-white hover:bg-teal-800 disabled:opacity-60" disabled={loading}>
              <Send className="h-4 w-4" />
              {loading ? "Asking..." : "Ask"}
            </button>
          </div>
          {error ? <div className="mt-3"><Alert tone="error" message={error} /></div> : null}
        </form>
        {answer ? (
          <div className="mt-4 rounded-lg border border-slate-200 bg-white p-4">
            <div className="mb-2 flex items-center gap-2">
              <span className="text-xs font-bold uppercase text-slate-500">Mode</span>
              <span className="rounded bg-cyan-100 px-2 py-0.5 text-xs font-semibold text-cyan-800">{answer.mode}</span>
            </div>
            <p className="whitespace-pre-wrap text-sm leading-6 text-slate-800">{answer.answer}</p>
            <CitationList citations={answer.citations} />
          </div>
        ) : null}
      </PageSection>
      <PageSection title="Q&A History">
        {history?.length ? history.map((item) => (
          <div key={item.id} className="mb-3 rounded-lg border border-slate-200 bg-white p-3">
            <div className="text-sm font-semibold">{item.question}</div>
            <p className="mt-1 line-clamp-3 text-sm text-slate-600">{item.answer}</p>
          </div>
        )) : <EmptyState label="No Q&A history" />}
      </PageSection>
    </div>
  );
}

function SemanticSearch({ api }) {
  const [query, setQuery] = useState("coal seam reserve");
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function submit(event) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      setResults(await api.semanticSearch(query, 5));
    } catch (err) {
      setError(formatError(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <PageSection title="Semantic Search">
      <form onSubmit={submit} className="mb-4 flex flex-col gap-3 rounded-lg border border-slate-200 bg-white p-4 md:flex-row">
        <input className="input" value={query} onChange={(event) => setQuery(event.target.value)} />
        <button className="inline-flex items-center justify-center gap-2 rounded-md bg-teal-700 px-4 py-2 text-sm font-semibold text-white hover:bg-teal-800 disabled:opacity-60" disabled={loading}>
          <Search className="h-4 w-4" />
          Search
        </button>
      </form>
      <LoadState loading={loading} error={error} />
      {results.length ? results.map((result) => (
        <div key={result.chunk_id} className="mb-3 rounded-lg border border-slate-200 bg-white p-4">
          <div className="mb-2 flex flex-wrap gap-2 text-xs text-slate-500">
            <span className="font-semibold text-slate-700">{result.filename}</span>
            <span>document_id={result.document_id}</span>
            <span>chunk_id={result.chunk_id}</span>
            <span>similarity={formatNumber(result.similarity)}</span>
            <span>{result.source_reference}</span>
          </div>
          <p className="whitespace-pre-wrap text-sm leading-6 text-slate-700">{result.text_snippet}</p>
        </div>
      )) : <EmptyState label="No search results loaded" />}
    </PageSection>
  );
}

function Reports({ api, canWrite, user }) {
  const { data: reports, error, loading, reload } = useApiLoad(api.listReports);
  const [title, setTitle] = useState("Geological and Mining Summary Report");
  const [selected, setSelected] = useState(null);
  const [detail, setDetail] = useState(null);
  const [versions, setVersions] = useState([]);
  const [actionError, setActionError] = useState("");
  const [approvalNote, setApprovalNote] = useState("");
  const [generating, setGenerating] = useState(false);
  const [workflowBusy, setWorkflowBusy] = useState("");
  const isAdmin = user?.role === "admin";

  async function generate(event) {
    event.preventDefault();
    setGenerating(true);
    setActionError("");
    try {
      const report = await api.generateReport({ title, report_type: "geological_summary" });
      setSelected(report.id);
      setDetail(report);
      setVersions([report]);
      reload();
    } catch (err) {
      setActionError(formatError(err));
    } finally {
      setGenerating(false);
    }
  }

  async function openReport(id) {
    setSelected(id);
    setActionError("");
    try {
      const [report, versionRows] = await Promise.all([api.getReport(id), api.getReportVersions(id)]);
      setDetail(report);
      setVersions(versionRows);
      setApprovalNote(report.approval_note || "");
    } catch (err) {
      setActionError(formatError(err));
    }
  }

  async function runWorkflow(action, handler) {
    if (!detail) return;
    setWorkflowBusy(action);
    setActionError("");
    try {
      const report = await handler(detail.id);
      setSelected(report.id);
      setDetail(report);
      setVersions(await api.getReportVersions(report.id));
      reload();
    } catch (err) {
      setActionError(formatError(err));
    } finally {
      setWorkflowBusy("");
    }
  }

  return (
    <div className="grid gap-4 xl:grid-cols-[360px_minmax(0,1fr)]">
      <PageSection title="Reports" action={<RefreshButton onClick={reload} loading={loading} />}>
        {canWrite ? (
          <form onSubmit={generate} className="mb-4 rounded-lg border border-slate-200 bg-white p-4">
            <Field label="Report title">
              <input className="input" value={title} onChange={(event) => setTitle(event.target.value)} />
            </Field>
            <button className="mt-3 inline-flex w-full items-center justify-center gap-2 rounded-md bg-teal-700 px-4 py-2 text-sm font-semibold text-white hover:bg-teal-800 disabled:opacity-60" disabled={generating}>
              <BookOpen className="h-4 w-4" />
              {generating ? "Generating..." : "Generate"}
            </button>
          </form>
        ) : (
          <Alert tone="info" message="Viewer role has read-only report access." />
        )}
        <LoadState loading={loading} error={error || actionError} />
        {reports?.length ? reports.map((report) => (
          <button key={report.id} onClick={() => openReport(report.id)} className={`mb-2 w-full rounded-lg border p-3 text-left text-sm ${selected === report.id ? "border-teal-500 bg-teal-50" : "border-slate-200 bg-white hover:bg-slate-50"}`}>
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-semibold">{report.title}</span>
              <StatusBadge status={report.status} />
              <span className="rounded bg-slate-100 px-2 py-0.5 text-xs font-bold text-slate-700">v{report.version_number}</span>
            </div>
            <div className="mt-1 text-xs text-slate-500">report_id={report.id}; sources={report.source_document_ids?.length || 0}</div>
          </button>
        )) : <EmptyState label="No reports found" />}
      </PageSection>
      <PageSection title="Report Detail">
        {detail ? (
          <div className="space-y-4">
            <div className="rounded-lg border border-slate-200 bg-white p-4">
              <div className="flex flex-wrap items-center gap-2">
                <StatusBadge status={detail.status} />
                <span className="rounded bg-slate-100 px-2 py-0.5 text-xs font-bold text-slate-700">version {detail.version_number}</span>
                {detail.parent_report_id ? <span className="text-xs text-slate-500">parent_report_id={detail.parent_report_id}</span> : null}
              </div>
              <div className="mt-3 grid gap-2 text-xs text-slate-600 md:grid-cols-2">
                <div>submitted_by={detail.submitted_for_review_by_user_id || "-"}</div>
                <div>submitted_at={formatDate(detail.submitted_for_review_at)}</div>
                <div>approved_by={detail.approved_by_user_id || "-"}</div>
                <div>approved_at={formatDate(detail.approved_at)}</div>
              </div>
              {detail.approval_note ? <div className="mt-2 text-sm text-slate-700">Approval note: {detail.approval_note}</div> : null}
              {canWrite ? (
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  {detail.status === "draft" ? (
                    <button className="inline-flex items-center gap-2 rounded-md bg-teal-700 px-3 py-2 text-sm font-semibold text-white hover:bg-teal-800 disabled:opacity-60" disabled={Boolean(workflowBusy)} onClick={() => runWorkflow("submit", api.submitReportForReview)}>
                      Submit for Review
                    </button>
                  ) : null}
                  {isAdmin && detail.status === "in_review" ? (
                    <>
                      <input className="input max-w-sm" value={approvalNote} onChange={(event) => setApprovalNote(event.target.value)} placeholder="Approval note" />
                      <button className="inline-flex items-center gap-2 rounded-md bg-emerald-700 px-3 py-2 text-sm font-semibold text-white hover:bg-emerald-800 disabled:opacity-60" disabled={Boolean(workflowBusy)} onClick={() => runWorkflow("approve", (id) => api.approveReport(id, approvalNote))}>
                        Approve
                      </button>
                    </>
                  ) : null}
                  {detail.status === "approved" ? (
                    <button className="inline-flex items-center gap-2 rounded-md bg-slate-900 px-3 py-2 text-sm font-semibold text-white hover:bg-slate-700 disabled:opacity-60" disabled={Boolean(workflowBusy)} onClick={() => runWorkflow("revision", api.createReportRevision)}>
                      Create Revision
                    </button>
                  ) : null}
                </div>
              ) : null}
            </div>
            <div className="rounded-lg border border-slate-200 bg-white p-4">
              <div className="mb-2 text-sm font-bold text-slate-800">Version History</div>
              {versions.length ? versions.map((version) => (
                <button key={version.id} onClick={() => openReport(version.id)} className="mb-2 flex w-full flex-wrap items-center justify-between gap-2 rounded-md bg-slate-50 px-3 py-2 text-left text-sm hover:bg-slate-100">
                  <span>report_id={version.id}; v{version.version_number}</span>
                  <StatusBadge status={version.status} />
                </button>
              )) : <EmptyState label="No version history loaded" />}
            </div>
            <MarkdownReport text={detail.generated_content} />
          </div>
        ) : <EmptyState label="Select or generate a report" />}
      </PageSection>
    </div>
  );
}

function Analytics({ api }) {
  const loadTopics = useCallback(() => api.topics(10), [api]);
  const loadWordcloud = useCallback(() => api.wordcloud(75), [api]);
  const loadDataQuality = useCallback(() => api.dataQuality(), [api]);
  const loadWorkflowMetrics = useCallback(() => api.workflowMetrics(), [api]);
  const { data: topics, error: topicError, loading: topicsLoading, reload: reloadTopics } = useApiLoad(loadTopics);
  const { data: terms, error: cloudError, loading: cloudLoading, reload: reloadCloud } = useApiLoad(loadWordcloud);
  const { data: quality, error: qualityError, loading: qualityLoading, reload: reloadQuality } = useApiLoad(loadDataQuality);
  const {
    data: workflow,
    error: workflowError,
    loading: workflowLoading,
    reload: reloadWorkflow,
  } = useApiLoad(loadWorkflowMetrics);

  return (
    <div className="space-y-4">
      <div className="grid gap-4 xl:grid-cols-[420px_minmax(0,1fr)]">
        <PageSection title="Topics" action={<RefreshButton onClick={reloadTopics} loading={topicsLoading} />}>
          <LoadState loading={topicsLoading} error={topicError} />
          {topics?.length ? topics.map((topic, index) => (
            <div key={topic.topic} className="mb-2 flex items-center justify-between rounded-lg border border-slate-200 bg-white px-3 py-2">
              <div className="flex items-center gap-3">
                <span className="grid h-7 w-7 place-items-center rounded-md bg-slate-900 text-xs font-bold text-white">{index + 1}</span>
                <span className="text-sm font-semibold">{topic.topic}</span>
              </div>
              <span className="text-sm text-slate-500">{formatNumber(topic.score)}</span>
            </div>
          )) : <EmptyState label="No topics found" />}
        </PageSection>
        <PageSection title="Word Cloud" action={<RefreshButton onClick={reloadCloud} loading={cloudLoading} />}>
          <LoadState loading={cloudLoading} error={cloudError} />
          <div className="rounded-lg border border-slate-200 bg-white p-4">
            {terms?.length ? <TagCloud terms={terms} /> : <EmptyState label="No word cloud terms found" />}
          </div>
        </PageSection>
      </div>
      <DataQualityPanel quality={quality} error={qualityError} loading={qualityLoading} onRefresh={reloadQuality} />
      <WorkflowMetricsPanel workflow={workflow} error={workflowError} loading={workflowLoading} onRefresh={reloadWorkflow} />
    </div>
  );
}

function DataQualityPanel({ quality, error, loading, onRefresh }) {
  return (
    <PageSection title="Data Quality" action={<RefreshButton onClick={onRefresh} loading={loading} />}>
      <LoadState loading={loading} error={error} />
      {quality ? (
        <div className="space-y-3 rounded-lg border border-slate-200 bg-white p-4">
          <div className="grid gap-3 md:grid-cols-4">
            <div>
              <div className="text-xs font-bold uppercase text-slate-500">Extraction accuracy</div>
              <div className="mt-1 text-2xl font-bold text-slate-950">{formatNumber(quality.structured_extraction_accuracy)}%</div>
              <div className="text-xs text-slate-500">{quality.matched_fields}/{quality.total_expected_fields} fields matched</div>
            </div>
            {["pass", "failed", "needs_review"].map((status) => (
              <div key={status}>
                <div className="text-xs font-bold uppercase text-slate-500">{status.replace("_", " ")}</div>
                <div className="mt-1 text-2xl font-bold text-slate-950">{quality.validation_counts?.[status] ?? 0}</div>
              </div>
            ))}
          </div>
          <details className="rounded-md border border-slate-200 p-3" open>
            <summary className="cursor-pointer text-sm font-bold text-slate-800">Validation rules</summary>
            <div className="mt-3 space-y-2">
              {quality.rule_results?.map((rule) => (
                <div key={rule.rule} className="flex flex-col gap-1 rounded-md bg-slate-50 p-3 text-sm md:flex-row md:items-start md:justify-between">
                  <div>
                    <div className="font-semibold text-slate-800">{rule.rule}</div>
                    <div className="text-slate-600">{rule.message}</div>
                  </div>
                  <StatusBadge status={rule.status} />
                </div>
              ))}
            </div>
          </details>
          <details className="rounded-md border border-slate-200 p-3">
            <summary className="cursor-pointer text-sm font-bold text-slate-800">Field evidence</summary>
            <div className="mt-3 max-h-96 overflow-auto">
              <table className="w-full text-left text-xs">
                <thead className="sticky top-0 bg-white text-slate-500">
                  <tr>
                    <th className="p-2">Field</th>
                    <th className="p-2">Expected</th>
                    <th className="p-2">Extracted</th>
                    <th className="p-2">Status</th>
                    <th className="p-2">Source</th>
                  </tr>
                </thead>
                <tbody>
                  {quality.field_evidence?.map((field) => (
                    <tr key={field.field} className="border-t border-slate-100">
                      <td className="p-2 font-semibold text-slate-700">{field.field}</td>
                      <td className="p-2">{field.expected_value} {field.unit}</td>
                      <td className="p-2">{field.extracted_value ?? "-"}</td>
                      <td className="p-2"><StatusBadge status={field.status} /></td>
                      <td className="p-2">{field.source_filename} #{field.chunk_id ?? "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
          <p className="text-xs leading-5 text-slate-500">{quality.methodology}</p>
        </div>
      ) : !loading ? <EmptyState label="No data quality results loaded" /> : null}
    </PageSection>
  );
}

function WorkflowMetricsPanel({ workflow, error, loading, onRefresh }) {
  const automationCounts = workflow?.automation_counts || {};
  return (
    <PageSection title="Workflow Metrics" action={<RefreshButton onClick={onRefresh} loading={loading} />}>
      <LoadState loading={loading} error={error} />
      {workflow ? (
        <div className="space-y-3 rounded-lg border border-slate-200 bg-white p-4">
          <div className="grid gap-3 md:grid-cols-4">
            <div>
              <div className="text-xs font-bold uppercase text-slate-500">Time reduction</div>
              <div className="mt-1 text-2xl font-bold text-slate-950">{workflow.time_reduction_percentage == null ? "-" : `${formatNumber(workflow.time_reduction_percentage)}%`}</div>
              <div className="text-xs text-slate-500">Measured vs assumed baseline</div>
            </div>
            <div>
              <div className="text-xs font-bold uppercase text-slate-500">Automated wall clock</div>
              <div className="mt-1 text-2xl font-bold text-slate-950">{formatNumber(workflow.automated_wall_clock_seconds)}s</div>
              <div className="text-xs text-slate-500">Measured real interval</div>
            </div>
            <div>
              <div className="text-xs font-bold uppercase text-slate-500">Manual baseline</div>
              <div className="mt-1 text-2xl font-bold text-slate-950">{formatNumber(workflow.manual_baseline_time_seconds)}s</div>
              <div className="text-xs text-slate-500">Documented assumption</div>
            </div>
            <div>
              <div className="text-xs font-bold uppercase text-slate-500">Automation</div>
              <div className="mt-1 text-2xl font-bold text-slate-950">{formatNumber(workflow.automation_percentage)}%</div>
              <div className="text-xs text-slate-500">{automationCounts.steps_without_manual_intervention}/{automationCounts.total_steps} steps automated</div>
            </div>
          </div>
          <div className="rounded-md bg-slate-50 p-3 text-xs leading-5 text-slate-600">
            aggregate_compute_seconds={formatNumber(workflow.aggregate_compute_seconds)}; {workflow.aggregate_compute_note}
          </div>
          <details className="rounded-md border border-slate-200 p-3" open>
            <summary className="cursor-pointer text-sm font-bold text-slate-800">Automation step breakdown</summary>
            <div className="mt-3 space-y-2">
              {workflow.automation_step_breakdown?.map((step) => (
                <div key={step.step} className="flex flex-col gap-1 rounded-md bg-slate-50 p-3 text-sm md:flex-row md:items-start md:justify-between">
                  <div>
                    <div className="font-semibold text-slate-800">{step.step}</div>
                    <div className="text-slate-600">{step.description}</div>
                    <div className="text-xs text-slate-500">{step.current_system_basis}</div>
                  </div>
                  <StatusBadge status={step.requires_manual_intervention ? "manual" : "automated"} />
                </div>
              ))}
            </div>
          </details>
          <details className="rounded-md border border-slate-200 p-3">
            <summary className="cursor-pointer text-sm font-bold text-slate-800">Manual baseline assumptions</summary>
            <div className="mt-3 space-y-2 text-sm">
              {workflow.manual_baseline_activities?.map((activity) => (
                <div key={activity.activity} className="rounded-md bg-slate-50 p-3">
                  <div className="font-semibold text-slate-800">{activity.activity}</div>
                  <div className="text-slate-600">{activity.assumption}</div>
                  <div className="text-xs text-slate-500">{activity.seconds} seconds</div>
                </div>
              ))}
            </div>
          </details>
          <p className="text-xs leading-5 text-slate-500">{workflow.manual_baseline_disclosure}</p>
          <p className="text-xs leading-5 text-slate-500">{workflow.methodology}</p>
        </div>
      ) : !loading ? <EmptyState label="No workflow metrics loaded" /> : null}
    </PageSection>
  );
}

function NavButton({ item, active, onClick }) {
  const Icon = item.icon;
  return (
    <button onClick={onClick} className={`flex w-full items-center gap-3 rounded-md px-3 py-2.5 text-left text-sm font-semibold ${active ? "bg-white text-slate-950" : "text-slate-300 hover:bg-slate-800 hover:text-white"}`}>
      <Icon className="h-4 w-4" />
      {item.label}
    </button>
  );
}

function PageSection({ title, action, children }) {
  return (
    <section>
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 className="text-base font-bold text-slate-950">{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}

function Field({ label, children }) {
  return (
    <label className="block w-full">
      <span className="mb-1 block text-xs font-bold uppercase text-slate-500">{label}</span>
      {children}
    </label>
  );
}

function MetricCard({ label, value, Icon }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex items-center justify-between">
        <div className="text-sm font-semibold text-slate-500">{label}</div>
        <Icon className="h-4 w-4 text-teal-700" />
      </div>
      <div className="mt-3 text-3xl font-bold text-slate-950">{value ?? "-"}</div>
    </div>
  );
}

function ChartPanel({ title, data, kind }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4">
      <h3 className="mb-3 text-sm font-bold text-slate-700">{title}</h3>
      <div className="h-72">
        {data.length ? (
          <ResponsiveContainer width="100%" height="100%">
            {kind === "pie" ? (
              <PieChart>
                <Pie data={data} dataKey="value" nameKey="name" outerRadius={95} label>
                  {data.map((entry, index) => <Cell key={entry.name} fill={COLORS[index % COLORS.length]} />)}
                </Pie>
                <Tooltip />
              </PieChart>
            ) : (
              <BarChart data={data}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="name" />
                <YAxis allowDecimals={false} />
                <Tooltip />
                <Bar dataKey="value" fill="#0f766e" radius={[4, 4, 0, 0]} />
              </BarChart>
            )}
          </ResponsiveContainer>
        ) : <EmptyState label="No chart data" />}
      </div>
    </div>
  );
}

function StatusBadge({ status }) {
  const tone = {
    processed: "bg-emerald-100 text-emerald-800",
    completed: "bg-emerald-100 text-emerald-800",
    failed: "bg-red-100 text-red-800",
    queued: "bg-amber-100 text-amber-800",
    uploaded: "bg-cyan-100 text-cyan-800",
    processing: "bg-blue-100 text-blue-800",
    running: "bg-blue-100 text-blue-800",
    pass: "bg-emerald-100 text-emerald-800",
    matched: "bg-emerald-100 text-emerald-800",
    needs_review: "bg-amber-100 text-amber-800",
    automated: "bg-emerald-100 text-emerald-800",
    manual: "bg-amber-100 text-amber-800",
    draft: "bg-slate-100 text-slate-700",
    in_review: "bg-blue-100 text-blue-800",
    approved: "bg-emerald-100 text-emerald-800",
    superseded: "bg-amber-100 text-amber-800",
  }[status] || "bg-slate-100 text-slate-700";
  return <span className={`inline-flex w-fit items-center rounded px-2 py-0.5 text-xs font-bold ${tone}`}>{status}</span>;
}

function formatDate(value) {
  if (!value) return "-";
  return new Date(value).toLocaleString();
}

function RoleBadge({ role }) {
  return <span className="rounded bg-teal-100 px-2 py-0.5 text-xs font-bold text-teal-800">{role}</span>;
}

function RefreshButton({ onClick, loading }) {
  return (
    <button onClick={onClick} className="inline-flex items-center gap-2 rounded-md border border-slate-200 bg-white px-3 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50" disabled={loading}>
      <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
      Refresh
    </button>
  );
}

function Alert({ tone = "info", title, message }) {
  const classes = tone === "error" ? "border-red-200 bg-red-50 text-red-800" : "border-cyan-200 bg-cyan-50 text-cyan-800";
  return (
    <div className={`rounded-lg border px-3 py-2 text-sm ${classes}`}>
      {title ? <div className="font-bold">{title}</div> : null}
      <div>{message}</div>
    </div>
  );
}

function EmptyState({ label }) {
  return <div className="rounded-lg border border-dashed border-slate-300 bg-white p-6 text-center text-sm text-slate-500">{label}</div>;
}

function LoadState({ loading, error }) {
  if (loading) return <div className="mb-3 text-sm text-slate-500">Loading...</div>;
  if (error) return <div className="mb-3"><Alert tone="error" message={error} /></div>;
  return null;
}

function CitationList({ citations = [] }) {
  if (!citations.length) return <EmptyState label="No citations returned" />;
  return (
    <div className="mt-4 space-y-2">
      {citations.map((citation) => (
        <div key={`${citation.document_id}-${citation.chunk_id}`} className="rounded-md border border-slate-200 bg-slate-50 p-3 text-xs text-slate-600">
          <div className="font-bold text-slate-800">{citation.filename}</div>
          <div className="mt-1 flex flex-wrap gap-2">
            <span>document_id={citation.document_id}</span>
            <span>chunk_id={citation.chunk_id}</span>
            <span>similarity={formatNumber(citation.similarity)}</span>
            <span>{citation.source_reference}</span>
          </div>
        </div>
      ))}
    </div>
  );
}

function MarkdownReport({ text }) {
  const lines = text.split("\n");
  return (
    <article className="markdown-report rounded-lg border border-slate-200 bg-white p-5">
      {lines.map((line, index) => {
        if (line.startsWith("# ")) return <h1 key={index}>{line.slice(2)}</h1>;
        if (line.startsWith("## ")) return <h2 key={index}>{line.slice(3)}</h2>;
        if (line.startsWith("- ")) return <li key={index} className="ml-5 list-disc">{line.slice(2)}</li>;
        if (!line.trim()) return <div key={index} className="h-2" />;
        return <p key={index}>{line}</p>;
      })}
    </article>
  );
}

function TagCloud({ terms }) {
  const max = Math.max(...terms.map((term) => term.value), 1);
  return (
    <div className="flex flex-wrap gap-2">
      {terms.map((term, index) => {
        const size = 0.8 + (term.value / max) * 0.75;
        return (
          <span
            key={term.text}
            className="rounded-md border border-slate-200 bg-slate-50 px-3 py-1 font-semibold text-slate-700"
            style={{ fontSize: `${size}rem`, color: COLORS[index % COLORS.length] }}
          >
            {term.text}
          </span>
        );
      })}
    </div>
  );
}

function useApiLoad(loader) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const reload = useCallback(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    loader()
      .then((result) => !cancelled && setData(result))
      .catch((err) => !cancelled && setError(formatError(err)))
      .finally(() => !cancelled && setLoading(false));
    return () => { cancelled = true; };
  }, [loader]);

  useEffect(() => reload(), [reload]);

  return { data, loading, error, reload };
}

function objectToRows(value = {}) {
  return Object.entries(value).map(([name, count]) => ({ name, value: count }));
}

function formatError(err) {
  if (err instanceof ApiError) return `${err.status}: ${err.message}`;
  return err?.message || "Unexpected error";
}

function formatNumber(value) {
  if (value === null || value === undefined) return "-";
  return Number(value).toFixed(3);
}

export default App;
