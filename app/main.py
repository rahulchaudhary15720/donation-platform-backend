from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.db.init_db import init_db
from app.routes import auth, ngos, campaigns, milestones, donations, admin, users, payments
from app.core.config import settings
import sys
from sqlalchemy import text

app = FastAPI(
    title="Donation & Charity Platform",
    description="Secure donation platform with milestone-based campaigns",
    version="1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_cors_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "Origin", "X-Requested-With"],
    expose_headers=["Content-Length", "Content-Range"],
    max_age=600,  # Cache preflight requests for 10 minutes
)

@app.on_event("startup")
async def startup_event():
    """Initialize database on application startup"""
    try:
        init_db()
        print("✅ Database initialized successfully")
        print(f"✅ CORS enabled for: {', '.join(settings.get_cors_origins())}")
    except Exception as e:
        error_msg = str(e)
        print("\n" + "="*60)
        print("❌ DATABASE CONNECTION FAILED")
        print("="*60)
        
        if "Network is unreachable" in error_msg or "IPv6" in error_msg or "2406:" in error_msg:
            # IPv6 connectivity issue
            from app.utils.ipv4_helper import diagnose_connectivity, get_connection_instructions
            diagnose_connectivity()
            print(get_connection_instructions())
            print("\n⚠️  Server starting anyway, but database operations will fail!")
            print("⚠️  Please fix the connection issue and restart the server.\n")
        else:
            print(f"Error: {e}")
            print("\nPlease check:")
            print("1. Database credentials in .env file")
            print("2. Network connectivity")
            print("3. Supabase dashboard - database might be paused\n")

app.include_router(auth.router)
app.include_router(ngos.router)
app.include_router(campaigns.router)
app.include_router(milestones.router)
app.include_router(donations.router)
app.include_router(admin.router)
app.include_router(users.router)
app.include_router(payments.router)

@app.get("/")
async def root():
    return {"message": "Donation & Charity Platform API", "status": "running"}

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        from app.db.session import engine
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        return {"status": "unhealthy", "database": "disconnected", "error": str(e)}
