# Banker Analytics

A professional-grade banking analytics application for analyzing borrower data, running stress scenarios, and generating rule-based explanations.

**Milestone 3**: Multi-User Authentication, Analysis History, and PDF Export Integration.

**Milestone 3.5**: Trend Engine v1 (Deterministic Trend Analysis)

---

## Features

### Quick Mode (Ephemeral)
- **30-minute session lifetime**: Upload CSV, analyze, and export without login
- **Session-based routes**: `/snapshot/{session_id}`, `/simulator/{session_id}`, `/explain/{session_id}`
- **No history**: Data is lost when session expires

### Persistent Mode (With Login)
- **User authentication**: Secure bcrypt password hashing with salting
- **Analysis history**: Save and reopen analyses forever
- **User isolation**: Hard boundaries—User A cannot see User B's data
- **PDF exports**: Link exports to analyses, downloadable anytime from history
- **Analysis routes**: `/snapshot/a/{analysis_id}`, `/simulator/a/{analysis_id}`, `/explain/a/{analysis_id}`

### Analysis Features
- **Borrower Snapshot**: KPI tiles, balance/rate trends, risk flags, and narrative summary
- **Scenario Simulator**: Apply interest rate and balance shocks, compare impacts
- **Explain Engine**: Rule-based 3-section narrative (What Matters, What Risks, Next Move)

### Trend Engine v1 (NEW - M3.5)
- **Deterministic Trend Analysis**: Compute balance and rate trends across 30/90/180-day windows
- **Versioned Outputs**: `TREND_ENGINE_VERSION = "v1.0"` + `inputs_hash` for reproducibility
- **Data Quality Metrics**: Volatility, confidence levels, outlier detection, missing date tracking
- **Multi-Window Display**: Show trends for balance and rate across all windows in Snapshot
- **History Badges**: 90-day trend direction (up/down/flat) displayed in Analysis History
- **Non-Disruptive**: Trend computation is non-fatal; uploads succeed even if trends fail
- **Bank-Grade Determinism**: Inputs hash prevents duplicate computations for identical data

---

## Installation & Setup

### Prerequisites
- Python 3.9+
- pip
- SQLite3 (included with Python)

### Step 1: Clone and Install Dependencies

```bash
cd malaga_local_app_v1
pip install -r requirements.txt
```

### Step 2: Generate SECRET_KEY

Banker Analytics uses secure session cookies. Generate a random SECRET_KEY:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Example output:
```
AbCdEfGhIjKlMnOpQrStUvWxYz1234567890ABCDE_F-G
```

### Step 3: Create .env Configuration

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

Edit `.env`:

```env
# Generate SECRET_KEY using: python -c "import secrets; print(secrets.token_urlsafe(32))"
SECRET_KEY=YOUR_GENERATED_SECRET_KEY_HERE

# Local dev = false, Production = true
SESSION_SECURE_COOKIE=false

# Session cookie lifetime in minutes (0 = no expiry, user logs out manually)
SESSION_COOKIE_LIFETIME_MINUTES=0

# Optional: SQLite database path (default: banker_analytics.db in repo root)
DATABASE_PATH=banker_analytics.db
```

### Step 4: Initialize Database

Run the app once—it will auto-create the database and schema:

```bash
python app.py
```

You should see:
```
INFO: Uvicorn running on http://127.0.0.1:8000
```

### Step 5: Register First User

**Option A: Via Web Form (Recommended)**
1. Navigate to http://localhost:8000/register
2. Enter username (e.g., "alice") and password (min 8 characters recommended)
3. Click "Register" → Auto-login

**Option B: Via Python Script (Manual)**
```python
from core.db import Database
from core.auth import create_user

db = Database()
user_id = db.create_user("alice", "AlicePass123!")
print(f"User created with ID: {user_id}")
```

### Step 6: Login and Try It Out

1. Go to http://localhost:8000
2. Click "Log In"
3. Enter credentials
4. Upload a CSV file
5. Explore Snapshot, Simulator, and Explain routes
6. Check "View History" to see saved analyses

---

## File Structure

```
malaga_local_app_v1/
├── app.py                    # Main FastAPI application
├── requirements.txt          # Python dependencies
├── .env.example              # Configuration template
├── banker_analytics.db       # SQLite database (auto-created)
│
├── core/
│   ├── auth.py              # Authentication (bcrypt, password hashing)
│   ├── db.py                # Database layer (users, analyses, exports)
│   ├── models.py            # Helper functions (filename sanitization, hashing)
│   ├── kpi.py               # KPI computation
│   └── ...                  # Other feature modules
│
├── data/
│   └── analyses/            # Persisted analysis parquet files
│
├── exports/                 # Generated PDF reports
│
├── templates/
│   ├── base.html            # Base template with nav
│   ├── hub.html             # Home page
│   ├── login.html           # Login form
│   ├── history.html         # Analysis history (M3)
│   ├── snapshot.html        # Snapshot page (M3 updated)
│   ├── simulator.html       # Simulator page (M3 updated)
│   ├── explain.html         # Explain page (M3 updated)
│   └── error.html           # Error page
│
└── tests/                   # Pytest test suites (M3)
    ├── test_auth.py         # Authentication tests
    ├── test_isolation.py    # User isolation tests
    └── test_history.py      # Analysis history tests
```

---

## Database Schema

### Users & Authentication
```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,  -- bcrypt hashed
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Analyses & Persistence
```sql
CREATE TABLE analyses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    filename TEXT NOT NULL,
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    row_count INTEGER NOT NULL,
    date_min DATE,
    date_max DATE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE analysis_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    analysis_id INTEGER NOT NULL,
    stored_path TEXT NOT NULL,  -- e.g., "data/analyses/123.parquet"
    file_hash TEXT NOT NULL,    -- SHA256 for integrity
    size_bytes INTEGER,
    format TEXT DEFAULT 'parquet',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (analysis_id) REFERENCES analyses(id) ON DELETE CASCADE
);
```

### Exports & Scenarios
```sql
CREATE TABLE exports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    analysis_id INTEGER,
    scenario_id INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    file_path TEXT NOT NULL,
    file_size INTEGER,
    report_kind TEXT,  -- 'snapshot_pdf', 'simulator_pdf', 'explain_pdf'
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (analysis_id) REFERENCES analyses(id) ON DELETE SET NULL
);

CREATE TABLE scenarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    analysis_id INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    rate_shock_bps INTEGER,
    balance_shock_pct REAL,
    results_json TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (analysis_id) REFERENCES analyses(id) ON DELETE CASCADE
);
```

### Trends & Determinism (M3.5)
```sql
CREATE TABLE analysis_trends (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    analysis_id INTEGER NOT NULL,
    computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    window_days INTEGER NOT NULL,  -- 30, 90, or 180
    series_name TEXT NOT NULL,     -- 'balance' or 'rate'
    metrics_json TEXT NOT NULL,    -- Compact JSON: slope, direction, volatility, confidence, etc.
    confidence TEXT,               -- 'high', 'medium', or 'low'
    inputs_hash TEXT UNIQUE,       -- Determinism key: hash(file_hash + VERSION + window + series)
    trend_engine_version TEXT,     -- 'v1.0' (for future versioning)
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (analysis_id) REFERENCES analyses(id) ON DELETE CASCADE
);
```

**Trend Metrics JSON Structure**:
```json
{
  "slope_per_day": 123.456,
  "direction": "up",
  "strength_score": 0.75,
  "volatility": 0.15,
  "confidence": "high",
  "sample_size": 30,
  "data_quality": {
    "missing_dates": 0,
    "duplicate_dates": 0,
    "outlier_count": 1
  },
  "breakpoint_dates": ["2024-01-15", "2024-02-01"],
  "trend_engine_version": "v1.0"
}

---

## API Routes

### Authentication (Public)
- `GET /login` - Login form
- `POST /login` - Authenticate user
- `POST /logout` - Clear session
- `GET /register` - Registration form
- `POST /register` - Create new user

### Hub & Upload
- `GET /` - Home page (auth optional)
- `POST /upload` - Upload CSV file
- `GET /history` - Analysis history (auth required)

### Quick Mode (Session-Based, 30-min TTL)
- `GET /snapshot/{session_id}` - View snapshot
- `GET /simulator/{session_id}` - View simulator form
- `POST /simulator/{session_id}` - Run scenario with shocks
- `GET /explain/{session_id}` - View explanation
- `POST /snapshot/{session_id}/export-pdf` - Export PDF
- `POST /simulator/{session_id}/export-pdf` - Export PDF
- `POST /explain/{session_id}/export-pdf` - Export PDF

### Persistent Mode (Analysis-Based, Auth Required)
- `GET /snapshot/a/{analysis_id}` - View snapshot
- `GET /simulator/a/{analysis_id}` - View simulator form
- `POST /simulator/a/{analysis_id}` - Run scenario with shocks
- `GET /explain/a/{analysis_id}` - View explanation
- `POST /snapshot/a/{analysis_id}/export-pdf` - Export PDF
- `POST /simulator/a/{analysis_id}/export-pdf` - Export PDF
- `POST /explain/a/{analysis_id}/export-pdf` - Export PDF

### File Downloads
- `GET /exports/{filename}` - Download PDF

---

## Security Features

### Authentication & Passwords
- **Bcrypt hashing**: 12 rounds with salt (OWASP standard)
- **72-byte limit**: Enforced per bcrypt spec
- **Signed session cookies**: Via Starlette SessionMiddleware
- **Manual logout**: No fixed TTL on cookies (user controls lifetime)

### User Isolation
- **Hard boundaries**: Every analysis lookup includes `user_id` WHERE clause
- **Ownership verification**: Explicit checks before returning data
- **404 on denied access**: Hides analysis existence from non-owners
- **Foreign key constraints**: Database-level protection

### File Safety
- **Path traversal prevention**: Filename sanitization (no `../`)
- **SHA256 integrity**: File hashes stored in database
- **Export cleanup**: Only deletes orphaned PDFs, preserves referenced files
- **Parquet format**: Compression and auditability

---

## Testing

### Run All Tests
```bash
pytest tests/ -v
python test_trends.py  # Standalone Trend Engine tests
```

### Test Coverage

#### test_auth.py
- Password hashing (bcrypt, salting, 72-byte limit)
- User registration (new, duplicate prevention, validation)
- Login/logout (session management, cookie handling)
- Auth guards (protected routes redirect to /login)

#### test_isolation.py
- User isolation (history, analysis access)
- Cross-user denial (404 on unauthorized access)
- Ownership verification (database-level)
- Export isolation and cleanup safety

#### test_history.py
- Analysis persistence and metadata
- Deterministic KPI computation (reproducible results)
- Analysis reopening (snapshot, simulator, explain)
- Export records and history

#### test_trends.py (NEW - M3.5)
- **Slope Computation**: Uptrend, downtrend, flat detection
- **Volatility Measurement**: Low and high volatility with edge cases
- **Outlier Detection**: Hampel method-based detection (modified Z-score)
- **Confidence Scoring**: High/medium/low confidence based on data quality
- **Deterministic Hashing**: Consistent hash generation for caching
- **Trend Serialization**: JSON serialization of metrics
- **Integration Tests**: Full trend computation with real DataFrames
- **Database CRUD**: Create, read, list trends with ownership verification
- **Determinism Caching**: Prevents duplicate trends via inputs_hash UNIQUE constraint
- **User Isolation**: Multi-user trends with hard boundaries
- **Graceful Degradation**: Small datasets handled with low confidence marking

---

## Troubleshooting

### Issue: "SECRET_KEY not found"
**Solution**: Create `.env` file with `SECRET_KEY` value (see Step 2-3 above)

### Issue: "Database is locked"
**Solution**: Close other connections to the database
```bash
# Or simply restart the app
pkill -f "python app.py"
python app.py
```

### Issue: Parquet files not found
**Solution**: Ensure `data/analyses/` directory exists and file was saved
```bash
ls -la data/analyses/
```

### Issue: Session cookie not persisting
**Solution**: Check browser cookies are enabled and `.env` has `SESSION_SECURE_COOKIE=false` (for local dev)

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | *(required)* | Session encryption key (generate with `secrets.token_urlsafe(32)`) |
| `SESSION_SECURE_COOKIE` | `false` | Set `true` for HTTPS production |
| `SESSION_COOKIE_LIFETIME_MINUTES` | `0` | Session TTL in minutes (0 = no expiry) |
| `DATABASE_PATH` | `banker_analytics.db` | SQLite database file location |

---

## Performance Notes

### Typical Response Times
- **Snapshot**: 200-400ms (KPI computation + chart rendering)
- **Simulator**: 300-600ms (shock application + comparison)
- **Explain**: 150-300ms (rule evaluation)
- **PDF Export**: 1-3s (rendering + file I/O)

### Database Tuning
- SQLite is suitable for up to 10K+ rows
- For larger datasets, consider PostgreSQL migration
- Indexes on `user_id`, `analysis_id` for fast lookups

---

## Future Enhancements

### PHASE 4A: Claude AI Integration
- Export Case Context Packet JSON
- Claude writes narratives (no numeric claims)
- Validation layer checks claims against computed KPIs

### PHASE 4B: Excel Automation
- Generate Excel memo with named ranges
- Claude outlines structure (prose only)
- App fills locked template

### PHASE 4C: Outlook Integration
- Email draft generation
- KPI summary + narrative in email body
- Optional Claude personalization

### PHASE 5: Data Integrations
- Government data sources (FRED, Census)
- Licensed financial data APIs
- Auto-fetch comparative metrics

---

## Support & Contributing

### Reporting Issues
1. Check `.env` is configured (SECRET_KEY, DATABASE_PATH)
2. Check `banker_analytics.db` exists and is readable
3. Review logs in console output
4. Run test suite: `pytest tests/ -v`

### Development Workflow
```bash
# Install dev dependencies
pip install -r requirements.txt pytest httpx

# Run tests
pytest tests/ -v

# Start dev server with reload
python app.py
# (or: uvicorn app:app --reload)
```

---

## License

Copyright © 2026. All rights reserved.

---

**Version**: Milestone 3.5 (M3.5) - Trend Engine v1.0
**Last Updated**: February 2026
**Status**: Production Ready ✅
