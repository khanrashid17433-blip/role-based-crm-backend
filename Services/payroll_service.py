import secrets
import math
import calendar
from typing import List, Dict, Any, Optional, Tuple
from uuid import UUID
from datetime import datetime, date, timezone

from Models.payroll import (
    PayrollRun, Payslip, EmployeePayrollConfig,
    PayrollRegion, PayrollStatus, PayslipStatus
)
from Models.employee import Employee, Department, JobTitle
from Services.attendance_service import AttendanceService


# ─── India Tax Calculations ────────────────────────────────────────────────────
def calc_in_deductions(basic: float, hra: float, allowances: float, bonus: float = 0, overtime: float = 0, loan: float = 0, advance: float = 0, other: float = 0) -> Dict[str, float]:
    gross = basic + hra + allowances + bonus + overtime
    pf = round(basic * 0.12)
    esi = round(gross * 0.0325) if gross <= 21000 else 0
    prof_tax = 200 if gross > 15000 else (150 if gross > 10000 else 0)
    annual = gross * 12
    tds = 0
    if annual > 1500000:
        tds = round((annual - 1500000) * 0.30 / 12)
    elif annual > 1200000:
        tds = round((annual - 1200000) * 0.20 / 12)
    elif annual > 900000:
        tds = round((annual - 900000) * 0.15 / 12)
    elif annual > 600000:
        tds = round((annual - 600000) * 0.10 / 12)
    deductions = pf + esi + prof_tax + tds + loan + advance + other
    return {
        "gross": gross, "pf": pf, "esi": esi,
        "prof_tax": prof_tax, "tds": tds,
        "loan": loan, "advance": advance, "other": other,
        "deductions": deductions, "net_pay": gross - deductions
    }


# ─── US Tax Calculations ───────────────────────────────────────────────────────
US_STATE_TAX = {
    "CA": 0.093, "NY": 0.0685, "TX": 0.0, "WA": 0.0,
    "IL": 0.0495, "FL": 0.0, "OR": 0.099, "NJ": 0.0637,
    "MA": 0.05, "GA": 0.055
}

def calc_us_deductions(gross: float, state: str, k401_rate: float, health_ins: float) -> Dict[str, float]:
    federal_tax = round(gross * 0.22)
    state_rate = US_STATE_TAX.get(state, 0.05)
    state_tax = round(gross * state_rate)
    social_sec = round(gross * 0.062)
    medicare = round(gross * 0.0145)
    k401 = round(gross * k401_rate)
    total_ded = federal_tax + state_tax + social_sec + medicare + k401 + int(health_ins)
    return {
        "gross": gross, "federal_tax": federal_tax, "state_tax": state_tax,
        "social_sec": social_sec, "medicare": medicare,
        "k401": k401, "health_ins": health_ins,
        "deductions": total_ded, "net_pay": gross - total_ded
    }


# ─── UK Tax Calculations ───────────────────────────────────────────────────────
UK_PA_MONTHLY = 1047.5

def calc_uk_deductions(gross: float, pension_rate: float) -> Dict[str, float]:
    taxable = max(0, gross - UK_PA_MONTHLY)
    basic_band = 4189
    if taxable <= basic_band:
        paye = round(taxable * 0.20)
    else:
        paye = round(basic_band * 0.20 + (taxable - basic_band) * 0.40)
    ni_lower, ni_upper = 1048, 4189
    ni = 0
    if gross > ni_lower:
        niable = min(gross, ni_upper) - ni_lower
        ni = round(niable * 0.12)
        if gross > ni_upper:
            ni += round((gross - ni_upper) * 0.02)
    pension = round(gross * pension_rate)
    total_ded = paye + ni + pension
    return {
        "gross": gross, "paye": paye, "ni": ni,
        "pension": pension, "deductions": total_ded,
        "net_pay": gross - total_ded
    }


MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
]


class PayrollService:

    # ── Employee Payroll Config ────────────────────────────────────────────────
    @staticmethod
    async def get_employee_configs(tenant_id: UUID, region: str) -> List[EmployeePayrollConfig]:
        return await EmployeePayrollConfig.find(
            EmployeePayrollConfig.tenant_id == tenant_id,
            EmployeePayrollConfig.region == region,
            EmployeePayrollConfig.is_active == True
        ).to_list()

    @staticmethod
    async def upsert_employee_config(
        tenant_id: UUID, employee_id: UUID, region: str, data: Dict[str, Any]
    ) -> EmployeePayrollConfig:
        existing = await EmployeePayrollConfig.find_one(
            EmployeePayrollConfig.tenant_id == tenant_id,
            EmployeePayrollConfig.employee_id == employee_id,
            EmployeePayrollConfig.region == region
        )
        if existing:
            for k, v in data.items():
                if hasattr(existing, k):
                    setattr(existing, k, v)
            existing.updated_at = datetime.utcnow()
            await existing.save()
            return existing
        config = EmployeePayrollConfig(
            tenant_id=tenant_id, employee_id=employee_id,
            region=region, **data
        )
        await config.insert()
        return config

    # ── Dashboard Summary ──────────────────────────────────────────────────────
    @staticmethod
    async def get_dashboard(tenant_id: UUID, region: str, month: int = None, year: int = None) -> Dict[str, Any]:
        employees = await Employee.find(
            Employee.tenant_id == tenant_id,
            Employee.employment_status == "active"
        ).to_list()
        
        if not employees:
            return PayrollService._empty_dashboard(region)

        configs = await PayrollService.get_employee_configs(tenant_id, region)
        config_map = {c.employee_id: c for c in configs}

        employees_data = []
        for emp in employees:
            cfg = config_map.get(emp.id)
            
            if month and year:
                payslip = await Payslip.find_one(
                    Payslip.tenant_id == tenant_id,
                    Payslip.employee_id == emp.id,
                    Payslip.month == month,
                    Payslip.year == year
                )
            else:
                payslip = None

            dept_name = ""
            if emp.department_id:
                dept = await Department.find_one(Department.id == emp.department_id)
                dept_name = dept.name if dept else ""
            job_title = ""
            if emp.job_title_id:
                jt = await JobTitle.find_one(JobTitle.id == emp.job_title_id)
                job_title = jt.name if jt else ""
            
            has_bank = False
            if emp.custom_fields_json and "bank_account" in emp.custom_fields_json:
                has_bank = True

            row = {
                "id": str(emp.id),
                "name": f"{emp.first_name} {emp.last_name}",
                "designation": job_title or getattr(emp, 'job_title', ""),
                "dept": dept_name,
                "status": payslip.status.value if payslip else "Pending",
                "has_bank_details": has_bank,
            }

            if payslip:
                row.update(payslip.components)
                row["gross"] = payslip.gross
                row["deductions"] = payslip.deductions
                row["net_pay"] = payslip.net_pay
            else:
                if region == "IN":
                    basic = cfg.basic if cfg and cfg.basic else 0
                    hra = cfg.hra if cfg and cfg.hra else 0
                    allow = cfg.allowances if cfg and cfg.allowances else 0
                    bonus = cfg.bonus if cfg and cfg.bonus else 0
                    overtime = cfg.overtime if cfg and cfg.overtime else 0
                    loan = cfg.loan if cfg and cfg.loan else 0
                    advance = cfg.advance if cfg and cfg.advance else 0
                    other = cfg.other if cfg and cfg.other else 0
                    c = calc_in_deductions(basic, hra, allow, bonus, overtime, loan, advance, other)
                    row.update({"basic": basic, "hra": hra, "allowances": allow, "bonus": bonus, "overtime": overtime, **c})
                elif region == "US":
                    gross = cfg.gross_salary if cfg and cfg.gross_salary else 0
                    state = cfg.state if cfg and cfg.state else "CA"
                    k401 = cfg.k401_rate if cfg and cfg.k401_rate else 0.05
                    health = cfg.health_ins if cfg and cfg.health_ins else 250
                    c = calc_us_deductions(gross, state, k401, health)
                    row.update({"state": state, "pay_type": cfg.pay_type if cfg else "Salary", "k401_rate": k401, **c})
                elif region == "UK":
                    gross = cfg.gross_monthly if cfg and cfg.gross_monthly else 0
                    pension = cfg.pension_rate if cfg and cfg.pension_rate else 0.05
                    c = calc_uk_deductions(gross, pension)
                    row.update({"ni_code": cfg.ni_code if cfg else "A", "pension_rate": pension, **c})
            employees_data.append(row)

        return PayrollService._build_summary(region, employees_data)

    @staticmethod
    def _empty_dashboard(region: str) -> Dict[str, Any]:
        return {
            "region": region, "employees": [],
            "summary": {}, "dept_breakdown": [],
            "total_gross": 0, "total_net": 0, "total_deductions": 0
        }

    @staticmethod
    def _build_summary(region: str, employees: List[Dict]) -> Dict[str, Any]:
        total_gross = sum(e.get("gross", 0) for e in employees)
        total_net = sum(e.get("net_pay", 0) for e in employees)
        total_ded = sum(e.get("deductions", 0) for e in employees)

        summary: Dict[str, Any] = {
            "total_gross": total_gross,
            "total_net": total_net,
            "total_deductions": total_ded,
            "employee_count": len(employees),
        }
        if region == "IN":
            summary.update({
                "total_pf": sum(e.get("pf", 0) for e in employees),
                "total_esi": sum(e.get("esi", 0) for e in employees),
                "total_prof_tax": sum(e.get("prof_tax", 0) for e in employees),
                "total_tds": sum(e.get("tds", 0) for e in employees),
            })
        elif region == "US":
            summary.update({
                "total_federal": sum(e.get("federal_tax", 0) for e in employees),
                "total_state": sum(e.get("state_tax", 0) for e in employees),
                "total_social_sec": sum(e.get("social_sec", 0) for e in employees),
                "total_medicare": sum(e.get("medicare", 0) for e in employees),
                "total_401k": sum(e.get("k401", 0) for e in employees),
                "total_health": sum(e.get("health_ins", 0) for e in employees),
            })
        elif region == "UK":
            summary.update({
                "total_paye": sum(e.get("paye", 0) for e in employees),
                "total_ni": sum(e.get("ni", 0) for e in employees),
                "total_pension": sum(e.get("pension", 0) for e in employees),
            })

        dept_map: Dict[str, Dict] = {}
        for e in employees:
            d = e.get("dept", "Other")
            if not d: d = "Other"
            if d not in dept_map:
                dept_map[d] = {"dept": d, "net_pay": 0, "count": 0}
            dept_map[d]["net_pay"] += e.get("net_pay", 0)
            dept_map[d]["count"] += 1
        dept_breakdown = sorted(dept_map.values(), key=lambda x: x["net_pay"], reverse=True)

        return {
            "region": region,
            "employees": employees,
            "summary": summary,
            "dept_breakdown": dept_breakdown,
        }

    # ── Attendance Sync ─────────────────────────────────────────────────────────
    @staticmethod
    async def sync_attendance(tenant_id: UUID, region: str, month: int, year: int, employee_ids: List[UUID] = None) -> List[Dict]:
        start_date = date(year, month, 1)
        end_date = date(year, month, calendar.monthrange(year, month)[1])
        
        employees = await Employee.find(
            Employee.tenant_id == tenant_id,
            Employee.employment_status == "active"
        ).to_list()
        if employee_ids:
            emp_id_strs = [str(e) for e in employee_ids]
            employees = [e for e in employees if str(e.id) in emp_id_strs]
            
        results = []
        for emp in employees:
            logs = await AttendanceService.get_attendance_logs(
                tenant_id, start_date, end_date, employee_id=emp.id
            )
            
            present_days = sum(1 for log in logs if log.status and log.status.value == "present")
            absent_days = sum(1 for log in logs if log.status and log.status.value == "absent")
            
            ot_hours = sum(max(0, log.working_hours - 9.0) for log in logs if log.working_hours)
            
            leave_days = 0
            if emp.custom_fields_json and "leave_history" in emp.custom_fields_json:
                for leave in emp.custom_fields_json["leave_history"]:
                    l_start = datetime.fromisoformat(leave["start_date"]).date()
                    l_end = datetime.fromisoformat(leave["end_date"]).date()
                    if l_start <= end_date and l_end >= start_date:
                        overlap_start = max(l_start, start_date)
                        overlap_end = min(l_end, end_date)
                        leave_days += (overlap_end - overlap_start).days + 1

            results.append({
                "employee_id": str(emp.id),
                "name": f"{emp.first_name} {emp.last_name}",
                "total_days": (end_date - start_date).days + 1,
                "present_days": present_days,
                "absent_days": absent_days,
                "leave_days": leave_days,
                "ot_hours": round(ot_hours, 2)
            })
            
        return results

    # ── Lock Period ────────────────────────────────────────────────────────────
    @staticmethod
    async def lock_period(tenant_id: UUID, region: str, month: int, year: int, lock: bool, employee_ids: List[UUID], admin_id: UUID) -> PayrollRun:
        run = await PayrollRun.find_one(
            PayrollRun.tenant_id == tenant_id,
            PayrollRun.region == PayrollRegion(region),
            PayrollRun.month == month,
            PayrollRun.year == year
        )
        if not run:
            if not lock:
                return None
            run = PayrollRun(
                tenant_id=tenant_id,
                region=PayrollRegion(region),
                month=month,
                year=year,
                status=PayrollStatus.draft,
                employee_ids=employee_ids,
                created_by=admin_id
            )
            await run.insert()
        else:
            if lock:
                run.status = PayrollStatus.draft
                run.employee_ids = employee_ids
            else:
                await run.delete()
                return None
            await run.save()
            
        return run

    # ── HR Update Overrides ───────────────────────────────────────────────────
    @staticmethod
    async def update_earnings(tenant_id: UUID, employee_id: UUID, data: Dict[str, Any]) -> None:
        cfg = await EmployeePayrollConfig.find_one(
            EmployeePayrollConfig.tenant_id == tenant_id,
            EmployeePayrollConfig.employee_id == employee_id
        )
        if cfg:
            for k, v in data.items():
                if hasattr(cfg, k):
                    setattr(cfg, k, v)
            cfg.updated_at = datetime.utcnow()
            await cfg.save()
        else:
            cfg = EmployeePayrollConfig(
                tenant_id=tenant_id,
                employee_id=employee_id,
                region="IN", # Defaults to IN if created here, typically UI sets this
                **data
            )
            await cfg.insert()

    # ── Approve Payroll ────────────────────────────────────────────────────────
    @staticmethod
    async def approve_payroll(tenant_id: UUID, region: str, month: int, year: int) -> bool:
        run = await PayrollRun.find_one(
            PayrollRun.tenant_id == tenant_id,
            PayrollRun.region == PayrollRegion(region),
            PayrollRun.month == month,
            PayrollRun.year == year
        )
        if not run:
            raise ValueError("Payroll run not found for this period")
        
        run.status = PayrollStatus.processed
        await run.save()
        return True

    # ── Finalize/Mark Paid Payroll ─────────────────────────────────────────────
    @staticmethod
    async def mark_as_paid(tenant_id: UUID, region: str, month: int, year: int) -> bool:
        run = await PayrollRun.find_one(
            PayrollRun.tenant_id == tenant_id,
            PayrollRun.region == PayrollRegion(region),
            PayrollRun.month == month,
            PayrollRun.year == year
        )
        if not run:
            raise ValueError("Payroll run not found")
            
        payslips = await Payslip.find(
            Payslip.tenant_id == tenant_id,
            Payslip.payroll_run_id == run.id
        ).to_list()
        
        for p in payslips:
            p.status = PayslipStatus.processed
            p.pay_date = datetime.utcnow()
            await p.save()
            
        from Models.employee import Payslip as EmployeePayslip
        for p in payslips:
            emp_slip = EmployeePayslip(
                tenant_id=tenant_id,
                user_id=p.employee_id, 
                month=f"{MONTHS[month-1][:3]} {year}",
                net_pay=p.net_pay,
                status="paid"
            )
            emp = await Employee.find_one(Employee.id == p.employee_id)
            if emp and emp.user_id:
                emp_slip.user_id = emp.user_id
                await emp_slip.insert()
            
        run.status = PayrollStatus.processed
        run.processed_at = datetime.utcnow()
        await run.save()
        return True

    # ── Preview Payroll ────────────────────────────────────────────────────────
    @staticmethod
    async def preview_payroll(
        tenant_id: UUID, region: str, month: int, year: int, employee_ids: Optional[List[UUID]] = None
    ) -> Dict[str, Any]:
        """Preview payroll calculations before running"""
        employees = await Employee.find(
            Employee.tenant_id == tenant_id,
            Employee.employment_status == "active"
        ).to_list()
        if employee_ids:
            emp_id_strs = [str(e) for e in employee_ids]
            employees = [e for e in employees if str(e.id) in emp_id_strs]
            
        configs = await PayrollService.get_employee_configs(tenant_id, region)
        config_map = {c.employee_id: c for c in configs}
        
        preview_data = []
        for emp in employees:
            cfg = config_map.get(emp.id)
            
            dept_name = ""
            if emp.department_id:
                dept = await Department.find_one(Department.id == emp.department_id)
                dept_name = dept.name if dept else ""
            
            job_title = ""
            if emp.job_title_id:
                jt = await JobTitle.find_one(JobTitle.id == emp.job_title_id)
                job_title = jt.name if jt else ""
            
            row = {
                "employee_id": str(emp.id),
                "employee_number": emp.employee_number,
                "name": f"{emp.first_name} {emp.last_name}",
                "designation": job_title or getattr(emp, 'job_title', ""),
                "dept": dept_name,
            }
            
            if region == "IN":
                basic = cfg.basic if cfg and cfg.basic else 0
                hra = cfg.hra if cfg and cfg.hra else 0
                allow = cfg.allowances if cfg and cfg.allowances else 0
                bonus = cfg.bonus if cfg and cfg.bonus else 0
                overtime = cfg.overtime if cfg and cfg.overtime else 0
                loan = cfg.loan if cfg and cfg.loan else 0
                advance = cfg.advance if cfg and cfg.advance else 0
                other = cfg.other if cfg and cfg.other else 0
                c = calc_in_deductions(basic, hra, allow, bonus, overtime, loan, advance, other)
                row.update(c)
                row.update({"basic": basic, "hra": hra, "allowances": allow, "bonus": bonus, "overtime": overtime})
                
            elif region == "US":
                gross = cfg.gross_salary if cfg and cfg.gross_salary else 0
                state = cfg.state if cfg and cfg.state else "CA"
                k401 = cfg.k401_rate if cfg and cfg.k401_rate else 0.05
                health = cfg.health_ins if cfg and cfg.health_ins else 250
                c = calc_us_deductions(gross, state, k401, health)
                row.update(c)
                
            elif region == "UK":
                gross = cfg.gross_monthly if cfg and cfg.gross_monthly else 0
                pension = cfg.pension_rate if cfg and cfg.pension_rate else 0.05
                c = calc_uk_deductions(gross, pension)
                row.update(c)
            
            preview_data.append(row)
        
        total_gross = sum(e.get("gross", 0) for e in preview_data)
        total_net = sum(e.get("net_pay", 0) for e in preview_data)
        total_ded = sum(e.get("deductions", 0) for e in preview_data)
        
        return {
            "region": region,
            "month": month,
            "year": year,
            "employee_count": len(preview_data),
            "employees": preview_data,
            "total_gross": total_gross,
            "total_net": total_net,
            "total_deductions": total_ded,
        }

    # ── Run Payroll ────────────────────────────────────────────────────────────
    @staticmethod
    async def run_payroll(
        tenant_id: UUID, region: str, month: int, year: int,
        employee_ids: Optional[List[UUID]] = None, created_by: Optional[UUID] = None
    ) -> PayrollRun:
        """Execute payroll run and generate payslips"""
        run = await PayrollRun.find_one(
            PayrollRun.tenant_id == tenant_id,
            PayrollRun.region == PayrollRegion(region),
            PayrollRun.month == month,
            PayrollRun.year == year
        )
        if not run:
            run = PayrollRun(
                tenant_id=tenant_id,
                region=PayrollRegion(region),
                month=month,
                year=year,
                status=PayrollStatus.processing,
                employee_ids=employee_ids or [],
                created_by=created_by
            )
            await run.insert()
            
        employees = await Employee.find(
            Employee.tenant_id == tenant_id,
            Employee.employment_status == "active"
        ).to_list()
        
        if run.employee_ids:
            emp_id_strs = [str(e) for e in run.employee_ids]
            employees = [e for e in employees if str(e.id) in emp_id_strs]
        elif employee_ids:
            emp_id_strs = [str(e) for e in employee_ids]
            employees = [e for e in employees if str(e.id) in emp_id_strs]
            
        configs = await PayrollService.get_employee_configs(tenant_id, region)
        config_map = {c.employee_id: c for c in configs}
        
        await Payslip.find(
            Payslip.tenant_id == tenant_id,
            Payslip.month == month,
            Payslip.year == year,
            Payslip.region == PayrollRegion(region)
        ).delete()
        
        payslips = []
        total_gross = 0
        total_ded = 0
        total_net = 0
        
        for emp in employees:
            cfg = config_map.get(emp.id)
            
            dept_name = ""
            if emp.department_id:
                dept = await Department.find_one(Department.id == emp.department_id)
                dept_name = dept.name if dept else ""
            
            job_title = ""
            if emp.job_title_id:
                jt = await JobTitle.find_one(JobTitle.id == emp.job_title_id)
                job_title = jt.name if jt else ""
            
            components = {}
            gross = 0
            deductions = 0
            net_pay = 0
            
            if region == "IN":
                basic = cfg.basic if cfg and cfg.basic else 0
                hra = cfg.hra if cfg and cfg.hra else 0
                allow = cfg.allowances if cfg and cfg.allowances else 0
                bonus = cfg.bonus if cfg and cfg.bonus else 0
                overtime = cfg.overtime if cfg and cfg.overtime else 0
                loan = cfg.loan if cfg and cfg.loan else 0
                advance = cfg.advance if cfg and cfg.advance else 0
                other = cfg.other if cfg and cfg.other else 0
                c = calc_in_deductions(basic, hra, allow, bonus, overtime, loan, advance, other)
                components = {
                    "basic": basic,
                    "hra": hra,
                    "allowances": allow,
                    "bonus": bonus,
                    "overtime": overtime,
                    "pf": c["pf"],
                    "esi": c["esi"],
                    "prof_tax": c["prof_tax"],
                    "tds": c["tds"],
                    "loan": c["loan"],
                    "advance": c["advance"],
                    "other": c["other"]
                }
                gross = c["gross"]
                deductions = c["deductions"]
                net_pay = c["net_pay"]
                
            elif region == "US":
                gross_s = cfg.gross_salary if cfg and cfg.gross_salary else 0
                state = cfg.state if cfg and cfg.state else "CA"
                k401 = cfg.k401_rate if cfg and cfg.k401_rate else 0.05
                health = cfg.health_ins if cfg and cfg.health_ins else 250
                c = calc_us_deductions(gross_s, state, k401, health)
                components = {
                    "gross": gross_s,
                    "state": state,
                    "federal_tax": c["federal_tax"],
                    "state_tax": c["state_tax"],
                    "social_sec": c["social_sec"],
                    "medicare": c["medicare"],
                    "k401": c["k401"],
                    "health_ins": c["health_ins"],
                }
                gross = c["gross"]
                deductions = c["deductions"]
                net_pay = c["net_pay"]
                
            elif region == "UK":
                gross_s = cfg.gross_monthly if cfg and cfg.gross_monthly else 0
                pension = cfg.pension_rate if cfg and cfg.pension_rate else 0.05
                c = calc_uk_deductions(gross_s, pension)
                components = {
                    "gross": gross_s,
                    "paye": c["paye"],
                    "ni": c["ni"],
                    "pension": c["pension"],
                }
                gross = c["gross"]
                deductions = c["deductions"]
                net_pay = c["net_pay"]
            
            payslip = Payslip(
                tenant_id=tenant_id,
                employee_id=emp.id,
                payroll_run_id=run.id,
                region=region,
                month=month,
                year=year,
                status=PayslipStatus.processed,
                employee_name=f"{emp.first_name} {emp.last_name}",
                designation=job_title or getattr(emp, 'job_title', ""),
                department=dept_name,
                components=components,
                gross=gross,
                deductions=deductions,
                net_pay=net_pay,
                pay_date=datetime.utcnow()
            )
            await payslip.insert()
            payslips.append(payslip)
            
            total_gross += gross
            total_ded += deductions
            total_net += net_pay
        
        run.status = PayrollStatus.processed
        run.payslip_count = len(payslips)
        run.total_gross = total_gross
        run.total_deductions = total_ded
        run.total_net = total_net
        run.processed_at = datetime.utcnow()
        await run.save()
        
        return run

    # ── Get Payslips ───────────────────────────────────────────────────────────
    @staticmethod
    async def get_payslips(
        tenant_id: UUID, region: str,
        month: Optional[int] = None,
        year: Optional[int] = None,
        status: Optional[str] = None,
        search: Optional[str] = None
    ) -> List[Payslip]:
        """Get payslips with filters"""
        query = [
            Payslip.tenant_id == tenant_id,
            Payslip.region == PayrollRegion(region)
        ]
        
        if month:
            query.append(Payslip.month == month)
        if year:
            query.append(Payslip.year == year)
        if status:
            query.append(Payslip.status == status)
        
        payslips = await Payslip.find(*query).to_list()
        
        if search:
            search_lower = search.lower()
            payslips = [
                p for p in payslips
                if search_lower in p.employee_name.lower() or
                   search_lower in p.department.lower()
            ]
        
        return payslips
