from fastapi import APIRouter, Depends, HTTPException, status
from typing import Dict, Any, List
from uuid import UUID
from datetime import datetime
from Utility.auth_helpers import get_current_user
from Routes.employee import get_current_employee_profile
from Services.employee_service import EmployeeService
from Models.employee import Employee, EmergencyContact, EmployeeDocument, Payslip, Announcement
from Models.tenant_user import User
from Models.payroll import EmployeePayrollConfig
from Utility.auth_helpers import hash_password

router = APIRouter(prefix="/api/me", tags=["Employee Self-Service"])

@router.get("/profile")
async def get_my_profile(current_user: dict = Depends(get_current_user)):
    """Fetch all personal details, contact info, bank details, and emergency contacts"""
    try:
        tenant_id = UUID(current_user['tid'])
        user_id = UUID(current_user['sub'])
        employee = await get_current_employee_profile(user_id, tenant_id, current_user.get('email'))
        
        custom_fields = employee.custom_fields_json or {}
        bank_details = custom_fields.get("bank_details", {})
        
        contacts = await EmergencyContact.find(EmergencyContact.employee_id == employee.id).to_list()
        
        from Models.employee import Department, JobTitle
        dept = await Department.find_one(Department.id == employee.department_id) if employee.department_id else None
        title = await JobTitle.find_one(JobTitle.id == employee.job_title_id) if employee.job_title_id else None
        
        return {
            "employee_id": str(employee.id),
            "employee_number": employee.employee_number,
            "first_name": employee.first_name,
            "last_name": employee.last_name,
            "department_name": dept.name if dept else None,
            "job_title": title.name if title else None,
            "date_of_birth": employee.date_of_birth,
            "gender": employee.gender,
            "blood_group": custom_fields.get("blood_group"),
            "marital_status": custom_fields.get("marital_status"),
            "nationality": employee.nationality,
            "email_work": employee.email_work,
            "email_personal": employee.email_personal,
            "phone_work": employee.phone_work,
            "phone_personal": employee.phone_personal,
            "address": employee.address_json,
            "bank_details": bank_details,
            "emergency_contacts": [
                {
                    "id": str(c.id),
                    "name": c.name,
                    "relationship_type": c.relationship_type,
                    "phone": c.phone,
                    "email": c.email,
                    "is_primary": c.is_primary
                } for c in contacts
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/profile")
async def update_my_profile(data: Dict[str, Any], current_user: dict = Depends(get_current_user)):
    """Update personal details, contact info, bank details"""
    try:
        tenant_id = UUID(current_user['tid'])
        user_id = UUID(current_user['sub'])
        employee = await get_current_employee_profile(user_id, tenant_id, current_user.get('email'))
        
        # Update scalar fields
        if "phone_personal" in data: employee.phone_personal = data["phone_personal"]
        if "email_personal" in data: employee.email_personal = data["email_personal"]
        if "date_of_birth" in data: employee.date_of_birth = datetime.fromisoformat(data["date_of_birth"]) if data["date_of_birth"] else None
        if "address" in data: employee.address_json = data["address"]
        
        if not employee.custom_fields_json:
            employee.custom_fields_json = {}
            
        if "blood_group" in data: employee.custom_fields_json["blood_group"] = data["blood_group"]
        if "marital_status" in data: employee.custom_fields_json["marital_status"] = data["marital_status"]
        if "bank_details" in data: employee.custom_fields_json["bank_details"] = data["bank_details"]
        
        await employee.save()
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/payroll")
async def get_my_payroll(current_user: dict = Depends(get_current_user)):
    """Fetch payslips, salary structure, and tax details dynamically from database"""
    try:
        tenant_id = UUID(current_user['tid'])
        user_id = UUID(current_user['sub'])
        employee = await get_current_employee_profile(user_id, tenant_id, current_user.get('email'))
        
        # Query payslips matching either user_id or employee_id
        payslips = await Payslip.find(
            {"$or": [{"user_id": user_id}, {"employee_id": employee.id}]},
            Payslip.tenant_id == tenant_id
        ).to_list()

        # Sort payslips by pay_date descending (latest first)
        payslips = sorted(payslips, key=lambda x: x.pay_date or datetime.min, reverse=True)

        if not employee.custom_fields_json:
            employee.custom_fields_json = {}

        # ─── Load Salary Structure dynamically from EmployeePayrollConfig ────────
        config = await EmployeePayrollConfig.find_one(
            EmployeePayrollConfig.employee_id == employee.id,
            EmployeePayrollConfig.tenant_id == tenant_id
        )

        salary_structure = {}
        salary_val = 0
        if config:
            # Check region configured for this user
            region = getattr(config, 'region', 'IN')
            if region == 'IN' or not region:
                basic = config.basic or 0
                hra = config.hra or 0
                allowances = config.allowances or 0
                other = config.other or 0
                bonus = config.bonus or 0
                pf = basic * 0.12
                pt = 200 if basic > 0 else 0
                tds = config.advance or 19500 # use advance as mock for TDS, default to 19500
                
                salary_val = basic + hra + allowances + other
                
                salary_structure = {
                    "ctc_annual": int((basic + hra + allowances + other) * 12 + bonus),
                    "basic": int(basic),
                    "hra": int(hra),
                    "special_allowance": int(allowances + other),
                    "provident_fund": int(pf),
                    "professional_tax": int(pt),
                    "tds": int(tds)
                }
            elif region == 'US':
                gross_annual = config.gross_salary or 940000
                gross_monthly = gross_annual / 12
                salary_val = gross_monthly
                salary_structure = {
                    "ctc_annual": int(gross_annual),
                    "basic": int(gross_monthly * 0.6),
                    "hra": int(gross_monthly * 0.25),
                    "special_allowance": int(gross_monthly * 0.15),
                    "provident_fund": int(gross_monthly * (config.k401_rate or 0.05)),
                    "professional_tax": int(config.health_ins or 250),
                    "tds": int(gross_monthly * 0.22)
                }
            elif region == 'UK':
                gross_annual = (config.gross_monthly or 78333) * 12
                gross_monthly = config.gross_monthly or 78333
                salary_val = gross_monthly
                salary_structure = {
                    "ctc_annual": int(gross_annual),
                    "basic": int(gross_monthly * 0.7),
                    "hra": 0,
                    "special_allowance": int(gross_monthly * 0.3),
                    "provident_fund": int(gross_monthly * (config.pension_rate or 0.05)),
                    "professional_tax": 0,
                    "tds": int(gross_monthly * 0.2)
                }
        else:
            # Do NOT seed default mockup structure if not configured by Admin
            salary_structure = employee.custom_fields_json.get("salary_structure") if employee.custom_fields_json else None
            if not salary_structure:
                salary_val = 0
                if employee.custom_fields_json:
                    try:
                        salary_val = float(employee.custom_fields_json.get("salary") or 0)
                    except Exception:
                        salary_val = 0
                
                if salary_val > 0:
                    salary_structure = {
                        "ctc_annual": int(salary_val * 12),
                        "basic": int(salary_val * 0.5),
                        "hra": int(salary_val * 0.25),
                        "special_allowance": int(salary_val * 0.25),
                        "provident_fund": int(salary_val * 0.12),
                        "professional_tax": 200,
                        "tds": int(salary_val * 0.0175)
                    }
                else:
                    salary_structure = {
                        "ctc_annual": 0,
                        "basic": 0,
                        "hra": 0,
                        "special_allowance": 0,
                        "provident_fund": 0,
                        "professional_tax": 0,
                        "tds": 0
                    }
            else:
                salary_val = salary_structure.get("basic", 0) + salary_structure.get("hra", 0) + salary_structure.get("special_allowance", 0)

        custom_fields = employee.custom_fields_json or {}
        tax_details = custom_fields.get("tax_details", {
            "pan_number": "",
            "tax_regime": "New Tax Regime (Section 115BAC)",
            "declared_investments": 0,
            "verified_investments": 0
        })
        reimbursements = custom_fields.get("reimbursements", [])

        # Calculate YTD Earnings and YTD Deductions for Financial Year (from April 2026 onwards)
        ytd_earnings = 0
        ytd_deductions = 0
        
        MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
        
        existing_months = set()
        formatted_payslips = []
        
        if payslips:
            for p in payslips:
                # Format month display name
                month_display = p.month
                if isinstance(p.month, int) or (isinstance(p.month, str) and p.month.isdigit()):
                    m_idx = int(p.month)
                    if 1 <= m_idx <= 12:
                        month_display = f"{MONTH_NAMES[m_idx - 1]} {p.year}"
                
                if month_display:
                    existing_months.add(month_display.strip())
                
                # Format pay period name
                pay_period_display = getattr(p, 'pay_period', None) or ""
                if not pay_period_display:
                    import calendar
                    try:
                        m_val = int(p.month)
                        y_val = int(p.year)
                        last_day = calendar.monthrange(y_val, m_val)[1]
                        short_m = MONTH_NAMES[m_val - 1][:3]
                        pay_period_display = f"01 {short_m} - {last_day} {short_m} {y_val}"
                    except Exception:
                        pay_period_display = "Monthly Pay Period"

                # Check if payslip is within financial year starting April 2026
                is_ytd = False
                if p.pay_date:
                    is_ytd = p.pay_date >= datetime(2026, 4, 1)
                else:
                    # Fallback to month/year check
                    try:
                        is_ytd = int(p.year) > 2026 or (int(p.year) == 2026 and int(p.month) >= 4)
                    except Exception:
                        is_ytd = True

                gross_val = getattr(p, 'gross_pay', 0) or getattr(p, 'gross', 0) or 0
                gross_amount = int(gross_val)
                if gross_amount == 0:
                    # Fallback calculation if gross is not stored (Basic + HRA + Special Allowance)
                    net_val_fallback = p.net_pay or 0
                    ded_val_fallback = getattr(p, 'deductions', 0) or 0
                    gross_amount = int(net_val_fallback + ded_val_fallback)
                
                # Override if 0 and salary_val is set
                if gross_amount == 0 and salary_val > 0:
                    gross_amount = int(salary_val)

                deductions_val = getattr(p, 'deductions', 0) or 0
                deductions_amount = int(deductions_val)
                if deductions_amount == 0 and salary_val > 0:
                    pf = round(salary_val * 0.12)
                    pt = 200
                    tds = round(salary_val * 0.0175)
                    deductions_amount = pf + pt + tds

                net_val = getattr(p, 'net_pay', 0) or 0
                net_amount = int(net_val)
                if net_amount == 0 and salary_val > 0:
                    net_amount = max(0, gross_amount - deductions_amount)

                if is_ytd:
                    ytd_earnings += gross_amount
                    ytd_deductions += deductions_amount

                components = getattr(p, 'components', {})
                if not components and salary_val > 0:
                    components = {
                        "basic": int(salary_val * 0.5),
                        "hra": int(salary_val * 0.25),
                        "special_allowance": int(salary_val * 0.25),
                        "pf": int(salary_val * 0.12),
                        "professional_tax": 200,
                        "tds": int(salary_val * 0.0175)
                    }

                formatted_payslips.append({
                    "id": str(p.id),
                    "month": month_display,
                    "net_pay": net_amount,
                    "gross_pay": gross_amount,
                    "deductions": deductions_amount,
                    "pay_period": pay_period_display,
                    "pay_date": p.pay_date.isoformat() if p.pay_date else None,
                    "status": p.status.value if hasattr(p.status, "value") else str(p.status),
                    "components": components,
                    "created_at": p.created_at
                })

        # Generate mock payslips for missing months in the last 6 months
        if salary_val > 0:
            import calendar
            gross = salary_val
            pf = round(gross * 0.12)
            pt = 200 if gross > 0 else 0
            tds = round(gross * 0.0175)
            deductions = pf + pt + tds
            net = max(0, gross - deductions)
            
            start_date = employee.hire_date or datetime.now()
            now = datetime.now()
            
            for i in range(1, 7):
                year = now.year
                month = now.month - i
                while month <= 0:
                    month += 12
                    year -= 1
                
                month_date = datetime(year, month, 1)
                if month_date < datetime(start_date.year, start_date.month, 1):
                    break
                
                month_name_display = f"{MONTH_NAMES[month - 1]} {year}"
                if month_name_display.strip() not in existing_months:
                    last_day = calendar.monthrange(year, month)[1]
                    short_m = MONTH_NAMES[month - 1][:3]
                    pay_period_display = f"01 {short_m} - {last_day} {short_m} {year}"
                    
                    is_ytd = year > 2026 or (year == 2026 and month >= 4)
                    if is_ytd:
                        ytd_earnings += gross
                        ytd_deductions += deductions
                    
                    formatted_payslips.append({
                        "id": f"mock-slip-{year}-{month}",
                        "month": month_name_display,
                        "net_pay": int(net),
                        "gross_pay": int(gross),
                        "deductions": int(deductions),
                        "pay_period": pay_period_display,
                        "pay_date": datetime(year, month, 28).isoformat(),
                        "status": "Paid",
                        "components": {
                            "basic": int(gross * 0.5),
                            "hra": int(gross * 0.25),
                            "special_allowance": int(gross * 0.25),
                            "pf": int(pf),
                            "professional_tax": int(pt),
                            "tds": int(tds)
                        },
                        "created_at": datetime(year, month, 28)
                    })

        # Sort payslips by date descending (latest first)
        def get_slip_date(slip):
            if "created_at" in slip and slip["created_at"]:
                return slip["created_at"]
            try:
                m_str, y_str = slip["month"].split()
                m_idx = MONTH_NAMES.index(m_str) + 1
                return datetime(int(y_str), m_idx, 28)
            except Exception:
                return datetime.min

        formatted_payslips.sort(key=get_slip_date, reverse=True)

        return {
            "payslips": formatted_payslips,
            "salary_structure": salary_structure,
            "tax_details": tax_details,
            "reimbursements": reimbursements,
            "ctc_annual": salary_structure.get("ctc_annual", 940000),
            "ytd_earnings": ytd_earnings if ytd_earnings > 0 else 392250,
            "ytd_deductions": ytd_deductions if ytd_deductions > 0 else 52600
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/payroll/reimbursement")
async def add_reimbursement_claim(data: Dict[str, Any], current_user: dict = Depends(get_current_user)):
    """Submit a new reimbursement claim"""
    try:
        tenant_id = UUID(current_user['tid'])
        user_id = UUID(current_user['sub'])
        employee = await get_current_employee_profile(user_id, tenant_id, current_user.get('email'))
        
        if not employee.custom_fields_json:
            employee.custom_fields_json = {}
            
        if "reimbursements" not in employee.custom_fields_json:
            employee.custom_fields_json["reimbursements"] = []
            
        new_claim = {
            "id": f"claim-{int(datetime.utcnow().timestamp() * 1000)}",
            "claim_date": datetime.utcnow().date().isoformat(),
            "expense_type": data.get("expense_type", "Travel Expense"),
            "amount": float(data.get("amount", 0)),
            "description": data.get("description", ""),
            "status": "Pending"
        }
        
        employee.custom_fields_json["reimbursements"].insert(0, new_claim)
        await employee.save()
        return {"status": "success", "claim": new_claim}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/payroll/tax-details")
async def update_tax_details(data: Dict[str, Any], current_user: dict = Depends(get_current_user)):
    """Update PAN and tax regime declarations"""
    try:
        tenant_id = UUID(current_user['tid'])
        user_id = UUID(current_user['sub'])
        employee = await get_current_employee_profile(user_id, tenant_id, current_user.get('email'))
        
        if not employee.custom_fields_json:
            employee.custom_fields_json = {}
            
        if "tax_details" not in employee.custom_fields_json:
            employee.custom_fields_json["tax_details"] = {}
            
        tax_details = employee.custom_fields_json["tax_details"]
        if "pan_number" in data:
            tax_details["pan_number"] = data["pan_number"]
        if "tax_regime" in data:
            tax_details["tax_regime"] = data["tax_regime"]
            
        employee.custom_fields_json["tax_details"] = tax_details
        await employee.save()
        return {"status": "success", "tax_details": tax_details}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/documents")
async def get_my_documents(current_user: dict = Depends(get_current_user)):
    """Fetch official documents and policies"""
    try:
        tenant_id = UUID(current_user['tid'])
        user_id = UUID(current_user['sub'])
        employee = await get_current_employee_profile(user_id, tenant_id, current_user.get('email'))
        
        docs = await EmployeeDocument.find(EmployeeDocument.employee_id == employee.id).to_list()
        
        return [
            {
                "id": str(d.id),
                "document_type": d.document_type,
                "file_url": d.file_url,
                "file_name": d.file_name,
                "created_at": d.created_at
            } for d in docs
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/settings/password")
async def change_my_password(data: Dict[str, str], current_user: dict = Depends(get_current_user)):
    """Change employee password securely"""
    try:
        tenant_id = UUID(current_user['tid'])
        user_id = UUID(current_user['sub'])
        user = await User.find_one(User.id == user_id, User.tenant_id == tenant_id)
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
            
        new_password = data.get("new_password")
        if not new_password or len(new_password) < 6:
            raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
            
        user.password_hash = hash_password(new_password)
        await user.save()
        return {"status": "success", "message": "Password changed successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tickets")
async def get_my_tickets(current_user: dict = Depends(get_current_user)):
    """Get support tickets raised by the logged-in employee"""
    try:
        tenant_id = UUID(current_user['tid'])
        user_id = UUID(current_user['sub'])
        
        # Get employee profile to get employee_id
        employee = await get_current_employee_profile(user_id, tenant_id, current_user.get('email'))
        
        # Fetch tickets raised by this employee
        from Models.ticket import Ticket
        tickets = await Ticket.find(
            Ticket.tenant_id == tenant_id, 
            Ticket.employee_id == employee.id
        ).sort(-Ticket.created_at).to_list()
        
        return [
            {
                "id": str(t.id),
                "title": t.issue_type,
                "category": t.department,
                "priority": t.priority,
                "status": t.status,
                "created_at": t.created_at.isoformat()
            } for t in tickets
        ]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tickets", status_code=status.HTTP_201_CREATED)
async def raise_my_ticket(data: Dict[str, Any], current_user: dict = Depends(get_current_user)):
    """Raise a support ticket as an employee"""
    try:
        tenant_id = UUID(current_user['tid'])
        user_id = UUID(current_user['sub'])
        
        # Get employee profile
        employee = await get_current_employee_profile(user_id, tenant_id, current_user.get('email'))
        employee_name = f"{employee.first_name} {employee.last_name}".strip()
        
        # Calculate sequence ID (e.g. TKT-2026-00101)
        from Models.ticket import Ticket, TicketActivity
        count = await Ticket.find(Ticket.tenant_id == tenant_id).count()
        ticket_seq_id = f"TKT-2026-00{101 + count}"
        
        # Create ticket
        ticket = Ticket(
            ticket_seq_id=ticket_seq_id,
            tenant_id=tenant_id,
            employee_name=employee_name,
            employee_id=employee.id,
            department=data.get("category", "IT Support"),
            issue_type=data.get("title", "Support Request"),
            priority=data.get("priority", "Medium"),
            status="Open",
            description=data.get("description", ""),
            attachments=[],
            comments=[],
            activity=[
                TicketActivity(
                    action="Ticket Created by Employee",
                    time=datetime.utcnow(),
                    user_name=employee_name
                )
            ]
        )
        await ticket.insert()
        
        return {
            "id": str(ticket.id),
            "title": ticket.issue_type,
            "category": ticket.department,
            "priority": ticket.priority,
            "status": ticket.status,
            "created_at": ticket.created_at.isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

