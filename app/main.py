from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.pipeline import (
    InputValidationError,
    PipelineOutput,
    ScoringError,
    generate_career_dna_report,
    serialise_output,
    serialise_pipeline_error,
)
from app.schemas import RawInput

app = FastAPI(title="Career DNA API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://career-dna-production.up.railway.app",
        "*",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def index():
    return {"status": "running"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/generate-dna", response_model=None)
def generate_dna(input_data: RawInput):
    try:
        output: PipelineOutput = generate_career_dna_report(input_data)
        return JSONResponse(status_code=200, content=serialise_output(output))

    except InputValidationError as exc:
        return JSONResponse(
            status_code=422,
            content=serialise_pipeline_error(exc),
        )

    except ScoringError as exc:
        return JSONResponse(
            status_code=422,
            content=serialise_pipeline_error(exc),
        )

    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={
                "error": True,
                "stage": "unknown",
                "message": f"Unexpected error: {exc}",
                "recoverable": False,
            },
        )