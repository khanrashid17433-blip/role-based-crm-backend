from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, timedelta
import logging
from uuid import UUID, uuid4

from Models.pm import (
    Project, ProjectMember, ProjectMilestone,
    Task, TaskWatcher, TaskSubtask, TaskTimeEntry, TaskStatus,
    ProjectStatus, Priority
)
from Schema.pm import (
    ProjectCreateRequest, ProjectUpdateRequest, MilestoneCreateRequest,
    TaskCreateRequest, TaskUpdateRequest, TaskSubtaskRequest, TaskTimeLogRequest
)

logger = logging.getLogger(__name__)


class PMService:

    # ─── PROJECT LOGIC ───────────────────────────────────────────────────────

    @staticmethod
    async def create_project(tenant_id: UUID, user_id: UUID, data: ProjectCreateRequest) -> Project:
        if data.type == "client_implementation" and not data.client_tenant_id:
            pass  # client name provided as plain text is fine

        project = Project(
            tenant_id=tenant_id,
            type=data.type,
            name=data.name,
            client_tenant_id=data.client_tenant_id,
            department=data.department,
            priority=data.priority,
            start_date=data.start_date,
            end_date=data.end_date,
            budget=data.budget,
            currency=data.currency,
            progress=data.progress,
            description_html=data.description_html,
            tags_json=data.tags,
            created_by=user_id
        )
        await project.insert()

        # Add Lead as a member
        if data.lead_id:
            lead_member = ProjectMember(project_id=project.id, user_id=data.lead_id, role="lead", added_by=user_id)
            await lead_member.insert()

        # Add team members
        for member_id in (data.team_members or []):
            if member_id != data.lead_id:
                member = ProjectMember(project_id=project.id, user_id=member_id, role="member", added_by=user_id)
                await member.insert()

        return project

    @staticmethod
    async def update_project(tenant_id: UUID, project_id: UUID, data: ProjectUpdateRequest, user_id: UUID) -> Project:
        project = await Project.find_one(
            Project.id == project_id,
            Project.tenant_id == tenant_id
        )
        if not project:
            raise ValueError("Project not found")

        if data.name is not None:             project.name = data.name
        if data.type is not None:             project.type = data.type
        if data.client is not None:           project.client = data.client
        if data.department is not None:       project.department = data.department
        if data.status is not None:           project.status = data.status
        if data.priority is not None:         project.priority = data.priority
        if data.start_date is not None:       project.start_date = data.start_date
        if data.end_date is not None:         project.end_date = data.end_date
        if data.actual_end_date is not None:  project.actual_end_date = data.actual_end_date
        if data.budget is not None:           project.budget = data.budget
        if data.progress is not None:         project.progress = data.progress
        if data.description_html is not None: project.description_html = data.description_html
        if data.tags is not None:             project.tags_json = data.tags

        # If lead_id or team_members are updated, we rewrite the members
        if data.lead_id is not None or data.team_members is not None:
            # Fetch current values if one of them is None
            lead_id = data.lead_id
            team_members = data.team_members
            
            if lead_id is None:
                curr_lead = await ProjectMember.find_one(
                    ProjectMember.project_id == project_id,
                    ProjectMember.role == "lead"
                )
                lead_id = curr_lead.user_id if curr_lead else None
                
            if team_members is None:
                curr_members = await ProjectMember.find(
                    ProjectMember.project_id == project_id,
                    ProjectMember.role == "member"
                ).to_list()
                team_members = [m.user_id for m in curr_members]

            # Clear all current members
            await ProjectMember.find(ProjectMember.project_id == project_id).delete()

            # Insert lead
            if lead_id:
                lead_member = ProjectMember(project_id=project.id, user_id=lead_id, role="lead", added_by=user_id)
                await lead_member.insert()

            # Insert team members
            for member_id in (team_members or []):
                if member_id != lead_id:
                    member = ProjectMember(project_id=project.id, user_id=member_id, role="member", added_by=user_id)
                    await member.insert()

        project.updated_at = datetime.utcnow()
        await project.save()
        return project

    # ─── TASK LOGIC ──────────────────────────────────────────────────────────

    @staticmethod
    async def create_task(tenant_id: UUID, user_id: UUID, data: TaskCreateRequest) -> Task:
        task = Task(
            tenant_id=tenant_id,
            project_id=data.project_id,
            parent_task_id=data.parent_task_id,
            title=data.title,
            description_html=data.description_html,
            related_type=data.related_type,
            related_id=data.related_id,
            assigned_to=data.assigned_to,
            created_by=user_id,
            priority=data.priority,
            status=data.status,
            due_at=data.due_at,
            reminder_at=data.reminder_at,
            estimated_hours=data.estimated_hours,
            tags_json=data.tags
        )
        await task.insert()

        for watcher_id in (data.watchers or []):
            watcher = TaskWatcher(task_id=task.id, user_id=watcher_id)
            await watcher.insert()

        # Note: Project progress is calculated dynamically at query time in get_dashboard_summary
        # and get_employee_summary to support manual overrides without database overwrites.
        return task

    @staticmethod
    async def update_task_status(tenant_id: UUID, task_id: UUID, status: Optional[TaskStatus] = None, priority: Optional[Priority] = None) -> Task:
        task = await Task.find_one(
            Task.id == task_id,
            Task.tenant_id == tenant_id
        )
        if not task:
            raise ValueError("Task not found")

        if status is not None:
            task.status = status
        if priority is not None:
            task.priority = priority
        task.updated_at = datetime.utcnow()
        await task.save()

        # Note: Project progress is calculated dynamically at query time in get_dashboard_summary
        # and get_employee_summary to support manual overrides without database overwrites.
        return task

    @staticmethod
    async def log_time(tenant_id: UUID, task_id: UUID, user_id: UUID, data: TaskTimeLogRequest) -> TaskTimeEntry:
        task = await Task.find_one(
            Task.id == task_id,
            Task.tenant_id == tenant_id
        )
        if not task:
            raise ValueError("Task not found")

        entry = TaskTimeEntry(
            task_id=task_id,
            user_id=user_id,
            started_at=data.started_at,
            ended_at=data.ended_at,
            duration_mins=data.duration_mins,
            note=data.note
        )
        await entry.insert()
        return entry

    # ─── MEMBERS ─────────────────────────────────────────────────────────────

    @staticmethod
    async def get_members(tenant_id: UUID) -> List[Dict[str, Any]]:
        from Models.employee import Employee
        employees = await Employee.find(Employee.tenant_id == tenant_id).to_list()
        members = []
        colors = [
            "bg-blue-500", "bg-violet-500", "bg-amber-500",
            "bg-emerald-500", "bg-rose-500", "bg-pink-500",
            "bg-indigo-500", "bg-teal-500"
        ]
        for emp in employees:
            # Use user_id as the canonical member ID (so tasks assigned to user_id match)
            member_id = emp.user_id or emp.id
            fn = emp.first_name or ""
            ln = emp.last_name or ""
            initials = ((fn[0] if fn else "") + (ln[0] if ln else "")).upper() or "EE"
            name_hash = sum(ord(c) for c in f"{fn} {ln}")
            color = colors[name_hash % len(colors)]
            members.append({
                "id": str(member_id),
                "name": f"{fn} {ln}".strip(),
                "initials": initials,
                "color": color,
                "title": "Employee",
                "dept": "Engineering"
            })
        return members

    # ─── DASHBOARD SUMMARY ────────────────────────────────────────────────────

    @staticmethod
    async def get_dashboard_summary(tenant_id: UUID, user_id: UUID) -> Dict[str, Any]:
        # Fetch all data
        projects = await Project.find(Project.tenant_id == tenant_id).to_list()
        tasks    = await Task.find(Task.tenant_id == tenant_id).to_list()
        members  = await PMService.get_members(tenant_id)

        # If no projects exist, keep them empty instead of seeding default mock data

        members_map = {m["id"]: m for m in members}

        # Stats
        today = datetime.utcnow()
        active_projects_count = len([
            p for p in projects
            if (p.status.value if hasattr(p.status, "value") else p.status)
               in ["in_progress", "planning", "not_started"]
        ])
        open_tasks_count   = len([t for t in tasks if t.status != TaskStatus.done])
        overdue_tasks_count = len([
            t for t in tasks
            if t.status != TaskStatus.done and t.due_at and t.due_at < today
        ])

        # Task counts per project
        project_task_counts: Dict[str, Dict] = {}
        for t in tasks:
            if t.project_id:
                p_id = str(t.project_id)
                if p_id not in project_task_counts:
                    project_task_counts[p_id] = {"todo": 0, "inProgress": 0, "review": 0, "done": 0}
                sv = t.status.value if hasattr(t.status, "value") else t.status
                if sv == "to_do":
                    project_task_counts[p_id]["todo"] += 1
                elif sv in ("in_progress", "blocked"):
                    project_task_counts[p_id]["inProgress"] += 1
                elif sv == "in_review":
                    project_task_counts[p_id]["review"] += 1
                elif sv in ("done", "cancelled"):
                    project_task_counts[p_id]["done"] += 1

        # Format projects
        formatted_projects = []
        for p in projects:
            p_id = str(p.id)
            p_members = await ProjectMember.find(ProjectMember.project_id == p.id).to_list()
            p_member_ids = [str(pm.user_id) for pm in p_members]
            lead_member = next((pm for pm in p_members if pm.role == "lead"), None)
            manager_id  = str(lead_member.user_id) if lead_member else (p_member_ids[0] if p_member_ids else str(user_id))

            counts = project_task_counts.get(p_id, {"todo": 0, "inProgress": 0, "review": 0, "done": 0})
            total_tasks = sum(counts.values())
            progress    = p.progress if (p.progress is not None) else (round((counts["done"] / total_tasks) * 100) if total_tasks > 0 else 0)

            p_status_val = p.status.value if hasattr(p.status, "value") else p.status
            health = "on-track"
            if p_status_val == "on_hold":
                health = "blocked"
            elif any(
                t for t in tasks
                if t.project_id == p.id and t.status != TaskStatus.done and t.due_at and t.due_at < today
            ):
                health = "at-risk"

            display_status = (
                "Active"    if p_status_val in ("in_progress", "planning", "not_started") else
                "On Hold"   if p_status_val == "on_hold" else
                "Completed" if p_status_val in ("completed", "cancelled") else
                "Active"
            )

            formatted_projects.append({
                "id":          p_id,
                "name":        p.name,
                "client":      p.client or "Internal",
                "clientLogo":  p.client_logo or (p.name[:2].upper() if p.name else "IN"),
                "clientColor": p.client_color or "bg-slate-600",
                "status":      display_status,
                "priority":    p.priority.value if hasattr(p.priority, "value") else str(p.priority),
                "health":      health,
                "managerId":   manager_id,
                "progress":    progress,
                "startDate":   p.start_date.isoformat() if p.start_date else "",
                "endDate":     p.end_date.isoformat()   if p.end_date   else "",
                "budget":      p.budget or 0,
                "spent":       int((p.budget or 0) * 0.6) if p.budget else 0,
                "description": p.description_html or "",
                "team":        p_member_ids,
                "taskCounts":  counts,
                "tags":        p.tags_json or []
            })

        # Team workload panel
        formatted_workloads = []
        for m in members:
            m_id = m["id"]
            member_tasks  = [t for t in tasks if str(t.assigned_to) == m_id]
            active_tasks  = [t for t in member_tasks if t.status != TaskStatus.done]
            overdue_tasks = [t for t in active_tasks if t.due_at and t.due_at < today]
            done_tasks    = [t for t in member_tasks if t.status == TaskStatus.done]

            assigned_project_ids = list(set(str(t.project_id) for t in active_tasks if t.project_id))
            assigned_projects = []
            for p_id in assigned_project_ids:
                p_obj = next((proj for proj in formatted_projects if proj["id"] == p_id), None)
                if p_obj:
                    assigned_projects.append({
                        "id": p_id,
                        "clientLogo":  p_obj["clientLogo"],
                        "clientColor": p_obj["clientColor"]
                    })

            formatted_workloads.append({
                "id":           m_id,
                "name":         m["name"],
                "initials":     m["initials"],
                "color":        m["color"],
                "title":        m["title"],
                "dept":         m["dept"],
                "totalTasks":   len(member_tasks),
                "activeTasks":  len(active_tasks),
                "overdueTasks": len(overdue_tasks),
                "doneTasks":    len(done_tasks),
                "projects":     assigned_projects
            })

        formatted_workloads.sort(key=lambda w: w["activeTasks"], reverse=True)

        # All tasks table
        status_map = {
            "to_do":      "To Do",
            "in_progress": "In Progress",
            "blocked":    "In Progress",
            "in_review":  "Review",
            "done":       "Done",
            "cancelled":  "Done"
        }
        priority_map = {
            "critical": "Critical",
            "high":     "High",
            "medium":   "Medium",
            "low":      "Low"
        }

        formatted_tasks = []
        for t in tasks:
            due_str      = t.due_at.strftime("%Y-%m-%d") if t.due_at else ""
            created_str  = t.created_at.strftime("%Y-%m-%d") if t.created_at else ""
            sv = t.status.value   if hasattr(t.status,   "value") else str(t.status)
            pv = t.priority.value if hasattr(t.priority, "value") else str(t.priority)

            formatted_tasks.append({
                "id":          str(t.id),
                "projectId":   str(t.project_id) if t.project_id else "",
                "title":       t.title,
                "description": t.description_html or "",
                "assignee":    str(t.assigned_to),
                "createdBy":   str(t.created_by),
                "priority":    priority_map.get(pv.lower(), "Medium"),
                "status":      status_map.get(sv.lower(), "To Do"),
                "dueDate":     due_str,
                "createdAt":   created_str,
                "tags":        t.tags_json or [],
                "comments": [
                    {
                        "id": str(c.id),
                        "userId": str(c.user_id),
                        "text": c.text,
                        "time": c.created_at.strftime("%I:%M %p, %d %b %Y") if c.created_at else "Just now"
                    } for c in (t.comments or [])
                ],
                "attachments": [
                    {
                        "id": str(att.get("id", "")),
                        "name": att.get("name", ""),
                        "size": att.get("size", 0),
                        "type": att.get("type", ""),
                        "url": att.get("url", "")
                    } for att in (t.attachments or [])
                ]
            })

        return {
            "stats": {
                "activeProjects": active_projects_count,
                "openTasks":      open_tasks_count,
                "overdueTasks":   overdue_tasks_count,
                "totalMembers":   len(members)
            },
            "projects":  formatted_projects,
            "workloads": formatted_workloads,
            "tasks":     formatted_tasks,
            "members":   members
        }

    @staticmethod
    async def get_employee_summary(tenant_id: UUID, user_id: UUID) -> Dict[str, Any]:
        # Find all project IDs where this user is a member
        member_records = await ProjectMember.find(ProjectMember.user_id == user_id).to_list()
        project_ids = [m.project_id for m in member_records]
        
        # Fetch those projects
        projects = await Project.find(
            {"_id": {"$in": project_ids}},
            Project.tenant_id == tenant_id
        ).to_list()
        
        # Fetch tasks assigned to this user
        tasks = await Task.find(
            Task.assigned_to == user_id,
            Task.tenant_id == tenant_id
        ).to_list()
        
        # Fetch all tenant members for mapping
        members = await PMService.get_members(tenant_id)
        members_map = {m["id"]: m for m in members}
        
        # Stats
        today = datetime.utcnow()
        assigned_projects_count = len(projects)
        my_tasks_count = len(tasks)
        
        in_progress_count = len([
            t for t in tasks 
            if (t.status.value if hasattr(t.status, "value") else t.status) in ["in_progress", "blocked", "in_review"]
        ])
        
        completed_count = len([
            t for t in tasks 
            if (t.status.value if hasattr(t.status, "value") else t.status) in ["done", "cancelled"]
        ])
        
        overdue_count = len([
            t for t in tasks 
            if (t.status.value if hasattr(t.status, "value") else t.status) not in ["done", "cancelled"] 
            and t.due_at and t.due_at < today
        ])
        
        # Task counts per project (for all tasks in the project to calculate overall project progress and stats)
        all_project_tasks = await Task.find(
            {"project_id": {"$in": project_ids}},
            Task.tenant_id == tenant_id
        ).to_list()
        
        project_task_counts = {}
        for t in all_project_tasks:
            p_id = str(t.project_id)
            if p_id not in project_task_counts:
                project_task_counts[p_id] = {
                    "total": 0, "todo": 0, "in_progress": 0, "review": 0, "done": 0, "overdue": 0
                }
            
            project_task_counts[p_id]["total"] += 1
            sv = t.status.value if hasattr(t.status, "value") else t.status
            if sv == "to_do":
                project_task_counts[p_id]["todo"] += 1
            elif sv in ["in_progress", "blocked"]:
                project_task_counts[p_id]["in_progress"] += 1
            elif sv == "in_review":
                project_task_counts[p_id]["review"] += 1
            elif sv in ["done", "cancelled"]:
                project_task_counts[p_id]["done"] += 1
                
            if sv not in ["done", "cancelled"] and t.due_at and t.due_at < today:
                project_task_counts[p_id]["overdue"] += 1
                
        # Format projects
        formatted_projects = []
        for p in projects:
            p_id = str(p.id)
            
            # Find lead/manager
            p_members = await ProjectMember.find(ProjectMember.project_id == p.id).to_list()
            lead_member = next((pm for pm in p_members if pm.role == "lead"), None)
            lead_id = str(lead_member.user_id) if lead_member else (str(p_members[0].user_id) if p_members else None)
            lead_name = members_map.get(lead_id, {}).get("name", "Unknown") if lead_id else "Unknown"
            
            counts = project_task_counts.get(p_id, {"total": 0, "todo": 0, "in_progress": 0, "review": 0, "done": 0, "overdue": 0})
            progress = p.progress if (p.progress is not None) else (round((counts["done"] / counts["total"]) * 100) if counts["total"] > 0 else 0)
            
            p_status_val = p.status.value if hasattr(p.status, "value") else p.status
            display_status = (
                "Active" if p_status_val in ["in_progress", "planning", "not_started"] else
                "On Hold" if p_status_val == "on_hold" else
                "Completed" if p_status_val in ["completed", "cancelled"] else "Active"
            )
            
            formatted_projects.append({
                "id": p_id,
                "name": p.name,
                "client": p.client or "Internal",
                "clientLogo": p.client_logo or (p.name[:2].upper() if p.name else "IN"),
                "clientColor": p.client_color or "bg-slate-600",
                "status": display_status,
                "progress": progress,
                "startDate": p.start_date.strftime("%d %b %Y") if p.start_date else "",
                "endDate": p.end_date.strftime("%d %b %Y") if p.end_date else "",
                "leadName": lead_name,
                "taskCounts": counts
            })
            
        # Format tasks
        status_map = {
            "to_do": "To Do",
            "in_progress": "In Progress",
            "blocked": "In Progress",
            "in_review": "Review",
            "done": "Done",
            "cancelled": "Done"
        }
        priority_map = {
            "critical": "Critical",
            "high": "High",
            "medium": "Medium",
            "low": "Low"
        }
        
        formatted_tasks = []
        for t in tasks:
            due_str = t.due_at.strftime("%Y-%m-%d") if t.due_at else ""
            created_str = t.created_at.strftime("%Y-%m-%d") if t.created_at else ""
            sv = t.status.value if hasattr(t.status, "value") else str(t.status)
            pv = t.priority.value if hasattr(t.priority, "value") else str(t.priority)
            
            # Find creator
            creator_id = str(t.created_by)
            creator_info = members_map.get(creator_id, {"name": "Admin", "initials": "AD", "color": "bg-slate-500"})
            
            proj_obj = next((proj for proj in projects if proj.id == t.project_id), None)
            
            formatted_tasks.append({
                "id": str(t.id),
                "projectId": str(t.project_id) if t.project_id else "",
                "projectName": proj_obj.name if proj_obj else "Independent Task",
                "title": t.title,
                "description": t.description_html or "",
                "assignee": str(t.assigned_to),
                "createdBy": creator_id,
                "assignedByName": creator_info.get("name"),
                "assignedByInitials": creator_info.get("initials"),
                "assignedByColor": creator_info.get("color"),
                "priority": priority_map.get(pv.lower(), "Medium"),
                "status": status_map.get(sv.lower(), "To Do"),
                "dueDate": due_str,
                "createdAt": created_str,
                "tags": t.tags_json or [],
                "comments": [
                    {
                        "id": str(c.id),
                        "userId": str(c.user_id),
                        "text": c.text,
                        "time": c.created_at.strftime("%I:%M %p, %d %b %Y") if c.created_at else "Just now"
                    } for c in (t.comments or [])
                ],
                "attachments": [
                    {
                        "id": str(att.get("id", "")),
                        "name": att.get("name", ""),
                        "size": att.get("size", 0),
                        "type": att.get("type", ""),
                        "url": att.get("url", "")
                    } for att in (t.attachments or [])
                ]
            })
            
        return {
            "stats": {
                "assignedProjects": assigned_projects_count,
                "myTasks": my_tasks_count,
                "inProgressTasks": in_progress_count,
                "completedTasks": completed_count,
                "overdueTasks": overdue_count
            },
            "projects": formatted_projects,
            "tasks": formatted_tasks,
            "members": members
        }

    # ─── DEFAULT SEED ────────────────────────────────────────────────────────

    @staticmethod
    async def seed_default_projects_and_tasks(tenant_id: UUID, user_id: UUID):
        from Models.employee import Employee

        employees    = await Employee.find(Employee.tenant_id == tenant_id).to_list()
        employee_ids = [emp.user_id or emp.id for emp in employees]
        if not employee_ids:
            employee_ids = [user_id]

        default_projects = [
            {
                "name":        "Client Alpha — HRMS Onboarding",
                "client":      "Alpha Corp",
                "logo":        "AC",
                "color":       "bg-blue-600",
                "status":      ProjectStatus.in_progress,
                "priority":    Priority.high,
                "start_delta": -30,
                "end_delta":   15,
                "budget":      480000,
                "desc":        "Complete HRMS setup for Alpha Corp including employee onboarding, payroll config, and attendance automation.",
            },
            {
                "name":        "Payroll Engine v2.0",
                "client":      "Internal",
                "logo":        "IN",
                "color":       "bg-slate-600",
                "status":      ProjectStatus.in_progress,
                "priority":    Priority.critical,
                "start_delta": -45,
                "end_delta":   45,
                "budget":      0,
                "desc":        "Rebuild payroll calculation engine to support multi-state tax, custom pay components, and compliance-ready processing.",
            },
            {
                "name":        "Client Beta — Data Migration",
                "client":      "Beta Industries",
                "logo":        "BI",
                "color":       "bg-emerald-600",
                "status":      ProjectStatus.on_hold,
                "priority":    Priority.high,
                "start_delta": -20,
                "end_delta":   10,
                "budget":      220000,
                "desc":        "Data migration from legacy HR system including employee records, attendance history, and payroll history.",
            },
            {
                "name":        "Recruitment ATS Enhancement",
                "client":      "Internal",
                "logo":        "IN",
                "color":       "bg-slate-600",
                "status":      ProjectStatus.in_progress,
                "priority":    Priority.medium,
                "start_delta": -60,
                "end_delta":   -5,
                "budget":      0,
                "desc":        "AI-powered resume screening, interview scheduling automation, and offer management.",
            },
        ]

        project_map: Dict[str, Project] = {}
        for idx, p_data in enumerate(default_projects):
            proj = Project(
                tenant_id=tenant_id,
                type="client_implementation" if p_data["client"] != "Internal" else "internal",
                name=p_data["name"],
                client=p_data["client"],
                client_logo=p_data["logo"],
                client_color=p_data["color"],
                status=p_data["status"],
                priority=p_data["priority"],
                start_date=datetime.utcnow() + timedelta(days=p_data["start_delta"]),
                end_date=datetime.utcnow()   + timedelta(days=p_data["end_delta"]),
                budget=p_data["budget"] or None,
                currency="INR",
                description_html=p_data["desc"],
                created_by=user_id
            )
            await proj.insert()
            project_map[p_data["name"]] = proj

            # Lead + team
            p_lead = employee_ids[idx % len(employee_ids)]
            lead_m = ProjectMember(project_id=proj.id, user_id=p_lead, role="lead", added_by=user_id)
            await lead_m.insert()
            for emp_id in employee_ids:
                if emp_id != p_lead:
                    mem = ProjectMember(project_id=proj.id, user_id=emp_id, role="member", added_by=user_id)
                    await mem.insert()

        default_tasks = [
            {"proj": "Client Alpha — HRMS Onboarding", "title": "Setup employee database schema",
             "desc": "Design core employee DB schema with all required fields.",
             "priority": Priority.high, "status": TaskStatus.done, "due_delta": -15, "tags": ["Backend", "DB"]},
            {"proj": "Client Alpha — HRMS Onboarding", "title": "Configure payroll rules for Alpha",
             "desc": "Map client payroll structure — CTC breakdown, deductions, statutory components.",
             "priority": Priority.high, "status": TaskStatus.done, "due_delta": -10, "tags": ["Payroll"]},
            {"proj": "Client Alpha — HRMS Onboarding", "title": "Employee bulk import (CSV)",
             "desc": "Build CSV import utility with validation for 300+ employee records.",
             "priority": Priority.high, "status": TaskStatus.in_progress, "due_delta": 5, "tags": ["Import", "Feature"]},
            {"proj": "Client Alpha — HRMS Onboarding", "title": "Onboarding portal UI",
             "desc": "Employee-facing onboarding checklist and document upload portal.",
             "priority": Priority.medium, "status": TaskStatus.in_progress, "due_delta": 8, "tags": ["UI", "Onboarding"]},
            {"proj": "Payroll Engine v2.0", "title": "Tax slab engine refactor",
             "desc": "Rewrite tax computation to support state-wise slabs and surcharge rules.",
             "priority": Priority.critical, "status": TaskStatus.in_progress, "due_delta": -2, "tags": ["Backend", "Tax"]},
            {"proj": "Payroll Engine v2.0", "title": "Multi-component pay builder UI",
             "desc": "Drag-and-drop pay structure builder for HR configurability.",
             "priority": Priority.high, "status": TaskStatus.to_do, "due_delta": 12, "tags": ["UI"]},
            {"proj": "Client Beta — Data Migration", "title": "Data audit — legacy HR system",
             "desc": "Audit 5 years of employee data for quality and migration readiness.",
             "priority": Priority.high, "status": TaskStatus.done, "due_delta": -5, "tags": ["Data", "Audit"]},
            {"proj": "Client Beta — Data Migration", "title": "Migration script — employee records",
             "desc": "ETL script to migrate employee master data with field mapping validation.",
             "priority": Priority.high, "status": TaskStatus.in_progress, "due_delta": 6, "tags": ["ETL", "Backend"]},
            {"proj": "Recruitment ATS Enhancement", "title": "AI resume screening integration",
             "desc": "Integrate GPT-based resume parser for candidate scoring.",
             "priority": Priority.high, "status": TaskStatus.in_review, "due_delta": 1, "tags": ["AI", "Feature"]},
        ]

        for idx, t_data in enumerate(default_tasks):
            proj = project_map.get(t_data["proj"])
            if proj:
                task_assignee = employee_ids[idx % len(employee_ids)]
                task = Task(
                    tenant_id=tenant_id,
                    project_id=proj.id,
                    title=t_data["title"],
                    description_html=t_data["desc"],
                    assigned_to=task_assignee,
                    created_by=user_id,
                    priority=t_data["priority"],
                    status=t_data["status"],
                    due_at=datetime.utcnow() + timedelta(days=t_data["due_delta"]),
                    tags_json=t_data["tags"]
                )
                await task.insert()

        logger.info(f"Seeded {len(default_projects)} projects and {len(default_tasks)} tasks for tenant {tenant_id}")

    @staticmethod
    async def add_task_comment(tenant_id: UUID, task_id: UUID, user_id: UUID, text: str) -> dict:
        task = await Task.find_one(Task.id == task_id, Task.tenant_id == tenant_id)
        if not task:
            raise ValueError("Task not found")
        from Models.pm import TaskComment
        comment = TaskComment(
            id=uuid4(),
            user_id=user_id,
            text=text,
            created_at=datetime.utcnow()
        )
        if task.comments is None:
            task.comments = []
        task.comments.append(comment)
        await task.save()
        return {
            "id": str(comment.id),
            "userId": str(comment.user_id),
            "text": comment.text,
            "time": comment.created_at.strftime("%I:%M %p, %d %b %Y")
        }

    @staticmethod
    async def add_task_attachment(tenant_id: UUID, task_id: UUID, user_id: UUID, file_name: str, file_size: int, content_type: str, file_url: str) -> dict:
        task = await Task.find_one(Task.id == task_id, Task.tenant_id == tenant_id)
        if not task:
            raise ValueError("Task not found")
        
        attachment = {
            "id": str(uuid4()),
            "name": file_name,
            "size": file_size,
            "type": content_type,
            "url": file_url
        }
        if task.attachments is None:
            task.attachments = []
        task.attachments.append(attachment)
        await task.save()
        return attachment

    @staticmethod
    async def delete_task_attachment(tenant_id: UUID, task_id: UUID, attachment_id: str) -> None:
        task = await Task.find_one(Task.id == task_id, Task.tenant_id == tenant_id)
        if not task:
            raise ValueError("Task not found")
        if task.attachments:
            original_len = len(task.attachments)
            task.attachments = [att for att in task.attachments if att.get("id") != attachment_id]
            if len(task.attachments) != original_len:
                await task.save()
