# SPX Reconciliation Report landing page

React + Vite landing page for the Windows desktop app.

## Local development

```powershell
npm install
npm run dev
```

## Download link

Set `VITE_DOWNLOAD_URL` to the publicly accessible direct URL of
`SPXReconciliationReport.exe`. For local testing, copy `.env.example` to `.env`
and set the URL there. In Vercel, add the same variable under **Project Settings
→ Environment Variables**, then redeploy.

The current executable in the main project is about 240 MB, so it is not copied
into the Vercel deployment. Host it as a release asset (for example, GitHub
Releases) and point `VITE_DOWNLOAD_URL` at that asset.

## Deploy on Vercel

Import the repository in Vercel and set **Root Directory** to `landing-page`.
Vercel detects Vite; the build command is `npm run build` and the output
directory is `dist`.
