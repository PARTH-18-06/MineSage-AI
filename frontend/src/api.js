const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

export class ApiError extends Error {
  constructor(status, message, body) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

export function createApiClient(getToken, onUnauthorized) {
  async function request(path, options = {}) {
    const headers = new Headers(options.headers || {});
    const token = getToken();
    if (token) {
      headers.set("Authorization", `Bearer ${token}`);
    }
    if (options.body && !(options.body instanceof FormData) && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }

    const response = await fetch(`${API_BASE_URL}${path}`, {
      ...options,
      headers,
    });

    const contentType = response.headers.get("content-type") || "";
    const body = contentType.includes("application/json") ? await response.json() : await response.text();

    if (!response.ok) {
      const message = typeof body === "object" && body?.detail ? body.detail : `Request failed with ${response.status}`;
      if (response.status === 401) {
        onUnauthorized?.();
      }
      throw new ApiError(response.status, message, body);
    }

    return body;
  }

  return {
    login: (email, password) =>
      request("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      }),
    me: () => request("/auth/me"),
    summary: () => request("/analytics/summary"),
    topics: (limit = 10) => request(`/analytics/topics?limit=${limit}`),
    wordcloud: (limit = 75) => request(`/analytics/wordcloud?limit=${limit}`),
    dataQuality: () => request("/analytics/data-quality"),
    workflowMetrics: () => request("/analytics/workflow-metrics"),
    listDocuments: () => request("/documents"),
    getDocument: (id) => request(`/documents/${id}`),
    getDocumentChunks: (id) => request(`/documents/${id}/chunks`),
    uploadDocument: (file) => {
      const form = new FormData();
      form.append("file", file);
      return request("/documents/upload", { method: "POST", body: form });
    },
    getJob: (id) => request(`/jobs/${id}`),
    semanticSearch: (q, limit = 5) => request(`/search/semantic?q=${encodeURIComponent(q)}&limit=${limit}`),
    askQuestion: (question, limit = 5) =>
      request("/qa/ask", {
        method: "POST",
        body: JSON.stringify({ question, limit }),
      }),
    qaHistory: (limit = 20) => request(`/qa/history?limit=${limit}`),
    listReports: () => request("/reports"),
    getReport: (id) => request(`/reports/${id}`),
    getReportVersions: (id) => request(`/reports/${id}/versions`),
    generateReport: (payload) =>
      request("/reports/generate", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    submitReportForReview: (id) => request(`/reports/${id}/submit-review`, { method: "POST" }),
    approveReport: (id, approvalNote = "") =>
      request(`/reports/${id}/approve`, {
        method: "POST",
        body: JSON.stringify({ approval_note: approvalNote }),
      }),
    createReportRevision: (id) => request(`/reports/${id}/create-revision`, { method: "POST" }),
  };
}
