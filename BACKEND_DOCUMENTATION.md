# Donation & Charity Platform - Backend Documentation

## 📋 Table of Contents
1. [Project Overview](#project-overview)
2. [Technology Stack](#technology-stack)
3. [Project Structure](#project-structure)
4. [Dependencies](#dependencies)
5. [Configuration & Environment Variables](#configuration--environment-variables)
6. [Database Architecture](#database-architecture)
7. [Core Components](#core-components)
8. [API Endpoints](#api-endpoints)
9. [Utility Services](#utility-services)
10. [Background Tasks](#background-tasks)
11. [Security Implementation](#security-implementation)
12. [Data Flow & Business Logic](#data-flow--business-logic)

---

## 🎯 Project Overview

This is a **FastAPI-based donation and charity platform** that connects donors with NGOs through transparent, milestone-based campaigns. The platform ensures accountability through proof verification and maintains donor privacy through encrypted email notifications.

### Key Features:
- **Multi-Role System**: Users, NGOs, and Admins with different access levels
- **Campaign Management**: NGOs can create fundraising campaigns
- **Milestone-Based Donations**: Campaigns are divided into verifiable milestones
- **Privacy Protection**: Anonymous donations with encrypted email storage
- **Proof Verification**: Admin verification of milestone completion
- **Email Notifications**: Automated notifications for donation confirmations and proof verification
- **Trust & Transparency**: System ensures funds are used as intended

---

## 💻 Technology Stack

- **Framework**: FastAPI (0.128.0)
- **Database**: PostgreSQL with SQLAlchemy (2.0.45)
- **Authentication**: JWT tokens with python-jose (3.5.0)
- **Password Hashing**: Passlib with bcrypt (5.0.0)
- **File Storage**: Cloudinary (1.44.1)
- **Email Encryption**: Cryptography/Fernet (46.0.3)
- **Email Service**: SMTP (Gmail)
- **Server**: Uvicorn (0.40.0)

---

## 📁 Project Structure

```
donation_charity_major_project/
├── app/
│   ├── main.py                     # Application entry point
│   ├── core/                       # Core configurations and utilities
│   │   ├── config.py              # Environment settings
│   │   ├── security.py            # Authentication & password handling
│   │   └── roles.py               # Role-based access control
│   ├── db/                        # Database configuration
│   │   ├── base.py                # SQLAlchemy base
│   │   ├── session.py             # Database session
│   │   └── init_db.py             # Database initialization
│   ├── models/                    # SQLAlchemy ORM models
│   │   ├── user.py                # User model (all roles)
│   │   ├── ngo.py                 # NGO model (legacy/unused)
│   │   ├── campaign.py            # Campaign model
│   │   ├── milestone.py           # Milestone model
│   │   ├── donation.py            # Donation model
│   │   ├── proof.py               # Proof upload model
│   │   └── email_notification.py  # Encrypted email storage
│   ├── routes/                    # API endpoint handlers
│   │   ├── auth.py                # Registration & login
│   │   ├── ngos.py                # NGO-specific routes
│   │   ├── campaigns.py           # Campaign CRUD
│   │   ├── milestones.py          # Milestone proof upload
│   │   ├── donations.py           # Donation processing
│   │   └── admin.py               # Admin operations
│   ├── tasks/                     # Background/scheduled tasks
│   │   └── cleanup.py             # Email notification cleanup
│   └── utils/                     # Utility functions
│       ├── cloudinary.py          # File upload to Cloudinary
│       ├── email_crypto.py        # Email encryption/decryption
│       └── email_service.py       # Email sending via SMTP
├── requirements.txt               # Python dependencies
└── .env                          # Environment variables (not in repo)
```

---

## 📦 Dependencies

### Core Dependencies:
```
fastapi==0.128.0                   # Web framework
uvicorn==0.40.0                    # ASGI server
SQLAlchemy==2.0.45                 # ORM
psycopg2-binary==2.9.11           # PostgreSQL driver
pydantic==2.12.5                   # Data validation
pydantic-settings==2.12.0          # Settings management
```

### Authentication & Security:
```
python-jose==3.5.0                 # JWT token handling
passlib==1.7.4                     # Password hashing
bcrypt==5.0.0                      # Bcrypt algorithm
cryptography==46.0.3               # Fernet encryption
```

### External Services:
```
cloudinary==1.44.1                 # Cloud file storage
python-multipart==0.0.21           # File upload handling
```

### Utilities:
```
python-dotenv==1.2.1               # Environment variable loading
alembic==1.18.1                    # Database migrations (optional)
```

---

## ⚙️ Configuration & Environment Variables

### File: `app/core/config.py`

The application uses Pydantic Settings for configuration management, loading from a `.env` file:

```python
class Settings(BaseSettings):
    DATABASE_URL: str              # PostgreSQL connection string
    JWT_SECRET: str                # Secret key for JWT signing
    JWT_ALGORITHM: str = "HS256"   # JWT algorithm
    CLOUDINARY_CLOUD_NAME: str     # Cloudinary cloud name
    CLOUDINARY_API_KEY: str        # Cloudinary API key
    CLOUDINARY_API_SECRET: str     # Cloudinary API secret
    SMTP_EMAIL: str                # Gmail sender email
    SMTP_PASSWORD: str             # Gmail app password
    FERNET_KEY: str                # Fernet encryption key
```

### Required `.env` File:
```env
DATABASE_URL=postgresql://user:password@localhost/dbname
JWT_SECRET=your-secret-key-here
JWT_ALGORITHM=HS256
CLOUDINARY_CLOUD_NAME=your-cloud-name
CLOUDINARY_API_KEY=your-api-key
CLOUDINARY_API_SECRET=your-api-secret
SMTP_EMAIL=your-email@gmail.com
SMTP_PASSWORD=your-app-password
FERNET_KEY=your-fernet-key
```

**Note**: Generate Fernet key using: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`

---

## 🗄️ Database Architecture

### Entity Relationship Overview:

```
User (multi-role)
  └─→ Campaign (as NGO)
       └─→ Milestone
            ├─→ Donation
            │    └─→ EmailNotification (if anonymous)
            └─→ Proof (uploaded by NGO)
```

### Database Models:

#### 1. **User Model** (`app/models/user.py`)
Central model for all user types (users, NGOs, admins).

```python
class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, nullable=False)
    password = Column(String, nullable=False)         # Bcrypt hashed
    role = Column(String, default="user")             # "user", "ngo", "admin"
    is_active = Column(Boolean, default=True)         # False for pending NGOs
```

**Fields Explanation**:
- `id`: Primary key
- `email`: Unique identifier for login
- `password`: Hashed using bcrypt (never stored in plain text)
- `role`: Determines user permissions (user/ngo/admin)
- `is_active`: NGOs start as False until admin approval; users/admins are True by default

---

#### 2. **Campaign Model** (`app/models/campaign.py`)
Represents fundraising campaigns created by NGOs.

```python
class Campaign(Base):
    __tablename__ = "campaigns"
    
    id = Column(Integer, primary_key=True)
    ngo_id = Column(Integer, ForeignKey("users.id"))  # References User table
    title = Column(String)
    target_amount = Column(Float)
    status = Column(String, default="active")         # "active", "paused", "completed"
```

**Fields Explanation**:
- `ngo_id`: Foreign key linking to User table (where role="ngo")
- `title`: Campaign name/description
- `target_amount`: Total fundraising goal
- `status`: Current state of campaign

---

#### 3. **Milestone Model** (`app/models/milestone.py`)
Campaigns are broken into milestones for transparent fund usage tracking.

```python
class Milestone(Base):
    __tablename__ = "milestones"
    
    id = Column(Integer, primary_key=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"))
    title = Column(String)
    target_amount = Column(Float)
    collected_amount = Column(Float, default=0)
    status = Column(String, default="pending")  # "pending", "awaiting_verification", "completed"
```

**Fields Explanation**:
- `campaign_id`: Links to parent campaign
- `target_amount`: Goal for this specific milestone
- `collected_amount`: Current donations for this milestone
- `status`: 
  - `pending`: Not yet funded or proof not uploaded
  - `awaiting_verification`: Proof uploaded, waiting for admin review
  - `completed`: Admin verified the proof

---

#### 4. **Donation Model** (`app/models/donation.py`)
Records individual donations to campaigns/milestones.

```python
class Donation(Base):
    __tablename__ = "donations"
    
    id = Column(Integer, primary_key=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"))
    milestone_id = Column(Integer, ForeignKey("milestones.id"))
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # Null if anonymous
    hashed_email = Column(String, nullable=True)                       # For anonymous donations
    transaction_id = Column(String, unique=True)
    amount = Column(Float)
    is_anonymous = Column(Boolean)
```

**Fields Explanation**:
- `user_id`: Null for anonymous donations
- `hashed_email`: Stores hashed email for anonymous donors (privacy protection)
- `transaction_id`: Unique identifier for the transaction
- `is_anonymous`: Flag to determine if donor info should be hidden

---

#### 5. **Proof Model** (`app/models/proof.py`)
Stores proof of milestone completion uploaded by NGOs.

```python
class Proof(Base):
    __tablename__ = "proofs"
    
    id = Column(Integer, primary_key=True)
    milestone_id = Column(Integer, ForeignKey("milestones.id"))
    file_url = Column(String)                         # Cloudinary URL
    verified = Column(Boolean, default=False)         # Admin verification status
```

**Fields Explanation**:
- `file_url`: Cloudinary CDN URL of uploaded proof document/image
- `verified`: Set to True by admin after reviewing the proof

---

#### 6. **EmailNotification Model** (`app/models/email_notification.py`)
Temporary storage for encrypted emails of anonymous donors.

```python
class EmailNotification(Base):
    __tablename__ = "email_notifications"
    
    id = Column(Integer, primary_key=True)
    donation_id = Column(Integer, ForeignKey("donations.id", ondelete="CASCADE"))
    encrypted_email = Column(Text, nullable=False)    # Fernet encrypted
    expires_at = Column(DateTime, nullable=False)     # Auto-cleanup date
    created_at = Column(DateTime(timezone=True), server_default=func.now())
```

**Fields Explanation**:
- `encrypted_email`: Fernet-encrypted email address
- `expires_at`: Date after which this record should be deleted (30 days from donation)
- Purpose: Allows notification of anonymous donors without permanently storing their emails

---

#### 7. **NGO Model** (`app/models/ngo.py`) - ⚠️ LEGACY/UNUSED
This model appears to be from an earlier design but is NOT currently used in the application.

```python
class NGO(Base):
    __tablename__ = "ngos"
    
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, nullable=False)
    password = Column(String, nullable=False)
    # Commented fields suggest this was replaced by the User model with role="ngo"
```

**Status**: This table is likely created but not actively used. The User model with `role="ngo"` is used instead.

---

## 🔐 Core Components

### 1. **Security Module** (`app/core/security.py`)

Handles authentication, password hashing, and token management.

#### Key Functions:

**Password Hashing**:
```python
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(password: str, hashed: str) -> bool:
    return pwd_context.verify(password, hashed)
```
- Uses bcrypt algorithm for secure password hashing
- Never stores plain text passwords

**JWT Token Creation**:
```python
def create_access_token(data: dict, expires_minutes: int = 60) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=expires_minutes)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
```
- Creates JWT tokens with 60-minute expiration
- Embeds user ID and role in token payload

**Authentication Dependency**:
```python
def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> User:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        user_id: int = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401)
    except JWTError:
        raise HTTPException(status_code=401)
    
    user = db.query(User).get(user_id)
    if not user:
        raise HTTPException(status_code=401)
    return user
```
- Validates JWT token
- Extracts user ID and fetches user from database
- Returns authenticated user object

**Database Session Management**:
```python
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```
- Provides database session as dependency
- Ensures proper cleanup after request

---

### 2. **Roles Module** (`app/core/roles.py`)

Implements role-based access control (RBAC).

#### Role Dependencies:

**User Role Check**:
```python
def user_required(user = Depends(get_current_user)):
    if user.role != "user":
        raise HTTPException(status_code=403, detail="User access required")
    return user
```

**NGO Role Check**:
```python
def ngo_required(user = Depends(get_current_user)):
    if user.role != "ngo":
        raise HTTPException(status_code=403, detail="NGO access required")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="NGO not approved")
    return user
```
- Additionally checks if NGO is approved (`is_active=True`)

**Admin Role Check**:
```python
def admin_required(user = Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user
```

**Usage**: These dependencies are added to route handlers to enforce permissions.

---

### 3. **Database Session** (`app/db/session.py`)

```python
engine = create_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False)
```
- Creates SQLAlchemy engine connected to PostgreSQL
- Configures session factory with `autoflush=False` for manual control

---

### 4. **Database Initialization** (`app/db/init_db.py`)

```python
def init_db():
    Base.metadata.create_all(bind=engine)
```
- Called on application startup
- Creates all tables if they don't exist
- Imports all models to register them with Base

---

## 🛣️ API Endpoints

### **Authentication Routes** (`app/routes/auth.py`)

Base path: `/auth`

#### 1. **POST /auth/register**
Registers a new user or NGO.

**Parameters**:
- `email` (str): User email address
- `password` (str): Plain text password (will be hashed)
- `role` (str): One of ["user", "ngo", "admin"]

**Logic**:
```python
ALLOWED_ROLES = {"user", "ngo", "admin"}

if role not in ALLOWED_ROLES:
    raise HTTPException(400, "Invalid role")
if role == "admin":
    raise HTTPException(403, "Admin cannot self-register")
if db.query(User).filter(User.email == email).first():
    raise HTTPException(400, "Email already registered")

is_active = role != "ngo"  # NGOs start inactive, awaiting approval
user = User(
    email=email,
    password=hash_password(password),
    role=role,
    is_active=is_active,
)
db.add(user)
db.commit()
```

**Response**:
```json
{
  "message": "user registered"  // or "ngo registered"
}
```

**Notes**:
- Admins cannot self-register (must be created manually in database)
- NGOs are created with `is_active=False` (require admin approval)
- Regular users are active immediately

---

#### 2. **POST /auth/login**
Authenticates user and returns JWT token.

**Parameters**:
- `email` (str)
- `password` (str)
- `role` (str): Must match the user's actual role

**Logic**:
```python
user = db.query(User).filter(User.email == email).first()

if not user or not verify_password(password, user.password):
    raise HTTPException(401, "Invalid credentials")

if user.role != role:
    raise HTTPException(403, "Role mismatch")

if not user.is_active:
    raise HTTPException(403, "Account not activated")

token = create_access_token({"sub": user.id, "role": user.role})
```

**Response**:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

**Notes**:
- Requires exact role match (prevents login with wrong role)
- Inactive NGOs cannot login until admin approval
- Token includes user ID (`sub`) and role in payload

---

### **NGO Routes** (`app/routes/ngos.py`)

Base path: `/ngos`

#### 1. **POST /ngos/register** (Duplicate of /auth/register for NGOs)
Alternative registration endpoint for NGOs.

**Parameters**:
- `email` (str)
- `password` (str)

**Logic**:
```python
if db.query(User).filter(User.email == email).first():
    raise HTTPException(400, "Email already exists")

hashed = hash_password(password)
user = User(email=email, password=hashed, role="ngo", is_active=False)
db.add(user)
db.commit()
```

**Response**:
```json
{
  "message": "NGO registered. Awaiting admin approval"
}
```

---

#### 2. **GET /ngos/me** 🔒 (NGO only)
Returns current authenticated NGO's profile.

**Authentication**: Requires JWT token and NGO role

**Response**: User object
```json
{
  "id": 5,
  "email": "ngo@example.com",
  "role": "ngo",
  "is_active": true
}
```

---

### **Campaign Routes** (`app/routes/campaigns.py`)

Base path: `/campaigns`

#### 1. **POST /campaigns/** 🔒 (NGO only)
Creates a new fundraising campaign.

**Authentication**: Requires NGO role and active status

**Parameters**:
- `title` (str): Campaign name
- `target_amount` (float): Fundraising goal

**Logic**:
```python
campaign = Campaign(
    title=title,
    target_amount=target_amount,
    ngo_id=ngo.id  # Automatically assigned from authenticated user
)
db.add(campaign)
db.commit()
```

**Response**: Created campaign object
```json
{
  "id": 10,
  "ngo_id": 5,
  "title": "Education for Underprivileged Children",
  "target_amount": 100000.0,
  "status": "active"
}
```

---

#### 2. **GET /campaigns/** 🌐 (Public)
Lists all active campaigns.

**No authentication required**

**Logic**:
```python
return db.query(Campaign).filter(Campaign.status == "active").all()
```

**Response**: Array of campaign objects
```json
[
  {
    "id": 10,
    "ngo_id": 5,
    "title": "Education for Underprivileged Children",
    "target_amount": 100000.0,
    "status": "active"
  },
  ...
]
```

---

### **Milestone Routes** (`app/routes/milestones.py`)

Base path: `/milestones`

#### 1. **POST /milestones/{milestone_id}/upload-proof** 🔒 (NGO only)
NGO uploads proof of milestone completion.

**Authentication**: Requires NGO role

**Path Parameters**:
- `milestone_id` (int): ID of the milestone

**Body**:
- `file` (UploadFile): Image/PDF proof document

**Logic**:
```python
milestone = db.query(Milestone).get(milestone_id)
if not milestone:
    raise HTTPException(404, "Milestone not found")

# Upload to Cloudinary
file_url = upload(file, folder="milestone_proofs")

# Create proof record
proof = Proof(
    milestone_id=milestone_id,
    file_url=file_url,
    verified=False
)
db.add(proof)
db.commit()

# Update milestone status
milestone.status = "awaiting_verification"
db.commit()
```

**Response**:
```json
{
  "message": "Proof uploaded successfully",
  "proof_url": "https://res.cloudinary.com/..."
}
```

**Notes**:
- File is uploaded to Cloudinary
- Milestone status changes to "awaiting_verification"
- Admin must verify the proof before milestone is completed

---

### **Donation Routes** (`app/routes/donations.py`)

Base path: `/donations`

#### 1. **POST /donations/** 🔒 (Authenticated users)
Process a donation to a campaign.

**Authentication**: Requires valid JWT token (any authenticated user)

**Parameters**:
- `campaign_id` (int): Target campaign
- `amount` (float): Donation amount
- `anonymous` (bool): Whether to hide donor identity
- `email` (str | None): Email for anonymous donations (optional)

**Logic**:
```python
# Create donation record
donation = Donation(
    campaign_id=campaign_id,
    amount=amount,
    is_anonymous=anonymous,
    user_id=None if anonymous else user.id,
    transaction_id=f"TXN-{datetime.utcnow().timestamp()}"
)
db.add(donation)
db.commit()

# If anonymous donation with email, encrypt and store
if anonymous and email:
    enc = encrypt_email(email)
    notify = EmailNotification(
        donation_id=donation.id,
        encrypted_email=enc,
        expires_at=datetime.utcnow() + timedelta(days=30)
    )
    db.add(notify)
    db.commit()
    
    # Send confirmation email
    send_email(email, "Donation Successful", "Your donation was received.")
```

**Response**:
```json
{
  "message": "Donation successful",
  "transaction_id": "TXN-1738915234.567890"
}
```

**Privacy Features**:
- Anonymous donations: `user_id` is NULL, only encrypted email stored
- Email encrypted with Fernet (symmetric encryption)
- Email record expires after 30 days (auto-cleanup)
- Regular donations: `user_id` populated, no email encryption needed

---

### **Admin Routes** (`app/routes/admin.py`)

Base path: `/admin`

#### 1. **GET /admin/ngos/pending** 🔒 (Admin only)
Lists NGOs awaiting approval.

**Authentication**: Admin role required

**Logic**:
```python
return db.query(User).filter(User.role == "ngo", User.is_active == False).all()
```

**Response**: Array of pending NGO users
```json
[
  {
    "id": 8,
    "email": "newgo@example.com",
    "role": "ngo",
    "is_active": false
  },
  ...
]
```

---

#### 2. **POST /admin/ngos/{ngo_id}/approve** 🔒 (Admin only)
Approves an NGO, allowing them to login and create campaigns.

**Authentication**: Admin role required

**Path Parameters**:
- `ngo_id` (int): User ID of the NGO

**Logic**:
```python
user = db.query(User).get(ngo_id)
if not user or user.role != "ngo":
    raise HTTPException(404, "NGO not found")

user.is_active = True
db.commit()
```

**Response**:
```json
{
  "message": "NGO approved and activated"
}
```

---

#### 3. **POST /admin/proofs/{proof_id}/verify** 🔒 (Admin only)
Verifies proof of milestone completion and notifies anonymous donors.

**Authentication**: Admin role required

**Path Parameters**:
- `proof_id` (int): ID of the proof to verify

**Logic**:
```python
# Mark proof as verified
proof = db.query(Proof).get(proof_id)
proof.verified = True
db.commit()

# Find associated email notification
notify = db.query(EmailNotification)\
    .filter(EmailNotification.donation_id == proof.milestone_id)\
    .first()

if notify:
    # Decrypt email and send notification
    email = decrypt_email(notify.encrypted_email)
    send_email(email, "Donation Used", "NGO proof verified.")
    
    # Delete notification (no longer needed)
    db.delete(notify)
    db.commit()
```

**Response**:
```json
{
  "message": "Proof verified"
}
```

**Note**: There's a potential bug here - it's checking `donation_id == proof.milestone_id`, but should likely check for donations related to the milestone, not using milestone_id directly as donation_id.

---

## 🛠️ Utility Services

### 1. **Cloudinary Upload** (`app/utils/cloudinary.py`)

Handles file uploads to Cloudinary CDN.

```python
import cloudinary, cloudinary.uploader
from app.core.config import settings

# Initialize Cloudinary with credentials
cloudinary.config(
    cloud_name=settings.CLOUDINARY_CLOUD_NAME,
    api_key=settings.CLOUDINARY_API_KEY,
    api_secret=settings.CLOUDINARY_API_SECRET
)

def upload(file, folder="proofs"):
    result = cloudinary.uploader.upload(file.file, folder=folder)
    return result["secure_url"]
```

**Usage**: 
- Called from milestone proof upload endpoint
- Returns HTTPS URL to uploaded file
- Files organized in folders (e.g., "milestone_proofs")

---

### 2. **Email Encryption** (`app/utils/email_crypto.py`)

Encrypts/decrypts emails using Fernet symmetric encryption.

```python
from cryptography.fernet import Fernet
from app.core.config import settings

cipher = Fernet(settings.FERNET_KEY.encode())

def encrypt_email(email: str) -> str:
    return cipher.encrypt(email.encode()).decode()

def decrypt_email(encrypted_email: str) -> str:
    return cipher.decrypt(encrypted_email.encode()).decode()
```

**Purpose**: Protects anonymous donor email addresses in database.

**Security Notes**:
- Uses Fernet (symmetric encryption from cryptography library)
- Key must be kept secret in environment variables
- Same key used for encryption and decryption

---

### 3. **Email Service** (`app/utils/email_service.py`)

Sends emails via Gmail SMTP.

```python
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587  # TLS port

def send_email(to_email: str, subject: str, body: str):
    msg = MIMEMultipart()
    msg["From"] = settings.SMTP_EMAIL
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))
    
    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()  # Enable TLS encryption
        server.login(settings.SMTP_EMAIL, settings.SMTP_PASSWORD)
        server.send_message(msg)
```

**Current Usage**:
1. Donation confirmation to anonymous donors
2. Proof verification notification to anonymous donors

**Configuration Required**:
- Gmail account with "App Password" (not regular password)
- Must enable 2-factor authentication in Gmail
- Generate App Password in Google Account settings

---

## ⏰ Background Tasks

### **Email Cleanup Task** (`app/tasks/cleanup.py`)

Removes expired email notifications from database.

```python
from datetime import datetime
from app.db.session import SessionLocal
from app.models.email_notification import EmailNotification

def cleanup_expired_emails():
    db = SessionLocal()
    db.query(EmailNotification)\
      .filter(EmailNotification.expires_at < datetime.utcnow())\
      .delete()
    db.commit()
    db.close()
```

**Purpose**: Privacy protection - ensures anonymous donor emails aren't stored indefinitely.

**Current Status**: ⚠️ Function defined but NOT scheduled to run automatically.

**To Implement**: Needs a task scheduler like:
- **Celery** (with Redis/RabbitMQ)
- **APScheduler** (simpler, built into Python)
- **Cron job** calling a management script

**Recommended Setup** (APScheduler example):
```python
from apscheduler.schedulers.background import BackgroundScheduler

scheduler = BackgroundScheduler()
scheduler.add_job(cleanup_expired_emails, 'interval', hours=24)
scheduler.start()
```

---

## 🔐 Security Implementation

### Authentication Flow:

1. **Registration**:
   - Password hashed with bcrypt (12 rounds by default)
   - Stored in database
   - NGOs marked as inactive

2. **Login**:
   - Verify email and password
   - Check role match and active status
   - Generate JWT token with 60-minute expiration
   - Token contains: `{"sub": user_id, "role": role, "exp": timestamp}`

3. **Protected Endpoints**:
   - Extract token from `Authorization: Bearer <token>` header
   - Decode and verify JWT signature
   - Fetch user from database using token's `sub` claim
   - Return user object to route handler

4. **Role Authorization**:
   - Additional dependency checks user's role attribute
   - Rejects request if role doesn't match requirement

### Security Best Practices Implemented:
✅ Password hashing with bcrypt  
✅ JWT token expiration  
✅ Role-based access control  
✅ Email encryption for privacy  
✅ HTTPS URLs from Cloudinary  
✅ Unique transaction IDs  

### Potential Security Improvements:
⚠️ Add refresh tokens (current tokens last only 60 minutes)  
⚠️ Rate limiting on login/registration endpoints  
⚠️ Email verification (currently emails not verified)  
⚠️ Input validation (Pydantic schemas recommended)  
⚠️ SQL injection protection (SQLAlchemy ORM provides this, but validate inputs)  
⚠️ CORS configuration (not visible in code)  
⚠️ File upload validation (check file types, sizes)  

---

## 📊 Data Flow & Business Logic

### 1. **NGO Approval Workflow**:
```
NGO registers → Admin receives list of pending NGOs → 
Admin approves → NGO.is_active = True → NGO can login
```

### 2. **Campaign Creation Workflow**:
```
Approved NGO creates campaign → Campaign.status = "active" → 
Visible to all users
```

### 3. **Donation Workflow**:

**Standard Donation**:
```
User donates → Donation created with user_id → 
(Milestone.collected_amount incremented) → Transaction ID returned
```

**Anonymous Donation**:
```
User donates anonymously → Donation created (user_id=NULL) → 
Email encrypted and stored → Expires in 30 days → 
Confirmation email sent
```

### 4. **Milestone Verification Workflow**:
```
Milestone funded → NGO uploads proof → Proof.verified = False → 
Milestone.status = "awaiting_verification" → Admin reviews → 
Admin verifies → Proof.verified = True → 
Anonymous donors notified → EmailNotification deleted
```

### 5. **Data Retention**:
- **User accounts**: Permanent (no deletion mechanism)
- **Campaigns**: Permanent (status changed to "completed" or "paused")
- **Donations**: Permanent (audit trail)
- **Encrypted emails**: 30 days (auto-cleanup needed)
- **Proofs**: Permanent (on Cloudinary and database)

---

## 🚀 Application Entry Point

### **Main Application** (`app/main.py`)

```python
from fastapi import FastAPI
from app.db.init_db import init_db
from app.routes import auth, ngos, campaigns, milestones, donations, admin

app = FastAPI()

# Initialize database (create tables)
init_db()

# Register route handlers
app.include_router(auth.router)
app.include_router(ngos.router)
app.include_router(campaigns.router)
app.include_router(milestones.router)
app.include_router(donations.router)
app.include_router(admin.router)
```

**Startup Process**:
1. FastAPI application instantiated
2. Database tables created (if not exist)
3. All route modules registered

**Running the Application**:
```bash
uvicorn app.main:app --reload
```

**Available at**: `http://localhost:8000`

**API Documentation**: 
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

---

## 📝 Missing/Incomplete Features

### Identified Issues:

1. **NGO Model Unused**: `app/models/ngo.py` exists but not used (User model handles NGOs)

2. **No Milestone Creation Endpoint**: Campaigns exist, but no API to create milestones for them

3. **Donation-Milestone Link**: Donations reference `milestone_id`, but no endpoint to donate to specific milestones

4. **Notification Bug**: In `/admin/proofs/{proof_id}/verify`, the query `EmailNotification.donation_id == proof.milestone_id` seems incorrect

5. **Campaign Collected Amount**: No tracking of total collected amount in Campaign model

6. **Trust Score**: NGO model has commented-out `trust_score` field - feature not implemented

7. **Cleanup Task Not Scheduled**: `cleanup_expired_emails()` defined but never called

8. **No Payment Gateway**: Donation endpoint creates records but no actual payment processing

9. **No Email Templates**: Email bodies are hardcoded strings

10. **No Pagination**: List endpoints return all records (will scale poorly)

11. **No Campaign-Milestone Relationship**: Milestones exist but no endpoint to view milestones for a campaign

12. **No Donation History**: Users can't view their donation history

---

## 🎯 Recommended Next Steps

### High Priority:
1. **Implement Milestone Creation Endpoint** (NGO creates milestones for their campaigns)
2. **Fix EmailNotification Query Bug** in admin proof verification
3. **Add Campaign Milestone List Endpoint** (`GET /campaigns/{id}/milestones`)
4. **Schedule Cleanup Task** using APScheduler or Celery
5. **Add Donation History Endpoints** for users and NGOs

### Medium Priority:
6. **Payment Gateway Integration** (Stripe, Razorpay, PayPal)
7. **Input Validation** using Pydantic models
8. **Email Templates** using Jinja2
9. **Pagination** for list endpoints
10. **Campaign Total Tracking** (sum of milestone amounts)

### Low Priority:
11. **Trust Score System** for NGOs
12. **Email Verification** on registration
13. **Password Reset Flow**
14. **Profile Management** (update email, password)
15. **Campaign Pause/Resume** functionality

---

## 🧪 Testing Recommendations

### Unit Tests:
- Password hashing and verification
- Email encryption/decryption
- JWT token creation and validation
- Role permission checks

### Integration Tests:
- Registration and login flows
- Campaign creation and listing
- Donation processing
- Admin approval workflows
- Proof upload and verification

### Test Tools:
- **pytest**: Test framework
- **httpx**: Async HTTP client for FastAPI testing
- **pytest-asyncio**: Async test support
- **faker**: Generate test data

---

## 📚 API Usage Examples

### 1. Register as NGO:
```bash
curl -X POST "http://localhost:8000/auth/register" \
  -H "Content-Type: application/json" \
  -d '{"email": "ngo@example.com", "password": "secure123", "role": "ngo"}'
```

### 2. Admin Login:
```bash
curl -X POST "http://localhost:8000/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@example.com", "password": "admin123", "role": "admin"}'
```

### 3. Create Campaign (NGO):
```bash
curl -X POST "http://localhost:8000/campaigns/" \
  -H "Authorization: Bearer <ngo_token>" \
  -H "Content-Type: application/json" \
  -d '{"title": "Clean Water Project", "target_amount": 50000}'
```

### 4. Make Anonymous Donation:
```bash
curl -X POST "http://localhost:8000/donations/" \
  -H "Authorization: Bearer <user_token>" \
  -H "Content-Type: application/json" \
  -d '{"campaign_id": 1, "amount": 1000, "anonymous": true, "email": "donor@example.com"}'
```

---

## 🗺️ System Architecture Diagram

```
┌─────────────┐
│   Client    │
│ (Web/Mobile)│
└──────┬──────┘
       │ HTTP/HTTPS
       ▼
┌─────────────────────────────────────────┐
│          FastAPI Application            │
│                                         │
│  ┌──────────────────────────────────┐  │
│  │     Routes (API Endpoints)       │  │
│  │  - Auth  - NGO   - Admin        │  │
│  │  - Campaigns - Donations        │  │
│  └──────────────┬──────────────────┘  │
│                 │                      │
│  ┌──────────────▼──────────────────┐  │
│  │    Core (Security & Roles)      │  │
│  │  - JWT Auth  - Password Hash    │  │
│  │  - Role Checks                  │  │
│  └──────────────┬──────────────────┘  │
│                 │                      │
│  ┌──────────────▼──────────────────┐  │
│  │         Models (ORM)            │  │
│  │  User, Campaign, Donation, etc. │  │
│  └──────────────┬──────────────────┘  │
└─────────────────┼───────────────────────┘
                  │
     ┌────────────┼────────────┐
     ▼            ▼            ▼
┌──────────┐ ┌──────────┐ ┌──────────┐
│PostgreSQL│ │Cloudinary│ │Gmail SMTP│
│ Database │ │File Store│ │  Email   │
└──────────┘ └──────────┘ └──────────┘
```

---

## 🔑 Key Takeaways

This is a **milestone-based donation platform** with these core features:

1. **Multi-role system**: Users donate, NGOs create campaigns, Admins approve and verify
2. **Privacy-first**: Anonymous donations with encrypted email storage
3. **Transparency**: Milestones require proof verification before completion
4. **Scalable architecture**: FastAPI + PostgreSQL + Cloudinary
5. **Security**: JWT auth, bcrypt hashing, role-based access control

**Current State**: Core functionality implemented, but needs:
- Payment gateway integration
- Milestone management endpoints
- Scheduled background tasks
- Bug fixes in notification system

---

## 📞 Support & Contact

For questions about this codebase, refer to:
- FastAPI Documentation: https://fastapi.tiangolo.com/
- SQLAlchemy Documentation: https://docs.sqlalchemy.org/
- Cloudinary Documentation: https://cloudinary.com/documentation

---

*Documentation generated on: February 9, 2026*
*Backend Version: 1.0.0*
*Python Version: 3.10+*
