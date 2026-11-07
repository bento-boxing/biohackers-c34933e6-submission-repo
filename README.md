# Biohackers — Full Stack App

A **Next.js + Flask** monorepo.

```
/                   ← Next.js frontend (TypeScript + Tailwind)
/backend            ← Flask API (Python)
```

## Getting Started

### Frontend (Next.js)
```bash
npm run dev
```
Runs at [http://localhost:3000](http://localhost:3000)

### Backend (Flask)
```bash
cd backend
python -m venv venv
venv\Scripts\activate      # Windows
# source venv/bin/activate # Mac/Linux
pip install -r requirements.txt
python app.py
```
Runs at [http://localhost:5000](http://localhost:5000)

## API Proxy

Next.js proxies all `/api/*` requests to Flask on port 5000.
So from the frontend, `fetch("/api/health")` hits `http://localhost:5000/api/health`.

## Project Structure

```
├── app/                  ← Next.js App Router pages & layouts
├── backend/
│   ├── app.py            ← Flask entry point
│   ├── requirements.txt  ← Python dependencies
│   └── .env.example      ← Environment variable template
├── next.config.ts        ← Next.js config (includes API proxy)
├── package.json
└── README.md
```
