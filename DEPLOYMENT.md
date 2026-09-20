# GitHub Pages + Python backend

GitHub Pages publishes only `frontend/`. PDF processing requires the Python API.
The checked-in `render.yaml` prepares a Render web service; select a suitable plan
in Render before deployment. No TypeSafe API key belongs in hosting settings.

1. Push the application to your GitHub repository's `main` branch.
2. In Render, create a Blueprint from that repository. Set `FRONTEND_ORIGINS`
   to your Pages origin, e.g. `https://YOUR-USER.github.io` (no repository path).
   For a custom domain, use its HTTPS origin instead.
3. Verify `https://YOUR-BACKEND.onrender.com/api/health` returns `{"status":"ok"}`.
4. In GitHub Settings → Secrets and variables → Actions → Variables, add
   `API_BASE_URL` with `https://YOUR-BACKEND.onrender.com`.
5. In Settings → Pages, choose GitHub Actions. Run the Deploy frontend to GitHub
   Pages workflow. Its environment link is the live frontend URL.
6. Open that URL, load a sample, check the preview and page navigation, enter a
   session API key, and evaluate. Refresh to confirm the key clears.

Local execution still uses the same-origin API without extra configuration.
Remote CORS permits only configured origins and exposes the image dimensions
needed for zoom. This is a demo, not an authenticated multi-user service:
uploaded documents remain in process memory until restart, with no expiry or
per-user access control. Use one worker and one service instance because the
document store is process-local. Restarts require users to upload again.

Do not publish `.env`, local environments, private PDFs, or credentials.
Only intended demo sample PDFs should be committed.
