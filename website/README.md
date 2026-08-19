# CLASSORA frontend

React + Vite application for CLASSORA.

- Marketing landing: `/`
- Classroom portals: `/app`

Full setup, architecture, and API documentation live in the repository root:

- [README.md](../README.md)
- [documentation/PROJECT.md](../documentation/PROJECT.md)

```bash
npm install
npm run dev
```

The Vite dev server (port `5173`) proxies `/api` to the FastAPI backend on `http://127.0.0.1:8000` when `VITE_API_URL` is empty.
