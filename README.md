# 🏢 B2B HRMS Backend — WorkMatrix

> **B2B Human Resource Management System** — A full-featured, multi-tenant backend API built with **FastAPI**, **MongoDB (Beanie ODM)**, and **Redis**, designed to manage everything from employee onboarding to CRM, payroll, attendance, and beyond.

---

## 📋 Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
  - [Environment Variables](#environment-variables)
  - [Running the Server](#running-the-server)
- [API Modules](#api-modules)
- [Authentication & Security](#authentication--security)
- [API Documentation](#api-documentation)
- [Contributing](#contributing)

---

## 🌟 Overview

**WorkMatrix** is a cloud-ready, multi-tenant B2B SaaS backend that provides a comprehensive suite of HR and business management tools. It supports multiple tenants (organizations), each with their own isolated data, roles, employees, CRM pipeline, and payroll configuration.

The system is built around:
- **Multi-tenancy** — Each organization (tenant) operates in complete isolation.
- **Role-Based Access Control (RBAC)** — Fine-grained permissions across all modules.
- **Secure Authentication** — JWT-based auth with MFA (TOTP), Redis-backed OTP, and login security tracking.

---

## ✨ Features

| Module | Description |
|---|---|
| 🔐 **Authentication** | JWT login, MFA (TOTP), email verification, forgot password, login security |
| 👥 **Employee Management** | Full employee lifecycle — add, update, deactivate, documents |
| 🧾 **Payroll** | Payslip generation, salary structure, deductions, payroll runs |
| 📅 **Attendance** | Clock-in/out, attendance reports, shift management |
| 🏖️ **Leave Management** | Leave types, policies, employee leave requests, approvals |
| 📊 **CRM** | Leads, contacts, deals, pipelines, deal workspaces |
| 📋 **Project Management** | Projects, tasks, assignments, workload tracking |
| 📣 **Announcements** | Company-wide announcements |
| 🎫 **Ticketing** | Internal support ticket system |
| 💳 **Billing & Subscriptions** | Plan management, trial, subscription billing |
| 🔍 **Audit Logs** | Full activity audit trail across all modules |
| 📋 **Onboarding** | New employee onboarding workflows |
| 🎯 **Roles & Permissions** | Custom role creation and permission assignment |
| 🏕️ **Holiday Management** | Company holiday calendar |
| 📝 **Notes** | Unified notes across CRM, deals, and projects |
| 📊 **Dashboards** | Super Admin, HR, and Admin dashboard analytics |
| 👤 **Employee Self-Service** | Employees can view/update their own profile, leaves, payslips |
| 💼 **Job Requisition & Posting** | Internal job requisitions and postings |
| 🤝 **Tenant Management** | Super admin management of all tenants |

---

## 🛠️ Tech Stack

| Technology | Purpose |
|---|---|
| **FastAPI** | High-performance async web framework |
| **MongoDB Atlas** | Cloud NoSQL database |
| **Beanie ODM** | Async MongoDB ODM (built on Motor + Pydantic) |
| **Motor** | Async MongoDB driver |
| **Pydantic v2** | Data validation and serialization |
| **Redis** | MFA sessions, OTP storage, rate limiting |
| **PyJWT** | JSON Web Token authentication |
| **Argon2** | Secure password hashing |
| **PyOTP** | TOTP-based Multi-Factor Authentication |
| **SlowAPI** | Rate limiting middleware |
| **Uvicorn** | ASGI server |
| **Python-dotenv** | Environment variable management |

---

## 📁 Project Structure

```
B2B_HRMS_BACKEND/
│
├── app.py                  # FastAPI app entry point (CORS, startup, exception handlers)
├── main.py                 # Uvicorn server runner
├── requirements.txt        # Python dependencies
├── .env                    # Environment variables (not committed to VCS)
├── .gitignore
│
├── Database/               # MongoDB connection & initialization (Beanie setup)
│   └── __init__.py
│
├── Models/                 # Beanie/Pydantic document models (DB schemas)
│   ├── attendance.py
│   ├── billing.py
│   ├── crm.py
│   ├── employee.py
│   ├── payroll.py
│   ├── tenant_user.py
│   └── ... (30+ models)
│
├── Routes/                 # FastAPI routers — one file per module
│   ├── auth.py
│   ├── employee.py
│   ├── payroll.py
│   ├── crm.py
│   ├── attendance.py
│   └── ... (34 route files)
│
├── Services/               # Business logic layer — one service per module
│   ├── auth_service.py
│   ├── employee_service.py
│   ├── payroll_service.py
│   ├── crm_service.py
│   └── ... (28 service files)
│
├── Schema/                 # Pydantic request/response schemas
├── Utility/                # Shared utilities (rate limiter, helpers, etc.)
└── static/                 # Static file serving
```

---

## 🚀 Getting Started

### Prerequisites

- **Python** 3.10+
- **MongoDB Atlas** account (or local MongoDB 6+)
- **Redis** server (local or cloud — e.g., Redis Cloud, Upstash)
- **Git**

---

### Installation

**1. Clone the repository**
```bash
git clone <your-repo-url>
cd B2B_HRMS_BACKEND
```

**2. Create and activate a virtual environment**
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS / Linux
python -m venv venv
source venv/bin/activate
```

**3. Install dependencies**
```bash
pip install -r requirements.txt
```

---

### Environment Variables

Create a `.env` file in the project root (copy the structure below):

```env
# MongoDB
MONGODB_URL=mongodb+srv://<username>:<password>@cluster.mongodb.net/<dbname>
MONGODB_DB_NAME=workmatrix

# Application
APP_ENV=development
SECRET_KEY=your-strong-secret-key-here

# CORS
ALLOWED_ORIGINS=http://localhost:3003,https://your-frontend.com

# Frontend URL (used in email links)
FRONTEND_URL=http://localhost:3003

# Email / SMTP
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_ADDRESS=your-email@gmail.com
EMAIL_PASSWORD=your-app-password
EMAIL_USE_TLS=true

# Redis (for MFA & OTP)
REDIS_URL=redis://localhost:6379
```

> ⚠️ **Never commit your `.env` file to version control.** It is already listed in `.gitignore`.

---

### Running the Server

**Development mode (with auto-reload)**
```bash
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

**Or using main.py**
```bash
python main.py
```

The API will be available at: **http://localhost:8000**

---

## 📡 API Modules

| Tag | Description |
|---|---|
| Authentication | Login, register, MFA, password reset |
| User Profile | User profile management |
| Tenants | Super admin tenant management |
| Plans | Subscription plan management |
| Trial | Trial management |
| Onboarding | Employee onboarding workflows |
| Invitations | Invite employees via email |
| Employee Management | Employee CRUD, documents, status |
| Employee Self-Service | Employee self-service portal |
| Attendance | Clock-in/out, reports |
| Leave Management | Leave types, policies |
| Employee Leave | Employee leave requests |
| Payroll | Salary, payslips, payroll runs |
| Holiday | Company holiday calendar |
| Roles & Permissions | RBAC management |
| CRM | Leads, deals, pipelines |
| CRM Contacts | Contact management |
| CRM Tasks | Task tracking in CRM |
| Deal Workspace | Deal collaboration workspace |
| Deal Associations | Link deals with contacts/companies |
| Notes | Unified notes |
| Project Management | Projects and tasks |
| Assignments | Team workload assignment |
| Announcements | Company announcements |
| Tickets | Support ticketing |
| Billing | Subscriptions and invoices |
| Audit Logs | Activity trail |
| Dashboards | Analytics dashboards |
| Job Requisition | Internal job requisitions |
| Job Posting | Job postings |

---

## 🔐 Authentication & Security

- **JWT Tokens** — Access and refresh token-based authentication.
- **Argon2 Password Hashing** — Industry-standard secure password storage.
- **MFA (TOTP)** — Time-based One-Time Passwords via PyOTP, sessions stored in Redis.
- **Email Verification** — Token-based email verification on registration.
- **Login Security** — Failed login tracking, account lockout, suspicious activity detection.
- **Rate Limiting** — SlowAPI-powered rate limiting to prevent brute-force attacks.
- **CORS** — Configurable allowed origins via environment variables.

---

## 📖 API Documentation

Once the server is running, interactive API documentation is available at:

| Interface | URL |
|---|---|
| **Swagger UI** | http://localhost:8000/docs |
| **ReDoc** | http://localhost:8000/redoc |
| **Health Check** | http://localhost:8000/health |

---

## 🤝 Contributing

1. Fork the repository
2. Create your feature branch: `git checkout -b feature/your-feature`
3. Commit your changes: `git commit -m "feat: add your feature"`
4. Push to the branch: `git push origin feature/your-feature`
5. Open a Pull Request

---

## 📄 License

This project is proprietary software. All rights reserved.

---

Built with ❤️ using FastAPI & MongoDB  
**WorkMatrix** — Powering Modern HR Management
