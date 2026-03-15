import os

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import ValidationError

try:
	from app.main import app as app
except Exception as exc:
	app = FastAPI(title="Donation Platform Backend (Startup Error)")

	missing_env: list[str] = []
	if isinstance(exc, ValidationError):
		for err in exc.errors():
			loc = err.get("loc", ())
			if loc:
				missing_env.append(str(loc[-1]))

	@app.get("/{path:path}")
	async def startup_error(path: str):
		startup_debug = os.getenv("STARTUP_DEBUG", "false").lower() == "true"
		content = {
			"error": "Backend startup failed",
			"hint": "Check Vercel environment variables and deployment logs.",
			"missing_env": sorted(set(missing_env)),
			"exception_type": exc.__class__.__name__,
		}
		if startup_debug:
			content["exception"] = str(exc)
		return JSONResponse(status_code=500, content=content)
