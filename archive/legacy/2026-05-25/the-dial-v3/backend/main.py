"""The Dial - FastAPI backend."""

from __future__ import annotations

import os
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Dict

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import uvicorn

from data_service import DataService


BASE_DIR = os.path.dirname(__file__)
DB_PATH = os.path.join(BASE_DIR, "macro_data.db")
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)


data_service = DataService(DB_PATH, DATA_DIR)


def _table_count(table: str) -> int:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(f"SELECT COUNT(*) FROM {table}")
    count = int(cursor.fetchone()[0])
    conn.close()
    return count


@asynccontextmanager
async def lifespan(app: FastAPI):
    del app
    print("Starting The Dial API server...")

    data_service.init_database()
    reconciled = data_service.reconcile_interrupted_pipeline_runs()
    if reconciled["marked_failed"]:
        print(f"Marked {reconciled['marked_failed']} interrupted pipeline run(s) as failed")

    if _table_count("factor_latest") == 0:
        data_service.bootstrap_defaults()

    factor_layer = data_service.ensure_factor_layer_ready()
    if factor_layer["rebuilt"]:
        factor_report = factor_layer["factors"]
        print(
            "Rebuilt factor layer from local raw data: "
            f"computed={factor_report.get('computed', 0)}, "
            f"missing={factor_report.get('missing', 0)}"
        )

    # Optional local seed for SP500, keeps charts available offline.
    if _table_count("sp500_data") == 0:
        csv_seed = os.path.abspath(os.path.join(BASE_DIR, "..", "..", "sp500_history.csv"))
        if os.path.exists(csv_seed):
            data_service.load_sp500_from_csv(csv_seed)

    print("Server ready")
    yield
    print("Server shutting down")


app = FastAPI(
    title="The Dial API",
    description="Macroeconomic data API for The Dial dashboard",
    version="3.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@app.get("/api/health")
@app.get("/api/v1/health")
async def health_check() -> Dict[str, Any]:
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "version": "3.1.0",
    }


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


@app.get("/api/v1/dashboard")
@app.get("/api/dashboard")
async def get_dashboard() -> Dict[str, Any]:
    try:
        return data_service.get_dashboard_data()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/v1/dashboard/drivers")
async def get_dashboard_drivers(period: str = Query("30d", pattern="^(7d|30d|90d)$")) -> Dict[str, Any]:
    try:
        return data_service.get_dashboard_drivers(period)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Scores
# ---------------------------------------------------------------------------


@app.get("/api/overall-score")
async def get_overall_score() -> Dict[str, Any]:
    try:
        return data_service.get_current_overall_score()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/history/overall")
async def get_overall_history(days: int = Query(365, ge=7, le=5000)) -> Dict[str, Any]:
    try:
        return data_service.get_overall_history(days)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/v1/modules")
@app.get("/api/modules")
async def get_modules() -> Dict[str, Any] | list[Dict[str, Any]]:
    try:
        return data_service.get_modules_v1()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/v1/modules/{module_id}")
async def get_module_v1(module_id: str) -> Dict[str, Any]:
    module = data_service.get_module_detail(module_id)
    if not module:
        raise HTTPException(status_code=404, detail=f"Module {module_id} not found")
    return module


@app.get("/api/modules/{module_id}")
async def get_module(module_id: str) -> Dict[str, Any]:
    module = data_service.get_module_score(module_id)
    if not module:
        raise HTTPException(status_code=404, detail=f"Module {module_id} not found")
    return module


@app.get("/api/v1/modules/{module_id}/history")
@app.get("/api/modules/{module_id}/history")
async def get_module_history(module_id: str, days: int = Query(365, ge=7, le=5000)) -> Dict[str, Any]:
    if not data_service.get_module_score(module_id):
        raise HTTPException(status_code=404, detail=f"Module {module_id} not found")
    return data_service.get_module_history(module_id, days)


@app.get("/api/v1/modules/{module_id}/factors/{factor_id}/history")
async def get_factor_history(module_id: str, factor_id: str, days: int = Query(365, ge=7, le=5000)) -> Dict[str, Any]:
    return data_service.get_factor_history(module_id, factor_id, days)


@app.get("/api/v1/modules/{module_id}/factors/{factor_id}/distribution")
async def get_factor_distribution(module_id: str, factor_id: str) -> Dict[str, Any]:
    return data_service.get_factor_distribution(module_id, factor_id)


@app.get("/api/modules/{module_id}/indicators")
async def get_module_indicators(module_id: str) -> Dict[str, Any] | list[Dict[str, Any]]:
    if not data_service.get_module_score(module_id):
        raise HTTPException(status_code=404, detail=f"Module {module_id} not found")
    return data_service.get_module_indicators(module_id)


@app.get("/api/indicators")
async def get_available_indicators() -> list[Dict[str, Any]]:
    return data_service.get_indicator_list()


# ---------------------------------------------------------------------------
# SP500 helper endpoints
# ---------------------------------------------------------------------------


@app.get("/api/v1/sp500")
@app.get("/api/sp500")
async def get_sp500(days: int = Query(365, ge=7, le=5000)) -> Dict[str, Any]:
    return data_service.get_sp500_data(days)


@app.get("/api/v1/sp500/current")
@app.get("/api/sp500/current")
async def get_sp500_current() -> Dict[str, Any]:
    return data_service.get_current_sp500()


# ---------------------------------------------------------------------------
# Updates / pipeline
# ---------------------------------------------------------------------------


@app.post("/api/v1/update")
@app.post("/api/update")
async def trigger_update(background_tasks: BackgroundTasks) -> Dict[str, Any]:
    background_tasks.add_task(data_service.update_all_data)
    return {"message": "Data update started", "timestamp": datetime.now().isoformat(timespec="seconds")}


@app.get("/api/v1/pipeline/runs")
async def get_pipeline_runs(limit: int = Query(20, ge=1, le=200)) -> Dict[str, Any]:
    return {"runs": data_service.get_pipeline_runs(limit=limit)}


# ---------------------------------------------------------------------------
# Static frontend
# ---------------------------------------------------------------------------


frontend_path = os.path.join(BASE_DIR, "..", "frontend")
if os.path.exists(frontend_path):
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
